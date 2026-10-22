"""Lot D.1 : persistance locale (hors base de données) du choix de moteur
actif/en attente — voir ``app.config.db_config_store``.

Aucun de ces tests ne nécessite de serveur PostgreSQL ni de coffre
d'identifiants : ce module ne porte jamais de secret (voir
``PostgreSQLProfile`` — pas de champ mot de passe)."""
from __future__ import annotations

import json
import os

import pytest

from app.config.db_config_store import (
    DB_CONFIG_FILE_VERSION,
    DbConfigFile,
    DbEngineConfig,
    PostgreSQLProfile,
    default_db_config_path,
    load_db_config_file,
    promote_pending_to_active,
    set_pending_config,
    write_db_config_file_atomic,
)


def _pg_profile(suffix: str = "") -> PostgreSQLProfile:
    return PostgreSQLProfile(
        host=f"pg-host{suffix}", port=5432, database=f"stockmanager{suffix}",
        username=f"smuser{suffix}", credential_key=f"profile-{suffix or '1'}",
    )


# -- fichier absent/corrompu/incompatible : repli systématique sur SQLite -------------


def test_missing_file_defaults_to_sqlite_active_no_pending(tmp_path) -> None:
    config = load_db_config_file(default_db_config_path(tmp_path))
    assert config.active.backend == "sqlite"
    assert config.active.postgresql is None
    assert config.pending is None
    assert config.version == DB_CONFIG_FILE_VERSION


def test_invalid_json_defaults_to_sqlite(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    path.write_text("{ceci n'est pas du JSON valide", encoding="utf-8")
    config = load_db_config_file(path)
    assert config.active.backend == "sqlite"


def test_unknown_version_defaults_to_sqlite(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    path.write_text(json.dumps({"version": 999, "active": {"backend": "sqlite"}}), encoding="utf-8")
    config = load_db_config_file(path)
    assert config.active.backend == "sqlite"


def test_missing_active_field_defaults_to_sqlite(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    path.write_text(json.dumps({"version": DB_CONFIG_FILE_VERSION}), encoding="utf-8")
    config = load_db_config_file(path)
    assert config.active.backend == "sqlite"


def test_postgresql_without_profile_defaults_to_sqlite(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    path.write_text(
        json.dumps({"version": DB_CONFIG_FILE_VERSION, "active": {"backend": "postgresql", "postgresql": None}}),
        encoding="utf-8",
    )
    config = load_db_config_file(path)
    assert config.active.backend == "sqlite"


@pytest.mark.parametrize("bad_port", [0, -1, 65536, 100000, "5432", 5432.0])
def test_invalid_port_defaults_to_sqlite(tmp_path, bad_port) -> None:
    path = default_db_config_path(tmp_path)
    path.write_text(
        json.dumps(
            {
                "version": DB_CONFIG_FILE_VERSION,
                "active": {
                    "backend": "postgresql",
                    "postgresql": {
                        "host": "h", "port": bad_port, "database": "d",
                        "username": "u", "credential_key": "k",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_db_config_file(path)
    assert config.active.backend == "sqlite"


@pytest.mark.parametrize("missing_field", ["host", "database", "username", "credential_key"])
def test_missing_postgresql_field_defaults_to_sqlite(tmp_path, missing_field) -> None:
    profile = {"host": "h", "port": 5432, "database": "d", "username": "u", "credential_key": "k"}
    del profile[missing_field]
    path = default_db_config_path(tmp_path)
    path.write_text(
        json.dumps({"version": DB_CONFIG_FILE_VERSION, "active": {"backend": "postgresql", "postgresql": profile}}),
        encoding="utf-8",
    )
    config = load_db_config_file(path)
    assert config.active.backend == "sqlite"


def test_password_field_present_is_rejected_never_loaded_as_valid(tmp_path) -> None:
    """Un fichier contenant un mot de passe (écrit à la main, ou produit par
    une version future incompatible) n'est jamais accepté comme une
    configuration PostgreSQL valide — repli sur SQLite, jamais une lecture
    silencieuse du secret."""
    path = default_db_config_path(tmp_path)
    path.write_text(
        json.dumps(
            {
                "version": DB_CONFIG_FILE_VERSION,
                "active": {
                    "backend": "postgresql",
                    "postgresql": {
                        "host": "h", "port": 5432, "database": "d", "username": "u",
                        "credential_key": "k", "password": "s3cret",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_db_config_file(path)
    assert config.active.backend == "sqlite"


def test_unreadable_file_defaults_to_sqlite(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    path.mkdir()  # un dossier à la place d'un fichier : provoque une IsADirectoryError à la lecture.
    config = load_db_config_file(path)
    assert config.active.backend == "sqlite"


# -- round-trip valide -------------------------------------------------------------------


def test_sqlite_config_round_trip(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    original = DbConfigFile(version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"), pending=None)
    write_db_config_file_atomic(path, original)
    loaded = load_db_config_file(path)
    assert loaded == original


def test_postgresql_config_round_trip(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    original = DbConfigFile(
        version=DB_CONFIG_FILE_VERSION,
        active=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("a")),
        pending=None,
    )
    write_db_config_file_atomic(path, original)
    loaded = load_db_config_file(path)
    assert loaded == original


def test_active_and_pending_round_trip(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    original = DbConfigFile(
        version=DB_CONFIG_FILE_VERSION,
        active=DbEngineConfig(backend="sqlite"),
        pending=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("b")),
    )
    write_db_config_file_atomic(path, original)
    loaded = load_db_config_file(path)
    assert loaded == original


# -- jamais de secret dans le fichier -----------------------------------------------------


def test_serialized_file_never_contains_a_secret_looking_field(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    config = DbConfigFile(
        version=DB_CONFIG_FILE_VERSION,
        active=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("c")),
        pending=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("d")),
    )
    write_db_config_file_atomic(path, config)
    raw_text = path.read_text(encoding="utf-8").lower()
    for forbidden in ("password", "mot_de_passe", "secret", "token"):
        assert forbidden not in raw_text


# -- écriture atomique --------------------------------------------------------------------


def test_atomic_write_leaves_no_temporary_file_behind(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(path, DbConfigFile(version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite")))
    remaining = list(tmp_path.iterdir())
    assert remaining == [path]


def test_atomic_write_creates_parent_directory(tmp_path) -> None:
    nested = tmp_path / "nested" / "data"
    path = default_db_config_path(nested)
    write_db_config_file_atomic(path, DbConfigFile(version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite")))
    assert path.exists()


# -- configuration en attente : préparer / annuler / appliquer ---------------------------


def test_set_pending_config_preserves_active(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(
        path, DbConfigFile(version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"))
    )

    updated = set_pending_config(
        path, DbEngineConfig(backend="postgresql", postgresql=_pg_profile("e"))
    )

    assert updated.active.backend == "sqlite"
    assert updated.pending is not None
    assert updated.pending.backend == "postgresql"
    reloaded = load_db_config_file(path)
    assert reloaded == updated


def test_cancel_pending_config_preserves_active_and_removes_pending(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(
        path,
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"),
            pending=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("f")),
        ),
    )

    updated = set_pending_config(path, None)

    assert updated.active.backend == "sqlite"
    assert updated.pending is None


def test_promote_pending_to_active_switches_and_clears_pending(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(
        path,
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"),
            pending=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("g")),
        ),
    )

    promoted = promote_pending_to_active(path)

    assert promoted.active.backend == "postgresql"
    assert promoted.active.postgresql == _pg_profile("g")
    assert promoted.pending is None
    reloaded = load_db_config_file(path)
    assert reloaded == promoted


def test_promote_without_pending_is_a_no_op(tmp_path) -> None:
    path = default_db_config_path(tmp_path)
    original = DbConfigFile(version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"), pending=None)
    write_db_config_file_atomic(path, original)

    promoted = promote_pending_to_active(path)

    assert promoted == original


def test_cancel_then_reload_never_touches_existing_sqlite_database_file(tmp_path) -> None:
    """Annuler une configuration en attente ne doit jamais toucher à un
    fichier de base SQLite existant (§4.3 du mandat : préservation
    intégrale des bases existantes)."""
    db_file = tmp_path / "stockmanager.db"
    db_file.write_bytes(b"contenu-sqlite-simule")

    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(
        path,
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"),
            pending=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("h")),
        ),
    )

    set_pending_config(path, None)

    assert db_file.read_bytes() == b"contenu-sqlite-simule"


# -- intégration avec Settings : priorité des variables d'environnement (Lot A) ---------


def test_settings_prefers_env_var_backend_over_json_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-régression explicite (Lot A) : si STOCKMANAGER_DB_BACKEND est
    défini, le fichier JSON (même présent, même PostgreSQL) est ignoré."""
    from app.config.settings import get_settings

    db_path = tmp_path / "stockmanager.db"
    write_db_config_file_atomic(
        default_db_config_path(tmp_path),
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION,
            active=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("i")),
        ),
    )

    monkeypatch.setenv("STOCKMANAGER_ENV", "test")
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(db_path))
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "sqlite")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.db_backend == "sqlite"
        assert settings.postgresql is None
    finally:
        get_settings.cache_clear()


def test_settings_reads_json_file_when_no_env_backend_set(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config.settings import get_settings

    db_path = tmp_path / "stockmanager.db"
    write_db_config_file_atomic(
        default_db_config_path(tmp_path),
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION,
            active=DbEngineConfig(backend="postgresql", postgresql=_pg_profile("j")),
        ),
    )

    monkeypatch.setenv("STOCKMANAGER_ENV", "test")
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(db_path))
    monkeypatch.delenv("STOCKMANAGER_DB_BACKEND", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.db_backend == "postgresql"
        assert settings.postgresql is not None
        assert settings.postgresql.host == "pg-hostj"
        assert settings.postgresql.credential_key == "profile-j"
    finally:
        get_settings.cache_clear()


def test_settings_defaults_to_sqlite_when_no_json_file_and_no_env_backend(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-régression explicite : une installation existante qui ne possède
    ni variable d'environnement ni fichier JSON (cas le plus courant, toute
    installation SQLite d'avant ce lot) continue de fonctionner exactement
    comme avant."""
    from app.config.settings import get_settings

    db_path = tmp_path / "stockmanager.db"
    monkeypatch.setenv("STOCKMANAGER_ENV", "test")
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(db_path))
    monkeypatch.delenv("STOCKMANAGER_DB_BACKEND", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.db_backend == "sqlite"
        assert settings.postgresql is None
        assert settings.sqlalchemy_database_uri == f"sqlite:///{db_path}"
    finally:
        get_settings.cache_clear()
