"""Lot E (§E.2/E.3) : orchestration des sauvegardes/restaurations
PostgreSQL par :class:`BackupService` — pendant PostgreSQL de
``tests/test_backup_service.py`` (SQLite, inchangé).

Serveur PostgreSQL de test réel, même convention que les lots précédents :
si le serveur ou ``STOCKMANAGER_TEST_PG_PASSWORD`` ne sont pas disponibles,
ces tests sont ignorés proprement. ``login_as``/``make_stack``
(``tests/conftest.py``) sont câblés exclusivement sur une base SQLite
temporaire (``initialized_db``) : ce fichier construit donc sa propre pile
minimale (``AuthService``/``PermissionService``/``BackupService``,
exactement comme ``app/backup_cli.py``), rattachée à une ``Settings``
PostgreSQL réelle — jamais une base cliente, uniquement
``stockmanager_test``."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Callable

import psycopg
import pytest
from sqlalchemy import text

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.auth.auth_service import AuthService
from app.services.auth.current_user import CurrentUser
from app.services.auth.permission_service import PermissionService
from app.services.backups import postgresql_backup_engine as pg_backup_engine
from app.services.backups.backup_service import BackupService
from app.utils.exceptions import PermissionDeniedError, ValidationError

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_TEST_USER_PASSWORD = "MotDePasse!23"


@pytest.fixture()
def postgresql_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    if _PG_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )
    password_env_var = f"__test_pg_backup_service_{uuid.uuid4().hex}__"
    monkeypatch.setenv(password_env_var, _PG_PASSWORD)
    settings = Settings(
        environment="test", db_path=tmp_path / "unused-for-postgresql.db", log_dir=tmp_path / "logs",
        log_level="DEBUG", default_currency="XOF", db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER,
            password_env_var=password_env_var, connect_timeout_seconds=5,
        ),
    )
    db_session_module.reset_engine_cache()
    try:
        init_database(settings)
    except Exception as exc:  # noqa: BLE001 - serveur injoignable -> skip, jamais un échec.
        db_session_module.reset_engine_cache()
        pytest.skip(f"Serveur PostgreSQL de test non atteignable ({_PG_HOST}:{_PG_PORT}) : {exc}")

    with db_session_module.session_scope(settings) as session:
        seed_reference_data(session)
        # État propre pour chaque test : jamais une configuration de
        # sauvegarde laissée par un test précédent sur cette même base
        # partagée (voir docstring de module).
        session.execute(text("DELETE FROM parametres WHERE cle LIKE 'backup.%'"))

    yield settings
    db_session_module.reset_engine_cache()


@pytest.fixture()
def login_as_pg(postgresql_settings: Settings) -> Callable[[str], tuple]:
    """Pendant minimal de ``login_as`` (``tests/conftest.py``), rattaché à
    ``postgresql_settings`` plutôt qu'à la base SQLite temporaire —
    construit directement ``AuthService``/``PermissionService``/
    ``BackupService``, sans passer par ``build_service_registry`` (qui
    exige une licence active, superflue pour ces tests)."""
    counter = {"n": 0}

    def _login_as(role_name: str) -> tuple[BackupService, PermissionService, CurrentUser]:
        counter["n"] += 1
        username = f"test_pg_{role_name.lower().replace(' ', '_')}_{counter['n']}_{uuid.uuid4().hex[:6]}"
        with db_session_module.session_scope(postgresql_settings) as session:
            role = session.query(Role).filter_by(nom=role_name).one()
            session.add(
                User(
                    username=username, password_hash=hash_password(_TEST_USER_PASSWORD),
                    role_id=role.id, roles=[role], actif=True,
                )
            )
        auth_service = AuthService(postgresql_settings)
        current_user = auth_service.login(username, _TEST_USER_PASSWORD)
        permission_service = PermissionService(auth_service)
        backup_service = BackupService(permission_service, settings=postgresql_settings)
        return backup_service, permission_service, current_user

    return _login_as


def _connect(settings: Settings, password: str):
    pg = settings.postgresql
    return psycopg.connect(host=pg.host, port=pg.port, dbname=pg.database, user=pg.username, password=password)


# -- permissions --------------------------------------------------------------------


def test_non_admin_cannot_create_postgresql_backup(login_as_pg, tmp_path: Path) -> None:
    admin_backups, _, _ = login_as_pg("Administrateur")
    destination = tmp_path / "backups"
    admin_backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=5,
    )

    vendeur_backups, _, _ = login_as_pg("Vendeur")
    with pytest.raises(PermissionDeniedError):
        vendeur_backups.create_manual_backup()
    assert list(destination.glob("*.dump")) == []


def test_non_admin_cannot_restore_postgresql_backup(login_as_pg, tmp_path: Path) -> None:
    backups, _, _ = login_as_pg("Vendeur")
    fake = tmp_path / "stockmanager_backup_pg_20260101_000000.dump"
    fake.write_bytes(b"x")
    with pytest.raises(PermissionDeniedError):
        backups.restore_backup(fake)


# -- sauvegarde ------------------------------------------------------------------------


def test_admin_creates_postgresql_backup_successfully(login_as_pg, tmp_path: Path) -> None:
    backups, _, _ = login_as_pg("Administrateur")
    destination = tmp_path / "backups"
    backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=5)

    result = backups.create_manual_backup()

    assert result.success is True
    assert "PostgreSQL" in result.message
    assert result.file_path is not None
    assert result.file_path.suffix == ".dump"
    assert result.file_path.exists()


def test_list_backups_tags_postgresql_entries_correctly(login_as_pg, tmp_path: Path) -> None:
    backups, _, _ = login_as_pg("Administrateur")
    destination = tmp_path / "backups"
    backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=5)
    backups.create_manual_backup()

    entries = backups.list_backups()

    assert len(entries) == 1
    assert entries[0].engine == "postgresql"
    assert entries[0].info.path.suffix == ".dump"


def test_active_engine_reports_postgresql(login_as_pg) -> None:
    backups, _, _ = login_as_pg("Administrateur")
    assert backups.active_engine() == "postgresql"


def test_create_backup_fails_cleanly_when_tools_missing(
    login_as_pg, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backups, _, _ = login_as_pg("Administrateur")
    destination = tmp_path / "backups"
    backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=5)
    monkeypatch.setattr(pg_backup_engine.shutil, "which", lambda name: None)

    result = backups.create_manual_backup()

    assert result.success is False
    assert "introuvable" in result.message
    assert list(destination.glob("*")) == []


# -- restauration : opérations incohérentes avec le moteur actif -----------------------


def test_restoring_a_sqlite_file_while_postgresql_is_active_is_refused(login_as_pg, tmp_path: Path) -> None:
    backups, _, _ = login_as_pg("Administrateur")
    fake_sqlite_backup = tmp_path / "stockmanager_backup_20260101_000000.db"
    fake_sqlite_backup.write_bytes(b"not actually opened: rejected before that")

    with pytest.raises(ValidationError, match="sqlite"):
        backups.restore_backup(fake_sqlite_backup)


# -- restauration réelle : validation de bout en bout (§E.2.4) -------------------------


def test_real_restore_round_trip_through_the_service(login_as_pg, postgresql_settings: Settings, tmp_path: Path) -> None:
    """Jamais la seule création d'une archive : données représentatives
    modifiées, sauvegarde, dérive, restauration via le service complet
    (permissions + audit + mécanique), puis comparaison réelle."""
    backups, _, _ = login_as_pg("Administrateur")
    destination = tmp_path / "backups"
    backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=5)

    table = f"lot_e_service_scratch_{uuid.uuid4().hex[:8]}"
    with _connect(postgresql_settings, _PG_PASSWORD) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE TABLE {table} (id serial PRIMARY KEY, label text)")
            cur.execute(f"INSERT INTO {table} (label) VALUES ('etat_sauvegarde_service')")
        conn.commit()

    try:
        backup_result = backups.create_manual_backup()
        assert backup_result.success is True

        with _connect(postgresql_settings, _PG_PASSWORD) as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {table} SET label = 'derive_apres_sauvegarde'")
            conn.commit()

        restore_result = backups.restore_backup(backup_result.file_path)

        assert restore_result.success is True, restore_result.message
        assert restore_result.security_backup_path is not None
        assert restore_result.security_backup_path.exists()

        with _connect(postgresql_settings, _PG_PASSWORD) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT label FROM {table}")
                rows = [r[0] for r in cur.fetchall()]
        assert rows == ["etat_sauvegarde_service"]
    finally:
        with _connect(postgresql_settings, _PG_PASSWORD) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            conn.commit()


def test_restore_refused_on_schema_version_mismatch(
    login_as_pg, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isole la comparaison de version (voir le test de bout en bout
    ci-dessus pour la validation sans aucun monkeypatch) : simule une base
    active dont la version de schéma diffère de celle de l'archive, sans
    jamais modifier réellement la base partagée."""
    backups, _, _ = login_as_pg("Administrateur")
    destination = tmp_path / "backups"
    backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=5)
    backup_result = backups.create_manual_backup()
    assert backup_result.success is True

    monkeypatch.setattr(pg_backup_engine, "get_live_alembic_version", lambda target, password, **kw: "0001-version-differente")

    with pytest.raises(ValidationError, match="incompatible"):
        backups.restore_backup(backup_result.file_path)


def test_restore_of_corrupted_archive_never_touches_live_data(login_as_pg, tmp_path: Path, postgresql_settings: Settings) -> None:
    backups, _, _ = login_as_pg("Administrateur")
    destination = tmp_path / "backups"
    backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=5)

    bad = destination / "stockmanager_backup_pg_20260101_000000.dump"
    destination.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"pas une vraie archive pg_dump" * 20)

    with pytest.raises(ValidationError, match="invalide"):
        backups.restore_backup(bad)
