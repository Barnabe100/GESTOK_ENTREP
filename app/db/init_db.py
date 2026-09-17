"""Initialisation du schéma de base de données via Alembic.

En développement comme en production, le schéma est toujours amené à jour
par les migrations Alembic (jamais par un ``create_all`` direct), afin que
les mises à jour ultérieures de l'application puissent faire évoluer le
schéma sans perte de données chez les clients déjà installés.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config

from app.config import Settings, get_settings
from app.utils.logging_config import get_logger

logger = get_logger("db.init")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_PATH = PROJECT_ROOT / "migrations"


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_uri)
    return config


def init_database(settings: Optional[Settings] = None) -> None:
    """Amène le schéma de la base au niveau de la dernière migration Alembic.

    Idempotent : sans effet si le schéma est déjà à jour. Crée le fichier de
    base de données et le répertoire parent s'ils n'existent pas encore.
    """
    settings = settings or get_settings()
    settings.ensure_directories()
    logger.info("Initialisation du schéma de base de données : %s", settings.db_path)
    config = _alembic_config(settings)
    command.upgrade(config, "head")
    logger.info("Schéma de base de données à jour.")
