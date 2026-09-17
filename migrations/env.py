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

    config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_database_uri)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
