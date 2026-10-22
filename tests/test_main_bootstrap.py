import logging
import sys

import pytest
from PySide6.QtWidgets import QMessageBox

import app.main as main_module
from app.config.db_config_store import (
    DB_CONFIG_FILE_VERSION,
    DbConfigFile,
    DbEngineConfig,
    PostgreSQLProfile,
    default_db_config_path,
    load_db_config_file,
    write_db_config_file_atomic,
)
from app.config.settings import Settings
from app.db.seed import INITIAL_ADMIN_USERNAME
from app.db.session import session_scope
from app.main import bootstrap
from app.models.rbac import Role
from app.models.user import User
from app.utils import error_handler
from app.utils.exceptions import ConfigurationError


def test_bootstrap_initializes_database_and_seeds_reference_data(test_settings: Settings) -> None:
    bootstrap()

    assert test_settings.db_path.exists()
    with session_scope(test_settings) as session:
        roles = {r.nom for r in session.query(Role).all()}
    assert roles == {"Administrateur", "Gestionnaire de stock", "Vendeur", "Consultation"}


def test_bootstrap_installs_global_exception_handler(test_settings: Settings) -> None:
    original_hook = sys.excepthook
    try:
        bootstrap()
        assert sys.excepthook is error_handler.handle_exception
    finally:
        sys.excepthook = original_hook


def test_bootstrap_configures_logging_with_settings_log_level(test_settings: Settings) -> None:
    bootstrap()
    logger = logging.getLogger("stockmanager")
    assert logger.level == logging.DEBUG  # STOCKMANAGER_LOG_LEVEL=DEBUG dans test_settings


def test_bootstrap_is_idempotent(test_settings: Settings) -> None:
    bootstrap()
    bootstrap()  # ne doit pas échouer ni dupliquer les données de référence

    with session_scope(test_settings) as session:
        assert session.query(Role).count() == 4


def test_bootstrap_creates_initial_admin_account(test_settings: Settings) -> None:
    bootstrap()

    with session_scope(test_settings) as session:
        admin = session.query(User).filter_by(username=INITIAL_ADMIN_USERNAME).one()
        assert [r.nom for r in admin.roles] == ["Administrateur"]
        assert admin.must_change_password is True


def test_bootstrap_does_not_recreate_admin_on_second_run(test_settings: Settings) -> None:
    bootstrap()
    bootstrap()

    with session_scope(test_settings) as session:
        count = session.query(User).filter_by(username=INITIAL_ADMIN_USERNAME).count()
    assert count == 1


# == Lot D.4 : démarrage et gestion des erreurs =======================================
#
# ``apply_pending_db_config_if_any``/``_show_fatal_startup_error`` concentrent
# tout le comportement nouveau de ce lot (application d'une configuration en
# attente avant la résolution de ``Settings`` ; message d'erreur sûr, jamais
# une trace technique brute, lorsque le démarrage échoue). ``bootstrap()``
# lui-même reste couvert par les tests historiques ci-dessus, inchangés.


# -- apply_pending_db_config_if_any : jamais en cours de session, une seule fois ------


def test_noop_when_env_backend_is_set_even_with_a_pending_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(tmp_path / "stockmanager.db"))
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "sqlite")
    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(
        path,
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"),
            pending=DbEngineConfig(
                backend="postgresql",
                postgresql=PostgreSQLProfile(host="h", port=5432, database="d", username="u", credential_key="k"),
            ),
        ),
    )

    main_module.apply_pending_db_config_if_any()

    # Le fichier n'a pas été touché : le déploiement scripté (Lot A) ignore
    # toujours ce fichier.
    reloaded = load_db_config_file(path)
    assert reloaded.active.backend == "sqlite"
    assert reloaded.pending is not None


def test_promotes_pending_to_active_when_no_env_backend(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(tmp_path / "stockmanager.db"))
    monkeypatch.delenv("STOCKMANAGER_DB_BACKEND", raising=False)
    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(
        path,
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"),
            pending=DbEngineConfig(
                backend="postgresql",
                postgresql=PostgreSQLProfile(host="h", port=5432, database="d", username="u", credential_key="k"),
            ),
        ),
    )

    main_module.apply_pending_db_config_if_any()

    reloaded = load_db_config_file(path)
    assert reloaded.active.backend == "postgresql"
    assert reloaded.active.postgresql.host == "h"
    assert reloaded.pending is None


def test_noop_and_no_file_created_when_nothing_pending_and_no_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(tmp_path / "stockmanager.db"))
    monkeypatch.delenv("STOCKMANAGER_DB_BACKEND", raising=False)

    main_module.apply_pending_db_config_if_any()

    assert not default_db_config_path(tmp_path).exists()


# -- _show_fatal_startup_error : jamais de trace technique brute, jamais de secret ----


def test_app_error_message_shown_directly(monkeypatch: pytest.MonkeyPatch, qapp) -> None:
    captured: list[str] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: captured.append(self.text()) or QMessageBox.StandardButton.Ok)

    main_module._show_fatal_startup_error(ConfigurationError("Message métier déjà sûr."))

    assert captured == ["Message métier déjà sûr."]


def test_non_app_error_shows_generic_message_never_the_raw_exception(
    monkeypatch: pytest.MonkeyPatch, qapp
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: captured.append(self.text()) or QMessageBox.StandardButton.Ok)

    raw_exc = RuntimeError(
        "connection to server at \"pg.example.com\" (10.0.0.5), port 5432 failed: "
        "password authentication failed for user \"smuser\" — mot-de-passe-secret"
    )
    main_module._show_fatal_startup_error(raw_exc)

    assert captured == [main_module._GENERIC_STARTUP_FAILURE_MESSAGE]
    assert "mot-de-passe-secret" not in captured[0]
    assert "10.0.0.5" not in captured[0]
    assert "pg.example.com" not in captured[0]
