"""Lot E (§E.3/E.4) : comportement de ``BackupsPage`` lorsque PostgreSQL est
le moteur actif — pendant PostgreSQL de ``tests/test_backups_page.py``
(SQLite, inchangé). Même convention de serveur de test réel que les autres
fichiers de ce lot (``STOCKMANAGER_TEST_PG_PASSWORD``, base
``stockmanager_test`` uniquement)."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.services.backups.backup_service import BackupService
from app.views.pages.backups_page import BackupsPage

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_TEST_USER_PASSWORD = "MotDePasse!23"


@pytest.fixture(autouse=True)
def _silence_message_boxes(monkeypatch: pytest.MonkeyPatch) -> list:
    captured: list[tuple[str, str]] = []
    monkeypatch.setattr(QMessageBox, "information", lambda self, title, text, *a, **k: captured.append(("information", text)))
    monkeypatch.setattr(QMessageBox, "warning", lambda self, title, text, *a, **k: captured.append(("warning", text)))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    return captured


@pytest.fixture()
def postgresql_backup_page_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    if _PG_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )
    password_env_var = f"__test_pg_backups_page_{uuid.uuid4().hex}__"
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

    from sqlalchemy import text

    username = f"test_pg_page_admin_{uuid.uuid4().hex[:8]}"
    with db_session_module.session_scope(settings) as session:
        seed_reference_data(session)
        session.execute(text("DELETE FROM parametres WHERE cle LIKE 'backup.%'"))
        role = session.query(Role).filter_by(nom="Administrateur").one()
        session.add(
            User(username=username, password_hash=hash_password(_TEST_USER_PASSWORD), role_id=role.id, roles=[role], actif=True)
        )

    auth_service = AuthService(settings)
    auth_service.login(username, _TEST_USER_PASSWORD)
    permission_service = PermissionService(auth_service)
    backup_service = BackupService(permission_service, settings=settings)

    destination = tmp_path / "backups"
    backup_service.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10,
    )

    yield backup_service, permission_service, destination
    db_session_module.reset_engine_cache()


def test_page_shows_postgresql_as_active_engine(qtbot, postgresql_backup_page_stack) -> None:
    backup_service, permission_service, _ = postgresql_backup_page_stack
    page = BackupsPage(backup_service, permission_service)
    qtbot.addWidget(page)

    assert page.active_engine_label.text() == "PostgreSQL"


def test_history_tags_postgresql_backup_with_correct_engine_column(qtbot, postgresql_backup_page_stack) -> None:
    backup_service, permission_service, _ = postgresql_backup_page_stack
    result = backup_service.create_manual_backup()
    assert result.success is True

    page = BackupsPage(backup_service, permission_service)
    qtbot.addWidget(page)

    assert page.history_table.rowCount() == 1
    assert page.history_table.item(0, 0).text() == "PostgreSQL"
    assert page.history_table.item(0, 2).text() == result.file_path.name


def test_restore_disabled_when_selected_backup_is_a_different_engine(
    qtbot, postgresql_backup_page_stack
) -> None:
    """§E.3 : jamais proposer la restauration d'une sauvegarde d'un moteur
    différent du moteur actif — ici, une ancienne sauvegarde SQLite
    retrouvée dans le même dossier alors que PostgreSQL est désormais actif."""
    backup_service, permission_service, destination = postgresql_backup_page_stack
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "stockmanager_backup_20260101_000000.db").write_bytes(b"ancienne sauvegarde sqlite")
    result = backup_service.create_manual_backup()
    assert result.success is True

    page = BackupsPage(backup_service, permission_service)
    qtbot.addWidget(page)

    assert page.history_table.rowCount() == 2
    rows_by_engine = {page.history_table.item(r, 0).text(): r for r in range(2)}

    page.history_table.selectRow(rows_by_engine["SQLite"])
    assert page.restore_button.isEnabled() is False

    page.history_table.selectRow(rows_by_engine["PostgreSQL"])
    assert page.restore_button.isEnabled() is True


def test_clicking_restore_on_mismatched_engine_warns_and_never_calls_the_service(
    qtbot, postgresql_backup_page_stack, monkeypatch: pytest.MonkeyPatch, _silence_message_boxes
) -> None:
    backup_service, permission_service, destination = postgresql_backup_page_stack
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "stockmanager_backup_20260101_000000.db").write_bytes(b"ancienne sauvegarde sqlite")

    page = BackupsPage(backup_service, permission_service)
    qtbot.addWidget(page)
    sqlite_row = next(r for r in range(page.history_table.rowCount()) if page.history_table.item(r, 0).text() == "SQLite")
    page.history_table.selectRow(sqlite_row)

    called = {"restore": False}
    monkeypatch.setattr(backup_service, "restore_backup", lambda *a, **k: called.__setitem__("restore", True))

    page._on_restore_clicked()

    assert called["restore"] is False
    assert any(kind == "warning" for kind, _ in _silence_message_boxes)


# -- identification de la cible de restauration (Lot E.7, §E.7.2) -------------------


def test_active_engine_banner_shows_host_port_and_database(qtbot, postgresql_backup_page_stack) -> None:
    backup_service, permission_service, _ = postgresql_backup_page_stack
    page = BackupsPage(backup_service, permission_service)
    qtbot.addWidget(page)

    target_text = page.active_target_label.text()
    assert _PG_HOST in target_text
    assert str(_PG_PORT) in target_text
    assert _PG_DB in target_text
    assert _PG_PASSWORD not in target_text


def test_restore_confirmation_mentions_the_target_database(
    qtbot, postgresql_backup_page_stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_service, permission_service, destination = postgresql_backup_page_stack
    result = backup_service.create_manual_backup()
    assert result.success is True

    page = BackupsPage(backup_service, permission_service)
    qtbot.addWidget(page)
    page.history_table.selectRow(0)

    captured_messages: list[str] = []

    def _fake_confirm(parent, title, message):
        captured_messages.append(message)
        return False  # n'effectue jamais réellement la restauration dans ce test.

    monkeypatch.setattr("app.views.pages.backups_page.confirm_action", _fake_confirm)

    page._on_restore_clicked()

    assert len(captured_messages) == 1
    assert _PG_HOST in captured_messages[0]
    assert _PG_DB in captured_messages[0]
    assert _PG_PASSWORD not in captured_messages[0]
