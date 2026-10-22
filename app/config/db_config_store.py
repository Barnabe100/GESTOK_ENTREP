"""Persistance locale, hors base de données, du choix de moteur actif.

Lot D (configuration utilisateur PostgreSQL) : ``app.config.settings``
construit ``Settings`` à partir de l'environnement (déploiement scripté,
Lot A, inchangé) OU, si aucune variable ``STOCKMANAGER_DB_BACKEND`` n'est
définie, à partir du fichier lu par ce module — jamais les deux à la fois,
jamais une fusion partielle : voir ``app.config.settings._load_settings_from_env``.

Pourquoi un fichier séparé, jamais la table ``parametres`` existante
(``app.repositories.parameter_repository``) : cette table vit **dans** la
base active elle-même. Il faudrait donc déjà savoir à quelle base se
connecter pour pouvoir lire la configuration qui dit à quelle base se
connecter — dépendance circulaire. Ce fichier vit à côté de la base
(``Settings.data_dir``), jamais dedans.

Ce fichier ne contient **jamais** de mot de passe, de jeton ni aucun autre
secret — uniquement l'hôte, le port, le nom de base, l'utilisateur, et
(si PostgreSQL) ``credential_key`` : un identifiant stable et non secret du
profil de connexion, utilisé pour retrouver le mot de passe correspondant
dans le coffre d'identifiants du système (voir
``app.security.credential_vault``) — jamais le mot de passe lui-même.

Distinction active/en attente (§4.3 du mandat) : ``active`` est la
configuration que le processus courant utilise réellement ; ``pending``,
si présente, est une configuration déjà enregistrée par un administrateur
mais pas encore appliquée — elle ne devient ``active`` qu'au prochain
démarrage complet de l'application (voir ``promote_pending_to_active``,
appelée une seule fois, au tout début du démarrage, jamais en cours de
session : aucune fonction de ce module ne doit être appelée après que
``get_settings()``/``get_engine()`` ont déjà été résolus pour ce
processus).

Tolérance aux fichiers absents/corrompus/incompatibles (§D.1 du mandat) :
toute lecture invalide (JSON illisible, version inconnue, champ manquant,
port hors plage, etc.) est journalisée puis traitée comme une absence de
fichier — jamais une exception propagée, jamais une configuration
PostgreSQL partiellement reconstruite. Le repli est toujours SQLite,
jamais l'inverse : une installation existante qui ne possède pas ce
fichier (ou dont le fichier est illisible) continue de fonctionner
exactement comme avant ce lot.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from app.utils.logging_config import get_logger

logger = get_logger("config.db_config_store")

DB_CONFIG_FILENAME = "db_config.json"
DB_CONFIG_FILE_VERSION = 1

_VALID_BACKENDS = {"sqlite", "postgresql"}


@dataclass(frozen=True)
class PostgreSQLProfile:
    """Paramètres de connexion PostgreSQL non secrets, persistés tels quels.

    ``credential_key`` identifie le secret correspondant dans le coffre
    d'identifiants (voir docstring de module) — jamais le mot de passe
    lui-même, qui n'existe nulle part dans ce fichier."""

    host: str
    port: int
    database: str
    username: str
    credential_key: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DbEngineConfig:
    """Un choix de moteur complet : ``backend`` seul pour SQLite,
    ``backend`` + ``postgresql`` pour PostgreSQL."""

    backend: str
    postgresql: Optional[PostgreSQLProfile] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "postgresql": self.postgresql.to_dict() if self.postgresql is not None else None,
        }


@dataclass(frozen=True)
class DbConfigFile:
    """Contenu complet du fichier de configuration externe."""

    version: int
    active: DbEngineConfig
    pending: Optional[DbEngineConfig] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "active": self.active.to_dict(),
            "pending": self.pending.to_dict() if self.pending is not None else None,
        }


def _default_sqlite_config() -> DbConfigFile:
    """Configuration de repli — toujours SQLite, jamais PostgreSQL : voir
    docstring de module (tolérance aux fichiers absents/corrompus)."""
    return DbConfigFile(version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"), pending=None)


def default_db_config_path(data_dir: Path) -> Path:
    return data_dir / DB_CONFIG_FILENAME


def _parse_postgresql_profile(raw: Any, *, context: str) -> PostgreSQLProfile:
    if not isinstance(raw, dict):
        raise ValueError(f"{context}.postgresql doit être un objet JSON.")

    host = raw.get("host")
    if not isinstance(host, str) or not host.strip():
        raise ValueError(f"{context}.postgresql.host est requis et doit être une chaîne non vide.")

    port = raw.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not (0 < port <= 65535):
        raise ValueError(f"{context}.postgresql.port invalide (entier 1-65535 attendu) : {port!r}.")

    database = raw.get("database")
    if not isinstance(database, str) or not database.strip():
        raise ValueError(f"{context}.postgresql.database est requis et doit être une chaîne non vide.")

    username = raw.get("username")
    if not isinstance(username, str) or not username.strip():
        raise ValueError(f"{context}.postgresql.username est requis et doit être une chaîne non vide.")

    credential_key = raw.get("credential_key")
    if not isinstance(credential_key, str) or not credential_key.strip():
        raise ValueError(f"{context}.postgresql.credential_key est requis et doit être une chaîne non vide.")

    # Jamais de mot de passe dans ce fichier : une clé "password" présente
    # (écriture manuelle erronée, fichier d'une version future incompatible)
    # est un champ invalide, pas une valeur à ignorer silencieusement.
    for forbidden_key in ("password", "mot_de_passe", "secret", "token"):
        if forbidden_key in raw:
            raise ValueError(
                f"{context}.postgresql contient un champ interdit ({forbidden_key!r}) : "
                "aucun secret ne doit jamais être écrit dans ce fichier."
            )

    return PostgreSQLProfile(
        host=host.strip(), port=port, database=database.strip(),
        username=username.strip(), credential_key=credential_key.strip(),
    )


def _parse_engine_config(raw: Any, *, context: str) -> DbEngineConfig:
    if not isinstance(raw, dict):
        raise ValueError(f"{context} doit être un objet JSON.")

    backend = raw.get("backend")
    if backend not in _VALID_BACKENDS:
        raise ValueError(f"{context}.backend invalide : {backend!r} (valeurs autorisées : {sorted(_VALID_BACKENDS)}).")

    postgresql_raw = raw.get("postgresql")
    if backend == "postgresql":
        postgresql = _parse_postgresql_profile(postgresql_raw, context=context)
    else:
        if postgresql_raw is not None:
            raise ValueError(f"{context}.postgresql doit être absent/null lorsque backend='sqlite'.")
        postgresql = None

    return DbEngineConfig(backend=backend, postgresql=postgresql)


def _parse_db_config_file(raw: Any) -> DbConfigFile:
    if not isinstance(raw, dict):
        raise ValueError("Le fichier de configuration doit contenir un objet JSON.")

    version = raw.get("version")
    if version != DB_CONFIG_FILE_VERSION:
        raise ValueError(
            f"Version de fichier non prise en charge : {version!r} "
            f"(seule la version {DB_CONFIG_FILE_VERSION} est comprise par cette version de l'application)."
        )

    active_raw = raw.get("active")
    if active_raw is None:
        raise ValueError("Le champ 'active' est requis.")
    active = _parse_engine_config(active_raw, context="active")

    pending_raw = raw.get("pending")
    pending = _parse_engine_config(pending_raw, context="pending") if pending_raw is not None else None

    return DbConfigFile(version=version, active=active, pending=pending)


def load_db_config_file(path: Path) -> DbConfigFile:
    """Lit le fichier de configuration externe. Ne lève jamais : tout
    problème (absence, JSON invalide, version inconnue, champ invalide)
    est journalisé puis traité comme une absence de fichier — repli
    systématique sur SQLite (voir docstring de module)."""
    if not path.exists():
        return _default_sqlite_config()

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Fichier de configuration illisible (%s) : %s — repli sur SQLite.", path, exc)
        return _default_sqlite_config()

    try:
        raw_json = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("Fichier de configuration JSON invalide (%s) : %s — repli sur SQLite.", path, exc)
        return _default_sqlite_config()

    try:
        return _parse_db_config_file(raw_json)
    except ValueError as exc:
        logger.warning("Fichier de configuration incohérent (%s) : %s — repli sur SQLite.", path, exc)
        return _default_sqlite_config()


def write_db_config_file_atomic(path: Path, config: DbConfigFile) -> None:
    """Écrit le fichier de façon atomique : jamais de fichier partiellement
    écrit visible par un lecteur concurrent (y compris ce même processus à
    un démarrage suivant après un arrêt brutal). Écrit dans un fichier
    temporaire du même répertoire puis ``os.replace`` (atomique sur le même
    volume, aussi bien sous Windows que sous Linux/macOS)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    fd, tmp_path_str = tempfile.mkstemp(dir=str(path.parent), prefix=f".{DB_CONFIG_FILENAME}.", suffix=".tmp")
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def set_pending_config(path: Path, new_pending: Optional[DbEngineConfig]) -> DbConfigFile:
    """Enregistre (ou, si ``new_pending`` est ``None``, annule) une
    configuration en attente — ne modifie jamais ``active``. Utilisé par le
    futur service d'administration (préparer une configuration / annuler la
    configuration en attente)."""
    current = load_db_config_file(path)
    updated = DbConfigFile(version=current.version, active=current.active, pending=new_pending)
    write_db_config_file_atomic(path, updated)
    return updated


def promote_pending_to_active(path: Path) -> DbConfigFile:
    """Fait passer ``pending`` à ``active`` si une configuration en attente
    existe — à appeler une seule fois, au tout début du démarrage, avant
    toute résolution de ``Settings``/moteur SQLAlchemy pour ce processus
    (jamais en cours de session : voir docstring de module). Sans effet si
    aucune configuration n'est en attente."""
    current = load_db_config_file(path)
    if current.pending is None:
        return current
    promoted = DbConfigFile(version=current.version, active=current.pending, pending=None)
    write_db_config_file_atomic(path, promoted)
    return promoted
