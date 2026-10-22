"""Lot D.5 : assistant de première configuration — voir
``app.views.database_setup_wizard`` et les fonctions ``_is_first_run``/
``maybe_show_first_run_wizard`` de ``app.main``.

Ce dialogue s'exécute avant toute authentification (voir sa docstring de
module) : ces tests ne passent jamais par ``login_as``/un utilisateur
connecté, exactement comme en conditions réelles."""
from __future__ import annotations

import os
from typing import Optional

import pytest
from PySide6.QtWidgets import QDialog

import app.main as main_module
from app.config.db_config_store import default_db_config_path, load_db_config_file
from app.config.settings import Settings
from app.utils.exceptions import CredentialVaultUnavailableError
from app.views.database_setup_wizard import DatabaseSetupWizard

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")


class _FakeVault:
    """Même principe que dans tests/test_database_admin_service.py : un
    double de test en mémoire, jamais un mécanisme utilisé par le code de
    production (qui refuse explicitement hors Windows, voir
    tests/test_credential_vault.py)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get_password(self, profile_id: str) -> Optional[str]:
        return self.store.get(profile_id)

    def set_password(self, profile_id: str, password: str) -> None:
        self.store[profile_id] = password

    def delete_password(self, profile_id: str) -> None:
        self.store.pop(profile_id, None)


@pytest.fixture()
def fake_vault(monkeypatch: pytest.MonkeyPatch) -> _FakeVault:
    vault = _FakeVault()
    monkeypatch.setattr("app.views.database_setup_wizard.get_credential_vault", lambda: vault)
    monkeypatch.setattr("app.services.database_admin.database_admin_service.get_credential_vault", lambda: vault)
    return vault


# -- _is_first_run -------------------------------------------------------------------


def test_is_first_run_true_for_a_genuinely_fresh_machine(test_settings: Settings) -> None:
    assert main_module._is_first_run(test_settings) is True


def test_is_first_run_false_when_config_file_already_exists(test_settings: Settings) -> None:
    from app.config.db_config_store import DB_CONFIG_FILE_VERSION, DbConfigFile, DbEngineConfig, write_db_config_file_atomic

    write_db_config_file_atomic(
        default_db_config_path(test_settings.data_dir),
        DbConfigFile(version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite")),
    )
    assert main_module._is_first_run(test_settings) is False


def test_is_first_run_false_when_sqlite_db_file_already_exists(test_settings: Settings) -> None:
    """Non-régression explicite : une installation SQLite déjà en place
    (fichier .db déjà créé par une version antérieure à ce lot, jamais de
    fichier de configuration externe) ne doit jamais se voir proposer
    l'assistant."""
    test_settings.ensure_directories()
    test_settings.db_path.write_bytes(b"sqlite-db-simule")
    assert main_module._is_first_run(test_settings) is False


def test_is_first_run_false_for_scripted_postgresql_deployment(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config.settings import Settings as SettingsCls

    monkeypatch.setenv("STOCKMANAGER_TEST_PG_FORCE", "1")  # no-op, juste pour lisibilité
    settings = SettingsCls(
        environment="test", db_path=tmp_path / "unused.db", log_dir=tmp_path / "logs",
        log_level="DEBUG", default_currency="XOF", db_backend="postgresql",
    )
    assert main_module._is_first_run(settings) is False


# -- maybe_show_first_run_wizard : n'affiche le dialogue que si nécessaire ------------


def test_wizard_not_shown_when_not_first_run(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_settings.ensure_directories()
    test_settings.db_path.write_bytes(b"sqlite-db-simule")

    def _fail_if_called(*_a, **_k):
        raise AssertionError("DatabaseSetupWizard ne doit pas être instancié hors premier lancement.")

    monkeypatch.setattr(main_module, "DatabaseSetupWizard", _fail_if_called)
    monkeypatch.setattr(main_module, "get_settings", lambda: test_settings)

    main_module.maybe_show_first_run_wizard()  # ne lève pas AssertionError : confirme l'absence d'appel.


def test_wizard_shown_when_first_run(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch, qapp
) -> None:
    called = []
    monkeypatch.setattr(main_module, "get_settings", lambda: test_settings)

    class _RecordingDialog:
        def __init__(self, settings):
            called.append(settings)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(main_module, "DatabaseSetupWizard", _RecordingDialog)

    main_module.maybe_show_first_run_wizard()

    assert called == [test_settings]


# -- DatabaseSetupWizard : comportement de l'interface --------------------------------


def test_sqlite_selected_by_default(test_settings: Settings, qtbot) -> None:
    dialog = DatabaseSetupWizard(test_settings)
    qtbot.addWidget(dialog)
    assert dialog.sqlite_radio.isChecked() is True
    assert dialog.postgresql_group.isEnabled() is False


def test_finishing_with_sqlite_writes_nothing(test_settings: Settings, qtbot) -> None:
    dialog = DatabaseSetupWizard(test_settings)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.finish_button, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not default_db_config_path(test_settings.data_dir).exists()


def test_later_button_rejects_and_writes_nothing(test_settings: Settings, qtbot) -> None:
    from PySide6.QtCore import Qt

    dialog = DatabaseSetupWizard(test_settings)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.later_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not default_db_config_path(test_settings.data_dir).exists()


def test_selecting_postgresql_without_real_vault_reverts_to_sqlite(test_settings: Settings, qtbot) -> None:
    """Sur cette machine (pas de Windows Credential Manager réel), choisir
    PostgreSQL doit être explicitement refusé — jamais un repli silencieux
    vers un autre stockage (voir app.security.credential_vault)."""
    dialog = DatabaseSetupWizard(test_settings)
    qtbot.addWidget(dialog)

    dialog.postgresql_radio.setChecked(True)

    assert dialog.sqlite_radio.isChecked() is True
    assert dialog.postgresql_group.isEnabled() is False
    assert "PostgreSQL indisponible" in dialog.status_label.text()


def test_selecting_postgresql_with_available_vault_enables_fields(
    test_settings: Settings, qtbot, fake_vault
) -> None:
    dialog = DatabaseSetupWizard(test_settings)
    qtbot.addWidget(dialog)

    dialog.postgresql_radio.setChecked(True)

    assert dialog.postgresql_group.isEnabled() is True


def test_finishing_with_postgresql_writes_pending_shows_restart_notice(
    test_settings: Settings, qtbot, fake_vault
) -> None:
    from PySide6.QtCore import Qt

    dialog = DatabaseSetupWizard(test_settings)
    qtbot.addWidget(dialog)
    dialog.postgresql_radio.setChecked(True)
    dialog.host_edit.setText("pg.example.com")
    dialog.port_spin.setValue(5432)
    dialog.database_edit.setText("stockmanager")
    dialog.username_edit.setText("smuser")
    dialog.password_edit.setText("s3cret-value")

    qtbot.mouseClick(dialog.finish_button, Qt.MouseButton.LeftButton)

    assert "démarrage" in dialog.status_label.text().lower()
    assert "s3cret-value" not in dialog.status_label.text()

    config_file = load_db_config_file(default_db_config_path(test_settings.data_dir))
    assert config_file.active.backend == "sqlite"  # jamais modifié dans cette session.
    assert config_file.pending is not None
    assert config_file.pending.backend == "postgresql"
    assert config_file.pending.postgresql.host == "pg.example.com"
    assert "s3cret-value" in fake_vault.store.values()

    # La boîte de dialogue reste ouverte (l'utilisateur doit lire l'avis de
    # redémarrage) jusqu'à un nouveau clic sur le bouton, désormais "Fermer".
    assert dialog.result() != QDialog.DialogCode.Accepted
    qtbot.mouseClick(dialog.finish_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted


# -- test de connexion intégré au dialogue, contre un serveur PostgreSQL réel --------


@pytest.fixture()
def _skip_if_no_pg_server() -> None:
    if _PG_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )


def test_test_connection_button_succeeds_against_real_server(
    test_settings: Settings, qtbot, fake_vault, _skip_if_no_pg_server
) -> None:
    from PySide6.QtCore import Qt

    dialog = DatabaseSetupWizard(test_settings)
    qtbot.addWidget(dialog)
    dialog.postgresql_radio.setChecked(True)
    dialog.host_edit.setText(_PG_HOST)
    dialog.port_spin.setValue(_PG_PORT)
    dialog.database_edit.setText(_PG_DB)
    dialog.username_edit.setText(_PG_USER)
    dialog.password_edit.setText(_PG_PASSWORD)

    qtbot.mouseClick(dialog.test_connection_button, Qt.MouseButton.LeftButton)

    assert dialog.status_label.text() == "Connexion réussie."


def test_test_connection_button_fails_explicitly_with_wrong_password(
    test_settings: Settings, qtbot, fake_vault, _skip_if_no_pg_server
) -> None:
    from PySide6.QtCore import Qt

    dialog = DatabaseSetupWizard(test_settings)
    qtbot.addWidget(dialog)
    dialog.postgresql_radio.setChecked(True)
    dialog.host_edit.setText(_PG_HOST)
    dialog.port_spin.setValue(_PG_PORT)
    dialog.database_edit.setText(_PG_DB)
    dialog.username_edit.setText(_PG_USER)
    dialog.password_edit.setText("mot-de-passe-invalide")

    qtbot.mouseClick(dialog.test_connection_button, Qt.MouseButton.LeftButton)

    assert "Connexion impossible" in dialog.status_label.text()
    assert "mot-de-passe-invalide" not in dialog.status_label.text()
