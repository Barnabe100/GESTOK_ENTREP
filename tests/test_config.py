from pathlib import Path

import pytest

from app.config.settings import Settings, get_settings


def test_settings_reads_db_path_override(test_settings: Settings) -> None:
    assert test_settings.environment == "test"
    assert test_settings.is_test is True
    assert test_settings.db_path.name == "test_stockmanager.db"


def test_settings_default_currency_is_xof(test_settings: Settings) -> None:
    assert test_settings.default_currency == "XOF"


def test_settings_sqlalchemy_uri_matches_db_path(test_settings: Settings) -> None:
    assert test_settings.sqlalchemy_database_uri == f"sqlite:///{test_settings.db_path}"


def test_settings_ensure_directories_creates_dirs(test_settings: Settings, tmp_path: Path) -> None:
    assert not test_settings.data_dir.exists() or test_settings.data_dir == tmp_path
    test_settings.ensure_directories()
    assert test_settings.data_dir.exists()
    assert test_settings.log_dir.exists()


def test_settings_invalid_environment_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_ENV", "not-a-real-environment")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()
    monkeypatch.delenv("STOCKMANAGER_ENV", raising=False)
    get_settings.cache_clear()


def test_settings_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_LOG_LEVEL", "NOT_A_LEVEL")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()
    monkeypatch.delenv("STOCKMANAGER_LOG_LEVEL", raising=False)
    get_settings.cache_clear()


def test_get_settings_is_cached(test_settings: Settings) -> None:
    assert get_settings() is test_settings
