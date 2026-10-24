"""Initialisation du schéma de base de données via Alembic.

En développement comme en production, le schéma est toujours amené à jour
par les migrations Alembic (jamais par un ``create_all`` direct), afin que
les mises à jour ultérieures de l'application puissent faire évoluer le
schéma sans perte de données chez les clients déjà installés.
"""
from __future__ import annotations

from typing import Optional

from alembic import command
from alembic.config import Config

from app.config import Settings, get_settings
from app.utils.logging_config import get_logger
from app.utils.runtime_paths import app_root

logger = get_logger("db.init")

PROJECT_ROOT = app_root()
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_PATH = PROJECT_ROOT / "migrations"


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    # Lot B : pour PostgreSQL, sqlalchemy_database_uri est un objet URL (Lot
    # A, masquage du mot de passe dans son propre repr/str) — Config exige
    # une chaîne. render_as_string(hide_password=False) restitue le mot de
    # passe réel (indispensable pour se connecter), jamais affiché ni
    # journalisé ici : seule la valeur transmise à Alembic en dépend.
    uri = settings.sqlalchemy_database_uri
    uri_str = uri if isinstance(uri, str) else uri.render_as_string(hide_password=False)
    # Correctif : alembic.config.Config stocke ses options dans un
    # configparser.ConfigParser, dont l'interpolation par défaut
    # (BasicInterpolation) traite tout « % » isolé comme le début d'une
    # référence — un mot de passe PostgreSQL contenant un caractère spécial
    # percent-encodé par render_as_string (ex. « %40 », « %21 ») y lève
    # ValueError: invalid interpolation syntax dès cet appel. Doubler
    # chaque « % » (« %% ») le restitue tel quel à la lecture (configparser
    # décode « %% » -> « % » dans son before_get) : jamais une altération du
    # mot de passe ni de l'URL utilisée par SQLAlchemy lui-même (ci-dessus,
    # `uri`/`uri_str`), qui ne voit jamais cette version échappée — seule la
    # valeur transmise à ``Config`` en dépend.
    config.set_main_option("sqlalchemy.url", uri_str.replace("%", "%%"))
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
