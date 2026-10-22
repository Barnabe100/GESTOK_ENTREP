"""Configuration centralisée de l'application.

Toute lecture de variable d'environnement ou de chemin de fichier doit passer
par ce module. Aucun autre module ne doit lire ``os.environ`` directement.

Lot A (socle multi-moteur) : deux moteurs de base de données sont pris en
charge, un seul actif à la fois (``Settings.db_backend``) — SQLite reste la
valeur par défaut, pour ne jamais changer le comportement d'une installation
existante qui ne configure rien de nouveau. Aucune synchronisation entre les
deux moteurs n'est implémentée, ici ou ailleurs.

Sécurité des identifiants PostgreSQL (§4 du mandat de ce lot) :
:class:`PostgreSQLConnectionConfig` ne porte **jamais** le mot de passe —
seulement le nom de la variable d'environnement qui le contient
(``password_env_var``). Le mot de passe lui-même n'est donc jamais un champ
de ``Settings``, jamais sérialisable, jamais journalisé par ce module, et
résolu uniquement à l'instant de la connexion (voir
:meth:`PostgreSQLConnectionConfig.resolve_password`). C'est la seule
intégration fournie par ce lot (déploiement scripté/poste préconfiguré) ;
l'intégration au coffre d'identifiants du système d'exploitation (Windows
Credential Manager en priorité) est prévue pour le lot consacré à la
configuration utilisateur — non implémentée ici, voir la docstring de
``resolve_password`` pour le point d'extension prévu. Ne jamais remplacer
cette lacune par un stockage en clair : en l'absence de la variable
d'environnement, la connexion échoue explicitement.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

APP_DIR_NAME = "StockManager"
DEFAULT_DB_FILENAME = "stockmanager.db"
VALID_ENVIRONMENTS = {"development", "test", "production"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# Lot A : un seul moteur actif par instance, SQLite par défaut (voir
# docstring de module) — "postgresql" est le seul autre moteur pris en
# charge pour cette première livraison (décision produit validée : aucun
# autre moteur n'est prévu).
DEFAULT_DB_BACKEND = "sqlite"
VALID_DB_BACKENDS = {"sqlite", "postgresql"}

DEFAULT_POSTGRESQL_PORT = 5432
# Délai de connexion explicite (§3.B du mandat) : une valeur raisonnable
# pour un poste client attendant un serveur réseau potentiellement distant,
# sans bloquer indéfiniment si le serveur est inaccessible.
DEFAULT_POSTGRESQL_CONNECT_TIMEOUT_SECONDS = 10
DEFAULT_PASSWORD_ENV_VAR = "STOCKMANAGER_DB_PASSWORD"


@dataclass(frozen=True)
class PostgreSQLConnectionConfig:
    """Paramètres de connexion PostgreSQL — ne porte jamais le mot de passe
    (voir docstring de module). Portée Lot A : exploitable depuis un
    déploiement scripté (variables d'environnement) et prête à être réutilisée
    telle quelle par le futur assistant graphique/écran d'administration
    (lot dédié), qui construira une instance de cette même classe à partir
    de la saisie utilisateur plutôt que de l'environnement."""

    host: str
    port: int
    database: str
    username: str
    password_env_var: str = DEFAULT_PASSWORD_ENV_VAR
    connect_timeout_seconds: int = DEFAULT_POSTGRESQL_CONNECT_TIMEOUT_SECONDS
    # Lot D : lorsqu'une configuration provient du fichier externe
    # (app.config.db_config_store), le mot de passe est résolu via le coffre
    # d'identifiants du système (app.security.credential_vault) plutôt que
    # via une variable d'environnement — ``credential_key`` est l'identifiant
    # stable et non secret du profil, jamais le mot de passe lui-même.
    # ``None`` (valeur par défaut, comportement Lot A inchangé) : résolution
    # par variable d'environnement, comme avant ce lot.
    credential_key: Optional[str] = None

    def resolve_password(self) -> str:
        """Résout le mot de passe au moment de l'usage — jamais mis en cache,
        jamais stocké sur cette instance ni ailleurs.

        Deux sources possibles, jamais combinées ni basculées silencieusement
        entre elles : le coffre d'identifiants du système si
        ``credential_key`` est renseigné (Lot D, poste administré via
        l'assistant/l'écran d'administration), sinon la variable
        d'environnement ``password_env_var`` (Lot A, déploiement scripté/tests
        — comportement inchangé). Lève :class:`ValueError` si la source
        retenue ne fournit aucune valeur, plutôt que de se rabattre sur une
        valeur par défaut ou un stockage en clair — un échec explicite est
        toujours préférable à une connexion silencieusement non sécurisée."""
        if self.credential_key is not None:
            from app.security.credential_vault import get_credential_vault

            password = get_credential_vault().get_password(self.credential_key)
            if not password:
                raise ValueError(
                    "Mot de passe PostgreSQL introuvable dans le coffre d'identifiants "
                    f"pour le profil {self.credential_key!r}. Aucune valeur n'est stockée "
                    "en clair dans la configuration de l'application."
                )
            return password

        password = os.environ.get(self.password_env_var)
        if not password:
            raise ValueError(
                "Mot de passe PostgreSQL introuvable : définissez la variable "
                f"d'environnement {self.password_env_var!r}. Aucune valeur "
                "n'est stockée en clair dans la configuration de l'application."
            )
        return password


def _default_app_data_dir() -> Path:
    """Répertoire de données par système d'exploitation.

    Choisi pour ne jamais coïncider avec le répertoire de ressources embarqué
    par PyInstaller, afin qu'une mise à jour de l'exécutable ne puisse pas
    écraser la base de données de production.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / APP_DIR_NAME


@dataclass(frozen=True)
class Settings:
    environment: str
    db_path: Path
    log_dir: Path
    log_level: str
    default_currency: str
    # Lot A : SQLite par défaut, jamais rompu pour une installation
    # existante qui ne définit aucune des variables ci-dessous — voir
    # ``_load_settings_from_env``. ``db_path`` reste toujours significatif
    # (répertoire de données local : logs, branding, etc., voir
    # ``data_dir``) même lorsque ``db_backend == "postgresql"`` : ce n'est
    # pas uniquement l'emplacement du fichier SQLite.
    db_backend: str = DEFAULT_DB_BACKEND
    postgresql: Optional[PostgreSQLConnectionConfig] = None

    @property
    def data_dir(self) -> Path:
        return self.db_path.parent

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def sqlalchemy_database_uri(self) -> Union[str, "URL"]:
        """URL de connexion SQLAlchemy pour le moteur actif.

        SQLite : chaîne simple, inchangée (comportement préservé à
        l'identique pour toute installation existante).

        PostgreSQL : un objet :class:`sqlalchemy.engine.URL` (jamais une
        chaîne construite à la main) — ``create_engine`` accepte aussi bien
        une chaîne qu'une ``URL``, mais ``URL`` échappe correctement tout
        caractère spécial du mot de passe et, surtout, masque
        automatiquement le mot de passe dans son propre ``repr()``/``str()``
        (``***``) : un affichage ou une journalisation accidentelle de cette
        valeur ne peut donc jamais exposer le mot de passe en clair (§4 du
        mandat de ce lot)."""
        if self.db_backend == "postgresql":
            if self.postgresql is None:
                raise ValueError(
                    "db_backend='postgresql' mais aucune configuration de connexion "
                    "(Settings.postgresql) n'a été fournie."
                )
            from sqlalchemy.engine import URL

            pg = self.postgresql
            return URL.create(
                "postgresql+psycopg",
                username=pg.username,
                password=pg.resolve_password(),
                host=pg.host,
                port=pg.port,
                database=pg.database,
            )
        return f"sqlite:///{self.db_path}"

    def ensure_directories(self) -> None:
        """Crée les répertoires de données/logs si nécessaire (aucune donnée écrasée)."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def resolve_data_dir() -> Path:
    """Répertoire de données applicatif, résolu uniquement depuis
    l'environnement — jamais depuis ``Settings`` (qui n'existe pas encore
    à ce stade du démarrage, voir ``app.main.bootstrap``). Doit rester
    cohérent avec le calcul de ``db_path``/``data_dir`` fait par
    :func:`_load_settings_from_env` (même source : ``STOCKMANAGER_DB_PATH``
    ou le répertoire de données par défaut du système)."""
    db_path_override = os.environ.get("STOCKMANAGER_DB_PATH")
    if db_path_override:
        return Path(db_path_override).parent
    return _default_app_data_dir()


def _load_postgresql_config_from_env() -> PostgreSQLConnectionConfig:
    """Lit les paramètres de connexion PostgreSQL depuis l'environnement —
    déploiement scripté (§3.A du mandat de ce lot) ; le futur assistant
    graphique/écran d'administration construira cette même classe
    directement depuis la saisie utilisateur, sans passer par
    l'environnement. Jamais le mot de passe lui-même : voir
    ``PostgreSQLConnectionConfig.password_env_var``."""
    host = os.environ.get("STOCKMANAGER_DB_HOST", "").strip()
    if not host:
        raise ValueError(
            "STOCKMANAGER_DB_BACKEND=postgresql nécessite STOCKMANAGER_DB_HOST."
        )

    database = os.environ.get("STOCKMANAGER_DB_NAME", "").strip()
    if not database:
        raise ValueError(
            "STOCKMANAGER_DB_BACKEND=postgresql nécessite STOCKMANAGER_DB_NAME."
        )

    username = os.environ.get("STOCKMANAGER_DB_USER", "").strip()
    if not username:
        raise ValueError(
            "STOCKMANAGER_DB_BACKEND=postgresql nécessite STOCKMANAGER_DB_USER."
        )

    port_raw = os.environ.get("STOCKMANAGER_DB_PORT", str(DEFAULT_POSTGRESQL_PORT))
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"STOCKMANAGER_DB_PORT invalide : {port_raw!r} (entier attendu).") from exc
    if not (0 < port <= 65535):
        raise ValueError(f"STOCKMANAGER_DB_PORT hors plage valide (1-65535) : {port}.")

    password_env_var = os.environ.get("STOCKMANAGER_DB_PASSWORD_ENV_VAR", "").strip() or DEFAULT_PASSWORD_ENV_VAR

    timeout_raw = os.environ.get(
        "STOCKMANAGER_DB_CONNECT_TIMEOUT", str(DEFAULT_POSTGRESQL_CONNECT_TIMEOUT_SECONDS)
    )
    try:
        connect_timeout_seconds = int(timeout_raw)
    except ValueError as exc:
        raise ValueError(
            f"STOCKMANAGER_DB_CONNECT_TIMEOUT invalide : {timeout_raw!r} (entier attendu)."
        ) from exc
    if connect_timeout_seconds <= 0:
        raise ValueError(
            f"STOCKMANAGER_DB_CONNECT_TIMEOUT doit être strictement positif : {connect_timeout_seconds}."
        )

    return PostgreSQLConnectionConfig(
        host=host,
        port=port,
        database=database,
        username=username,
        password_env_var=password_env_var,
        connect_timeout_seconds=connect_timeout_seconds,
    )


def _load_settings_from_env() -> Settings:
    environment = os.environ.get("STOCKMANAGER_ENV", "development")
    if environment not in VALID_ENVIRONMENTS:
        raise ValueError(
            f"STOCKMANAGER_ENV invalide : {environment!r} "
            f"(valeurs autorisées : {sorted(VALID_ENVIRONMENTS)})"
        )

    db_path_override = os.environ.get("STOCKMANAGER_DB_PATH")
    if db_path_override:
        db_path = Path(db_path_override)
    else:
        db_path = _default_app_data_dir() / DEFAULT_DB_FILENAME

    # Les logs vivent toujours à côté de la base effective (respecte donc, lui
    # aussi, une éventuelle surcharge STOCKMANAGER_DB_PATH — important en test).
    log_dir = db_path.parent / "logs"

    log_level = os.environ.get("STOCKMANAGER_LOG_LEVEL", "INFO").upper()
    if log_level not in VALID_LOG_LEVELS:
        raise ValueError(
            f"STOCKMANAGER_LOG_LEVEL invalide : {log_level!r} "
            f"(valeurs autorisées : {sorted(VALID_LOG_LEVELS)})"
        )

    default_currency = os.environ.get("STOCKMANAGER_DEFAULT_CURRENCY", "XOF").upper()

    # Lot A (socle multi-moteur) : si STOCKMANAGER_DB_BACKEND est explicitement
    # défini (déploiement scripté/tests), il est prioritaire et autosuffisant
    # — comportement strictement inchangé par le Lot D.
    db_backend_env = os.environ.get("STOCKMANAGER_DB_BACKEND")
    if db_backend_env is not None:
        db_backend = db_backend_env.strip().lower()
        if db_backend not in VALID_DB_BACKENDS:
            raise ValueError(
                f"STOCKMANAGER_DB_BACKEND invalide : {db_backend!r} "
                f"(valeurs autorisées : {sorted(VALID_DB_BACKENDS)})"
            )
        postgresql_config = _load_postgresql_config_from_env() if db_backend == "postgresql" else None
    else:
        # Lot D : aucune variable scriptée définie — lit la configuration
        # externe (assistant/écran d'administration), SQLite si le fichier
        # est absent ou invalide (voir app.config.db_config_store, jamais
        # d'exception propagée par cette lecture).
        from app.config.db_config_store import default_db_config_path, load_db_config_file

        db_config_file = load_db_config_file(default_db_config_path(db_path.parent))
        active = db_config_file.active
        db_backend = active.backend
        if db_backend == "postgresql":
            # Garanti non None pour ce backend par load_db_config_file.
            profile = active.postgresql
            postgresql_config = PostgreSQLConnectionConfig(
                host=profile.host, port=profile.port, database=profile.database,
                username=profile.username, credential_key=profile.credential_key,
            )
        else:
            postgresql_config = None

    return Settings(
        environment=environment,
        db_path=db_path,
        log_dir=log_dir,
        log_level=log_level,
        default_currency=default_currency,
        db_backend=db_backend,
        postgresql=postgresql_config,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne la configuration courante (mise en cache pour tout le processus).

    En test, appeler ``get_settings.cache_clear()`` après avoir modifié
    ``os.environ`` pour forcer un rechargement.
    """
    return _load_settings_from_env()
