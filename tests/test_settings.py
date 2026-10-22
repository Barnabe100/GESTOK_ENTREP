"""Lot A (socle multi-moteur) : sélection SQLite/PostgreSQL, construction de
l'URL SQLAlchemy, validation des paramètres, et non-exposition du mot de
passe PostgreSQL — voir ``app/config/settings.py``.

Aucun de ces tests ne nécessite de serveur PostgreSQL réel : ils portent
uniquement sur la configuration et la construction d'URL (voir
``tests/test_db_session.py`` pour les tests de connexion réelle)."""
from pathlib import Path

import pytest

from app.config.settings import (
    DEFAULT_DB_BACKEND,
    DEFAULT_PASSWORD_ENV_VAR,
    DEFAULT_POSTGRESQL_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_POSTGRESQL_PORT,
    PostgreSQLConnectionConfig,
    Settings,
    get_settings,
)


def _make_sqlite_settings(**overrides) -> Settings:
    defaults = dict(
        environment="test", db_path=Path("/tmp/does-not-matter.db"),
        log_dir=Path("/tmp/logs"), log_level="INFO", default_currency="XOF",
    )
    defaults.update(overrides)
    return Settings(**defaults)


# -- sélection du moteur : SQLite reste le défaut, comportement préservé -------------


def test_default_db_backend_constant_is_sqlite() -> None:
    assert DEFAULT_DB_BACKEND == "sqlite"


def test_settings_default_db_backend_is_sqlite_when_unspecified() -> None:
    settings = _make_sqlite_settings()
    assert settings.db_backend == "sqlite"
    assert settings.postgresql is None


def test_sqlite_uri_unchanged_for_default_backend() -> None:
    settings = _make_sqlite_settings(db_path=Path("/tmp/stockmanager.db"))
    assert settings.sqlalchemy_database_uri == "sqlite:////tmp/stockmanager.db"


def test_load_settings_from_env_defaults_to_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Non-régression explicite : une installation existante qui ne définit
    aucune des nouvelles variables d'environnement garde exactement son
    comportement SQLite d'avant ce lot."""
    monkeypatch.setenv("STOCKMANAGER_ENV", "test")
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(tmp_path / "stockmanager.db"))
    monkeypatch.delenv("STOCKMANAGER_DB_BACKEND", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.db_backend == "sqlite"
    assert settings.postgresql is None
    assert settings.sqlalchemy_database_uri == f"sqlite:///{tmp_path / 'stockmanager.db'}"
    get_settings.cache_clear()


def test_load_settings_from_env_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "mongodb")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="STOCKMANAGER_DB_BACKEND"):
        get_settings()
    get_settings.cache_clear()


# -- PostgreSQL : construction d'URL --------------------------------------------------


def test_postgresql_uri_uses_psycopg3_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PASSWORD", "s3cret")
    settings = _make_sqlite_settings(
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host="db.example.com", port=5432, database="stockmanager", username="smuser",
        ),
    )

    url = settings.sqlalchemy_database_uri

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "db.example.com"
    assert url.port == 5432
    assert url.database == "stockmanager"
    assert url.username == "smuser"
    assert url.password == "s3cret"


def test_postgresql_uri_requires_config_when_backend_selected() -> None:
    settings = _make_sqlite_settings(db_backend="postgresql", postgresql=None)

    with pytest.raises(ValueError, match="postgresql"):
        _ = settings.sqlalchemy_database_uri


def test_postgresql_connection_config_defaults() -> None:
    config = PostgreSQLConnectionConfig(host="h", port=DEFAULT_POSTGRESQL_PORT, database="d", username="u")
    assert config.password_env_var == DEFAULT_PASSWORD_ENV_VAR
    assert config.connect_timeout_seconds == DEFAULT_POSTGRESQL_CONNECT_TIMEOUT_SECONDS


# -- mot de passe : jamais stocké, jamais exposé ---------------------------------------


def test_resolve_password_reads_from_configured_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOM_PG_PASSWORD", "topsecret")
    config = PostgreSQLConnectionConfig(
        host="h", port=5432, database="d", username="u", password_env_var="CUSTOM_PG_PASSWORD",
    )
    assert config.resolve_password() == "topsecret"


def test_resolve_password_raises_explicitly_when_env_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCKMANAGER_DB_PASSWORD", raising=False)
    config = PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u")

    with pytest.raises(ValueError, match="STOCKMANAGER_DB_PASSWORD"):
        config.resolve_password()


def test_resolve_password_rejects_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PASSWORD", "")
    config = PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u")

    with pytest.raises(ValueError):
        config.resolve_password()


def test_postgresql_connection_config_repr_never_contains_a_password() -> None:
    """``PostgreSQLConnectionConfig`` ne porte jamais le mot de passe lui-même
    (seulement le nom de la variable qui le contient) : sa représentation
    textuelle ne peut donc structurellement jamais l'exposer."""
    config = PostgreSQLConnectionConfig(
        host="h", port=5432, database="d", username="u", password_env_var="STOCKMANAGER_DB_PASSWORD",
    )
    assert "s3cret" not in repr(config)
    assert "password_env_var" in repr(config)


def test_settings_repr_never_contains_a_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PASSWORD", "s3cret-value")
    settings = _make_sqlite_settings(
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u"),
    )
    assert "s3cret-value" not in repr(settings)


def test_sqlalchemy_url_object_masks_password_in_str_and_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garantie supplémentaire offerte par l'objet ``URL`` de SQLAlchemy
    lui-même (voir docstring de ``Settings.sqlalchemy_database_uri``) : même
    affiché ou journalisé par erreur, le mot de passe n'apparaît jamais en
    clair dans ``str()``/``repr()``."""
    monkeypatch.setenv("STOCKMANAGER_DB_PASSWORD", "s3cret-value")
    settings = _make_sqlite_settings(
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u"),
    )
    url = settings.sqlalchemy_database_uri

    assert "s3cret-value" not in str(url)
    assert "s3cret-value" not in repr(url)
    assert url.password == "s3cret-value"  # la valeur réelle reste accessible pour create_engine


# -- validation des paramètres de connexion (déploiement scripté) --------------------


@pytest.mark.parametrize(
    "missing_var",
    ["STOCKMANAGER_DB_HOST", "STOCKMANAGER_DB_NAME", "STOCKMANAGER_DB_USER"],
)
def test_postgresql_backend_requires_mandatory_variables(
    monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "postgresql")
    monkeypatch.setenv("STOCKMANAGER_DB_HOST", "localhost")
    monkeypatch.setenv("STOCKMANAGER_DB_NAME", "stockmanager")
    monkeypatch.setenv("STOCKMANAGER_DB_USER", "smuser")
    monkeypatch.delenv(missing_var, raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="STOCKMANAGER_DB_BACKEND=postgresql"):
        get_settings()
    get_settings.cache_clear()


def test_postgresql_backend_loads_full_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "postgresql")
    monkeypatch.setenv("STOCKMANAGER_DB_HOST", "pg.example.com")
    monkeypatch.setenv("STOCKMANAGER_DB_PORT", "6543")
    monkeypatch.setenv("STOCKMANAGER_DB_NAME", "stockmanager")
    monkeypatch.setenv("STOCKMANAGER_DB_USER", "smuser")
    monkeypatch.setenv("STOCKMANAGER_DB_CONNECT_TIMEOUT", "20")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.db_backend == "postgresql"
    assert settings.postgresql is not None
    assert settings.postgresql.host == "pg.example.com"
    assert settings.postgresql.port == 6543
    assert settings.postgresql.database == "stockmanager"
    assert settings.postgresql.username == "smuser"
    assert settings.postgresql.connect_timeout_seconds == 20
    get_settings.cache_clear()


def test_postgresql_port_must_be_a_valid_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "postgresql")
    monkeypatch.setenv("STOCKMANAGER_DB_HOST", "localhost")
    monkeypatch.setenv("STOCKMANAGER_DB_NAME", "stockmanager")
    monkeypatch.setenv("STOCKMANAGER_DB_USER", "smuser")
    monkeypatch.setenv("STOCKMANAGER_DB_PORT", "not-a-port")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="STOCKMANAGER_DB_PORT"):
        get_settings()
    get_settings.cache_clear()


def test_postgresql_port_out_of_range_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "postgresql")
    monkeypatch.setenv("STOCKMANAGER_DB_HOST", "localhost")
    monkeypatch.setenv("STOCKMANAGER_DB_NAME", "stockmanager")
    monkeypatch.setenv("STOCKMANAGER_DB_USER", "smuser")
    monkeypatch.setenv("STOCKMANAGER_DB_PORT", "70000")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="STOCKMANAGER_DB_PORT"):
        get_settings()
    get_settings.cache_clear()


def test_postgresql_connect_timeout_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "postgresql")
    monkeypatch.setenv("STOCKMANAGER_DB_HOST", "localhost")
    monkeypatch.setenv("STOCKMANAGER_DB_NAME", "stockmanager")
    monkeypatch.setenv("STOCKMANAGER_DB_USER", "smuser")
    monkeypatch.setenv("STOCKMANAGER_DB_CONNECT_TIMEOUT", "0")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="STOCKMANAGER_DB_CONNECT_TIMEOUT"):
        get_settings()
    get_settings.cache_clear()


def test_postgresql_default_port_and_timeout_applied_when_unspecified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "postgresql")
    monkeypatch.setenv("STOCKMANAGER_DB_HOST", "localhost")
    monkeypatch.setenv("STOCKMANAGER_DB_NAME", "stockmanager")
    monkeypatch.setenv("STOCKMANAGER_DB_USER", "smuser")
    monkeypatch.delenv("STOCKMANAGER_DB_PORT", raising=False)
    monkeypatch.delenv("STOCKMANAGER_DB_CONNECT_TIMEOUT", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.postgresql.port == DEFAULT_POSTGRESQL_PORT
    assert settings.postgresql.connect_timeout_seconds == DEFAULT_POSTGRESQL_CONNECT_TIMEOUT_SECONDS
    get_settings.cache_clear()


def test_postgresql_custom_password_env_var_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "postgresql")
    monkeypatch.setenv("STOCKMANAGER_DB_HOST", "localhost")
    monkeypatch.setenv("STOCKMANAGER_DB_NAME", "stockmanager")
    monkeypatch.setenv("STOCKMANAGER_DB_USER", "smuser")
    monkeypatch.setenv("STOCKMANAGER_DB_PASSWORD_ENV_VAR", "MY_CUSTOM_PG_PASSWORD")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.postgresql.password_env_var == "MY_CUSTOM_PG_PASSWORD"
    get_settings.cache_clear()
