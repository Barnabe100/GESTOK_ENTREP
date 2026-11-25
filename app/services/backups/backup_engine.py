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

import os
import re
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models import Base

BACKUP_PREFIX = "stockmanager_backup"
PRERESTORE_PREFIX = "stockmanager_prerestore"

# Mission corrective « Fiabilisation du module de sauvegarde », §3.2/§3.9 :
# un remplacement de fichier (ex. sous Windows, antivirus/indexeur détenant
# brièvement une poignée sur le fichier) peut échouer transitoirement — ces
# quelques nouvelles tentatives rapprochées restent très rapides (1 s au
# total au maximum) et sans effet perceptible sur une opération qui dure de
# toute façon plusieurs secondes.
_REPLACE_RETRY_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_SECONDS = 0.2


class RestoreValidationError(Exception):
    """Le fichier restauré vers un emplacement temporaire n'a pas passé la
    vérification d'intégrité SQLite (``PRAGMA integrity_check``) avant tout
    remplacement de la base de destination — celle-ci n'a, dans ce cas,
    jamais été touchée (voir :func:`restore_database_from_backup`)."""


class AtomicReplaceError(Exception):
    """Le remplacement atomique final (``os.replace``) a échoué après
    plusieurs tentatives — typiquement un verrou transitoire sous Windows
    (antivirus, indexeur, sauvegarde système). La destination d'origine n'a
    jamais été modifiée (``os.replace`` est tout-ou-rien, jamais un état
    intermédiaire) ; la copie déjà créée et déjà vérifiée reste disponible
    à :attr:`recovered_path`, jamais perdue ni supprimée automatiquement."""

    def __init__(self, message: str, recovered_path: Path) -> None:
        super().__init__(message)
        self.recovered_path = recovered_path


def _replace_atomically_with_retry(source: Path, destination: Path) -> None:
    """``os.replace(source, destination)`` avec quelques nouvelles
    tentatives rapprochées en cas d'``OSError`` — jamais supposé réussir du
    premier coup sous Windows (§3.2 de la mission corrective : « ne pas
    supposer que os.replace fonctionnera automatiquement sur une base
    encore ouverte »). Sans effet perceptible sous POSIX, où ce genre
    d'échec transitoire de renommage n'existe normalement pas. En cas
    d'échec persistant, ``source`` n'est jamais supprimé — voir
    :class:`AtomicReplaceError`."""
    last_exc: Optional[OSError] = None
    for attempt in range(_REPLACE_RETRY_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except OSError as exc:
            last_exc = exc
            if attempt < _REPLACE_RETRY_ATTEMPTS - 1:
                time.sleep(_REPLACE_RETRY_DELAY_SECONDS)
    raise AtomicReplaceError(
        f"Le remplacement de « {destination} » a échoué après {_REPLACE_RETRY_ATTEMPTS} tentative(s) "
        f"({last_exc}) — probablement un verrou transitoire (ex. antivirus) sous Windows.",
        recovered_path=source,
    )

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
    métier propre et de l'auditer, jamais de prétendre un succès.

    Écrit d'abord dans un fichier temporaire du même répertoire (nom ne
    correspondant jamais au motif de nommage StockManager, donc invisible
    de ``list_backup_files``/la rotation tant qu'il existe), puis ne
    renomme vers le nom final qu'une fois la copie terminée (§3.9 de la
    mission corrective) : une interruption brutale pendant la copie ne
    laisse ainsi jamais de fichier partiel visible sous un nom de
    sauvegarde reconnu — jamais besoin que l'appelant le découvre a
    posteriori via une vérification d'intégrité."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = _next_available_path(destination_dir, generate_backup_filename(prefix, when))
    fd, tmp_path_str = tempfile.mkstemp(dir=str(destination_dir), prefix=f".{target.name}_", suffix=".creating.tmp")
    os.close(fd)
    tmp_path = Path(tmp_path_str)
    try:
        _sqlite_backup(db_path, tmp_path)
        _replace_atomically_with_retry(tmp_path, target)
    except AtomicReplaceError:
        # Remplacement final impossible malgré les nouvelles tentatives :
        # la copie reste disponible (voir AtomicReplaceError), mais jamais
        # sous le nom de sauvegarde final tant qu'elle n'y a pas été
        # effectivement renommée — jamais supprimée ici pour autant,
        # contrairement aux autres échecs, afin de ne pas perdre une copie
        # par ailleurs entièrement valide.
        raise
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return target


def restore_database_from_backup(backup_path: Path, db_path: Path) -> None:
    """Restaure ``db_path`` à partir de ``backup_path``.

    Jamais un remplacement direct (§3.2 de la mission corrective) : copie
    d'abord vers un fichier temporaire du même répertoire que ``db_path``,
    vérifie son intégrité structurelle SQLite (``PRAGMA integrity_check``,
    via :func:`verify_backup_file`) — la vérification de compatibilité de
    version/moteur reste de la responsabilité de l'appelant, avant même
    d'arriver ici — puis ne remplace ``db_path`` que si cette vérification
    réussit, via un remplacement atomique (``os.replace``, avec quelques
    nouvelles tentatives, voir :func:`_replace_atomically_with_retry`).

    ``db_path`` n'est, dans tous les cas, jamais touché avant que la copie
    temporaire ne soit intégralement écrite et vérifiée : une interruption
    à n'importe quelle étape qui précède laisse ``db_path`` parfaitement
    intact. Lève :class:`RestoreValidationError` si la vérification
    échoue, ou :class:`AtomicReplaceError` si le remplacement final échoue
    malgré les nouvelles tentatives (dans les deux cas, ``db_path`` reste
    intact ; voir leurs docstrings pour la suite)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(db_path.parent), prefix=f".{db_path.name}_restore_", suffix=".tmp"
    )
    os.close(fd)
    tmp_path = Path(tmp_path_str)
    try:
        _sqlite_backup(backup_path, tmp_path)
        verification = verify_backup_file(tmp_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    if not verification.integrity_ok:
        tmp_path.unlink(missing_ok=True)
        raise RestoreValidationError(
            "Le fichier restauré n'a pas passé la vérification d'intégrité SQLite avant "
            "remplacement : " + "; ".join(verification.errors or ["échec de PRAGMA integrity_check."])
        )
    # Jamais supprimé par ce chemin si le remplacement échoue (voir
    # AtomicReplaceError.recovered_path) : seul le chemin de vérification
    # ci-dessus supprime la copie temporaire, jamais celui-ci.
    _replace_atomically_with_retry(tmp_path, db_path)


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
