import os

# Doit être défini avant tout import de PySide6 (y compris via le plugin pytest-qt).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from typing import Iterator

import pytest

from app.config.settings import Settings, get_settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.db.seed import seed_reference_data


@pytest.fixture()
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Configuration isolée pointant vers une base SQLite temporaire par test."""
    db_path = tmp_path / "test_stockmanager.db"
    monkeypatch.setenv("STOCKMANAGER_ENV", "test")
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(db_path))
    monkeypatch.setenv("STOCKMANAGER_LOG_LEVEL", "DEBUG")

    get_settings.cache_clear()
    db_session_module.reset_engine_cache()

    yield get_settings()

    db_session_module.reset_engine_cache()
    get_settings.cache_clear()


@pytest.fixture()
def initialized_db(test_settings: Settings) -> Settings:
    """Base de test migrée (Alembic) et pré-remplie avec les données de référence."""
    init_database(test_settings)
    with db_session_module.session_scope(test_settings) as session:
        seed_reference_data(session)
    return test_settings
