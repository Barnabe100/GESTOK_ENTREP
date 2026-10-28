"""Tests de ``app.views.database_unreachable_dialog.DatabaseUnreachableDialog``
(phase accès réseau/déconnexion auto/permissions Consultant, point 1).

Même principe que ``tests/test_database_setup_wizard.py`` : les boutons
sont cliqués directement sur une instance construite avec ``qtbot``, jamais
via ``exec()`` (qui bloquerait)."""
from __future__ import annotations

import dataclasses
from typing import Optional

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.config.db_config_store import default_db_config_path, load_db_config_file
from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.utils.exceptions import ConfigurationError
from app.views.database_unreachable_dialog import (
    GENERIC_UNREACHABLE_MESSAGE,
    DatabaseUnreachableDialog,
    startup_failure_message,
)


class _FakeVault:
    """Même double de test que ``tests/test_database_setup_wizard.py`` —
    jamais un mécanisme utilisé par le code de production."""

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
    monkeypatch.setattr("app.services.database_admin.database_admin_service.get_credential_vault", lambda: vault)
    return vault


@pytest.fixture()
def postgresql_settings(test_settings: Settings) -> Settings:
    """La configuration active au moment de l'échec (ce dialogue n'est
    construit par ``app.main`` que dans ce cas, voir
    ``_recover_from_startup_failure``) — jamais de connexion réelle
    requise pour la seule construction du dialogue."""
    return dataclasses.replace(
        test_settings,
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host="old-server.example.com", port=5432, database="stockmanager", username="smuser",
        ),
    )


# -- startup_failure_message : jamais de trace technique brute, jamais de secret -----


def test_app_error_message_is_shown_directly() -> None:
    assert startup_failure_message(ConfigurationError("Message métier déjà sûr.")) == "Message métier déjà sûr."


def test_non_app_error_falls_back_to_the_generic_message() -> None:
    raw_exc = RuntimeError(
        "connection to server at \"10.0.0.5\" port 5432 failed: "
        "password authentication failed for user \"smuser\" — mot-de-passe-secret"
    )
    message = startup_failure_message(raw_exc)
    assert message == GENERIC_UNREACHABLE_MESSAGE
    assert "mot-de-passe-secret" not in message
    assert "10.0.0.5" not in message


# -- pré-remplissage : jamais le mot de passe --------------------------------------


def test_dialog_is_prefilled_with_the_active_postgresql_params_but_never_a_password(
    postgresql_settings: Settings, qtbot
) -> None:
    dialog = DatabaseUnreachableDialog(postgresql_settings, ConfigurationError("Connexion impossible."))
    qtbot.addWidget(dialog)

    assert dialog.postgresql_radio.isChecked() is True
    assert dialog.host_edit.text() == "old-server.example.com"
    assert dialog.port_spin.value() == 5432
    assert dialog.database_edit.text() == "stockmanager"
    assert dialog.username_edit.text() == "smuser"
    assert dialog.password_edit.text() == ""
    assert dialog.error_label.text() == "Connexion impossible."


# -- bouton Quitter : renonce, n'écrit rien ------------------------------------------


def test_quit_button_rejects_and_writes_nothing(postgresql_settings: Settings, qtbot) -> None:
    dialog = DatabaseUnreachableDialog(postgresql_settings, ConfigurationError("Connexion impossible."))
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.quit_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not default_db_config_path(postgresql_settings.data_dir).exists()


# -- correction PostgreSQL : enregistrée directement comme ACTIVE (jamais pending) ---


def test_retry_with_corrected_postgresql_params_writes_them_as_active_immediately(
    postgresql_settings: Settings, qtbot, fake_vault
) -> None:
    dialog = DatabaseUnreachableDialog(postgresql_settings, ConfigurationError("Connexion impossible."))
    qtbot.addWidget(dialog)
    dialog.host_edit.setText("nouveau-serveur.example.com")
    dialog.port_spin.setValue(5555)
    dialog.database_edit.setText("stockmanager_prod")
    dialog.username_edit.setText("smuser2")
    dialog.password_edit.setText("s3cret-value")

    qtbot.mouseClick(dialog.retry_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    config_file = load_db_config_file(default_db_config_path(postgresql_settings.data_dir))
    # Jamais seulement "pending" + redémarrage requis : contrairement à
    # DatabaseSetupWizard, la correction est appliquée immédiatement.
    assert config_file.pending is None
    assert config_file.active.backend == "postgresql"
    assert config_file.active.postgresql.host == "nouveau-serveur.example.com"
    assert config_file.active.postgresql.port == 5555
    assert "s3cret-value" in fake_vault.store.values()


def test_switching_to_sqlite_writes_it_as_active_immediately(
    postgresql_settings: Settings, qtbot, fake_vault
) -> None:
    dialog = DatabaseUnreachableDialog(postgresql_settings, ConfigurationError("Connexion impossible."))
    qtbot.addWidget(dialog)
    dialog.sqlite_radio.setChecked(True)

    qtbot.mouseClick(dialog.retry_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    config_file = load_db_config_file(default_db_config_path(postgresql_settings.data_dir))
    assert config_file.pending is None
    assert config_file.active.backend == "sqlite"


def test_retry_with_invalid_params_shows_the_error_and_never_closes_the_dialog(
    postgresql_settings: Settings, qtbot, fake_vault
) -> None:
    dialog = DatabaseUnreachableDialog(postgresql_settings, ConfigurationError("Connexion impossible."))
    qtbot.addWidget(dialog)
    dialog.host_edit.setText("")  # hôte manquant : refusé par _validate_postgresql_fields

    qtbot.mouseClick(dialog.retry_button, Qt.MouseButton.LeftButton)

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "obligatoire" in dialog.status_label.text().lower()
    assert not default_db_config_path(postgresql_settings.data_dir).exists()
