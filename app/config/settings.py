"""Configuration centralisée de l'application.

Toute lecture de variable d'environnement ou de chemin de fichier doit passer
par ce module. Aucun autre module ne doit lire ``os.environ`` directement.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

APP_DIR_NAME = "StockManager"
DEFAULT_DB_FILENAME = "stockmanager.db"
VALID_ENVIRONMENTS = {"development", "test", "production"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


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

    @property
    def data_dir(self) -> Path:
        return self.db_path.parent

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def sqlalchemy_database_uri(self) -> str:
        return f"sqlite:///{self.db_path}"

    def ensure_directories(self) -> None:
        """Crée les répertoires de données/logs si nécessaire (aucune donnée écrasée)."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


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

    return Settings(
        environment=environment,
        db_path=db_path,
        log_dir=log_dir,
        log_level=log_level,
        default_currency=default_currency,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne la configuration courante (mise en cache pour tout le processus).

    En test, appeler ``get_settings.cache_clear()`` après avoir modifié
    ``os.environ`` pour forcer un rechargement.
    """
    return _load_settings_from_env()
