"""Mécanique pure des sauvegardes SQLite : création, vérification, rotation,
restauration.

Aucune dépendance à SQLAlchemy, aucune vérification de permission, aucun
audit ici — ce module est un ensemble de fonctions déterministes opérant
directement sur des fichiers, réutilisées à l'identique par
:class:`~app.services.backups.backup_service.BackupService` (orchestration,
permissions, audit) et par ``app/backup_cli.py`` (exécution hors
application graphique, cf. §8 du cahier des charges de cette phase).

Méthode de sauvegarde retenue (§3) : l'API de sauvegarde en ligne de SQLite
(``sqlite3.Connection.backup()``, wrapper stdlib de ``sqlite3_backup_init/
step/finish``) — jamais ``shutil.copy`` pendant que l'application utilise
activement la base. Cette API produit une copie cohérente même en présence
de transactions actives ou d'un journal WAL, contrairement à une copie de
fichier brute qui pourrait capturer un état incohérent. La restauration
réutilise la même API, simplement avec la source et la destination
inversées — aucune deuxième méthode de copie n'est introduite.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models import Base

BACKUP_PREFIX = "stockmanager_backup"
PRERESTORE_PREFIX = "stockmanager_prerestore"

# Nom de fichier strictement reconnaissable : c'est ce motif, et lui seul,
# qui identifie un fichier comme appartenant à StockManager pour la rotation
# (§6) — jamais un simple « *.db » générique, qui supprimerait des fichiers
# étrangers présents dans le même dossier.
_FILENAME_RE_TEMPLATE = r"^{prefix}_\d{{8}}_\d{{6}}(?:_\d+)?\.db$"


def _filename_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(_FILENAME_RE_TEMPLATE.format(prefix=re.escape(prefix)))


def _expected_tables() -> set[str]:
    """Tables attendues dans une sauvegarde valide : dérivées directement du
    mapping SQLAlchemy (``Base.metadata``), jamais recopiées à la main —
    reste automatiquement synchronisé avec le schéma au fil des phases."""
    return set(Base.metadata.tables.keys())


def _sqlite_backup(source_path: Path, destination_path: Path) -> None:
    """Copie cohérente de ``source_path`` vers ``destination_path`` via l'API
    de sauvegarde en ligne de SQLite. Utilisée aussi bien pour créer une
    sauvegarde (base active -> fichier de sauvegarde) que pour restaurer
    (fichier de sauvegarde -> base active) : même mécanisme dans les deux
    sens, par symétrie."""
    source_conn = sqlite3.connect(str(source_path))
    try:
        dest_conn = sqlite3.connect(str(destination_path))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()


def generate_backup_filename(prefix: str = BACKUP_PREFIX, when: Optional[datetime] = None) -> str:
    when = when or datetime.now()
    return f"{prefix}_{when.strftime('%Y%m%d_%H%M%S')}.db"


def _next_available_path(destination_dir: Path, filename: str) -> Path:
    """Évite toute collision de nom (§2) : ajoute un suffixe numérique si un
    fichier du même nom existe déjà (ex. deux sauvegardes lancées dans la
    même seconde)."""
    candidate = destination_dir / filename
    if not candidate.exists():
        return candidate
    stem, suffix = filename[:-3], 2
    while True:
        candidate = destination_dir / f"{stem}_{suffix}.db"
        if not candidate.exists():
            return candidate
        suffix += 1


def create_backup_file(
    db_path: Path, destination_dir: Path, *, prefix: str = BACKUP_PREFIX, when: Optional[datetime] = None
) -> Path:
    """Crée une sauvegarde cohérente de ``db_path`` dans ``destination_dir``
    et retourne le chemin créé. Lève ``OSError``/``sqlite3.Error`` telle
    quelle en cas d'échec (dossier non accessible, disque plein, ...) —
    c'est à l'appelant (``BackupService``) de traduire cet échec en réponse
    métier propre et de l'auditer, jamais de prétendre un succès."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = _next_available_path(destination_dir, generate_backup_filename(prefix, when))
    _sqlite_backup(db_path, target)
    return target


def restore_database_from_backup(backup_path: Path, db_path: Path) -> None:
    """Restaure ``db_path`` à partir de ``backup_path`` via la même API de
    sauvegarde en ligne (source et destination inversées par rapport à
    ``create_backup_file``)."""
    _sqlite_backup(backup_path, db_path)


@dataclass(frozen=True)
class BackupVerification:
    """Résultat de la vérification d'un fichier de sauvegarde (§4, §10)."""

    valid: bool
    integrity_ok: bool
    tables_ok: bool
    alembic_version: Optional[str]
    errors: list[str] = field(default_factory=list)


def verify_backup_file(file_path: Path) -> BackupVerification:
    """Vérifie qu'un fichier est une base SQLite valide, cohérente
    (``PRAGMA integrity_check``), et contient les tables attendues. Ne
    vérifie PAS ici la compatibilité de version de schéma avec la base
    actuelle — c'est le rôle de l'appelant lors d'une restauration (§10),
    qui compare ``alembic_version`` à la version courante."""
    if not file_path.exists() or not file_path.is_file():
        return BackupVerification(False, False, False, None, ["Le fichier de sauvegarde est introuvable."])

    try:
        # Ouverture en lecture seule via URI : n'écrit jamais dans le fichier
        # vérifié, y compris s'il ne s'agit pas réellement d'une base SQLite.
        connection = sqlite3.connect(f"file:{file_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return BackupVerification(False, False, False, None, [f"Fichier illisible ou non SQLite : {exc}"])

    errors: list[str] = []
    integrity_ok = False
    tables_ok = False
    alembic_version: Optional[str] = None
    try:
        row = connection.execute("PRAGMA integrity_check;").fetchone()
        integrity_ok = row is not None and row[0] == "ok"
        if not integrity_ok:
            errors.append("La vérification d'intégrité SQLite a échoué.")

        actual_tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table';")}
        missing = _expected_tables() - actual_tables
        tables_ok = not missing
        if not tables_ok:
            errors.append(f"Tables manquantes dans la sauvegarde : {', '.join(sorted(missing))}")

        try:
            version_row = connection.execute("SELECT version_num FROM alembic_version;").fetchone()
            alembic_version = version_row[0] if version_row else None
        except sqlite3.Error:
            errors.append("Impossible de lire la version de schéma (table alembic_version).")
    except sqlite3.Error as exc:
        errors.append(f"Erreur lors de la lecture de la sauvegarde : {exc}")
    finally:
        connection.close()

    return BackupVerification(
        valid=integrity_ok and tables_ok, integrity_ok=integrity_ok, tables_ok=tables_ok,
        alembic_version=alembic_version, errors=errors,
    )


def get_alembic_version(db_path: Path) -> Optional[str]:
    """Lit la version de schéma de la base active — utilisée pour comparer à
    celle d'une sauvegarde avant restauration (§10)."""
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version;").fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


@dataclass(frozen=True)
class BackupFileInfo:
    """Une ligne de l'historique des sauvegardes (§15)."""

    path: Path
    name: str
    size_bytes: int
    modified_at: datetime


def list_backup_files(destination_dir: Path, *, prefix: str = BACKUP_PREFIX) -> list[BackupFileInfo]:
    """Sauvegardes StockManager présentes dans ``destination_dir``, triées de
    la plus récente à la plus ancienne. Ne renvoie jamais un fichier ne
    correspondant pas exactement au motif de nommage StockManager (§6)."""
    if not destination_dir.exists():
        return []
    pattern = _filename_pattern(prefix)
    infos = []
    for entry in destination_dir.iterdir():
        if entry.is_file() and pattern.match(entry.name):
            stat = entry.stat()
            infos.append(
                BackupFileInfo(
                    path=entry, name=entry.name, size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                )
            )
    return sorted(infos, key=lambda info: info.name, reverse=True)


def apply_retention(destination_dir: Path, retention: int, *, prefix: str = BACKUP_PREFIX) -> list[Path]:
    """Supprime les sauvegardes StockManager excédant ``retention`` (les plus
    anciennes en premier). Ne touche jamais un fichier hors du motif de
    nommage StockManager (§6). ``retention <= 0`` est traité comme « ne rien
    supprimer » (choix sûr par défaut plutôt que « tout supprimer »)."""
    if retention <= 0:
        return []
    files = list_backup_files(destination_dir, prefix=prefix)
    deleted: list[Path] = []
    for info in files[retention:]:
        try:
            info.path.unlink()
            deleted.append(info.path)
        except OSError:
            continue
    return deleted
