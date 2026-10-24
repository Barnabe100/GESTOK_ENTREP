from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False : sinon fileConfig désactive silencieusement
    # tout logger déjà créé par l'application (ex. "stockmanager.*") qui n'est
    # pas explicitement listé dans alembic.ini.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Si aucune URL n'a été injectée par le code appelant (app/db/init_db.py),
# on retombe sur la configuration applicative standard (usage CLI direct).
if not config.get_main_option("sqlalchemy.url"):
    from app.config import get_settings

    # Lot B : pour PostgreSQL, sqlalchemy_database_uri est un objet URL (Lot
    # A, masquage du mot de passe dans son propre repr/str) — Config exige
    # une chaîne. render_as_string(hide_password=False) restitue le mot de
    # passe réel (indispensable pour se connecter), jamais affiché ni
    # journalisé ici : seule la valeur transmise à Alembic en dépend.
    _uri = get_settings().sqlalchemy_database_uri
    _uri_str = _uri if isinstance(_uri, str) else _uri.render_as_string(hide_password=False)
    # Correctif : voir le commentaire équivalent dans
    # app/db/init_db.py::_alembic_config — configparser (utilisé par
    # alembic.config.Config) interprète tout « % » isolé comme une
    # interpolation ; un mot de passe PostgreSQL percent-encodé (« %40»,
    # « %21»...) y lève sinon ValueError: invalid interpolation syntax.
    # Doubler « % » le restitue tel quel à la lecture, sans jamais altérer
    # le mot de passe ni l'URL ci-dessus.
    config.set_main_option("sqlalchemy.url", _uri_str.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    # Lot B : render_as_batch n'est utile (et nécessaire) que pour SQLite,
    # dont l'ALTER TABLE limité impose de recréer la table ; PostgreSQL
    # applique les ALTER TABLE directement (voir op.batch_alter_table,
    # recreate='auto', dans les fichiers de migration). Ne change rien à
    # l'exécution des migrations existantes, seulement au futur
    # autogenerate si celui-ci est un jour pointé sur PostgreSQL.
    from sqlalchemy.engine import make_url

    render_as_batch = make_url(url).get_backend_name() == "sqlite"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=render_as_batch,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        render_as_batch = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=render_as_batch,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
