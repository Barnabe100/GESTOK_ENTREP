"""Lot D.6 : écran d'administration de la base de données — voir
``app.views.pages.database_admin_page``.

Les contrôles de permission sont vérifiés côté service (déjà couvert par
``tests/test_database_admin_service.py``) : ces tests portent sur le
comportement propre à l'interface — affichage, désactivation des contrôles
pour un rôle sans ``DATABASE_CONFIG_UPDATE``, et qu'un contournement direct
du service (plutôt que du bouton) reste malgré tout refusé."""
from __future__ import annotations

from typing import Optional

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.utils.exceptions import PermissionDeniedError
from app.views.pages.database_admin_page import DatabaseAdminPage


class _FakeVault:
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


@pytest.fixture(autouse=True)
def _silence_message_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)


def test_admin_sees_active_sqlite_configuration(login_as, qtbot) -> None:
    stack, _ = login_as("Administrateur")
    page = DatabaseAdminPage(stack.database_admin, stack.permissions)
    qtbot.addWidget(page)
    assert page.active_label.text() == "SQLite"
    assert page.pending_label.text() == "Aucune configuration en attente."


def test_non_admin_update_controls_are_disabled(login_as, qtbot) -> None:
    stack, _ = login_as("Vendeur")
    page = DatabaseAdminPage(stack.database_admin, stack.permissions)
    qtbot.addWidget(page)
    assert page.sqlite_radio.isEnabled() is False
    assert page.postgresql_radio.isEnabled() is False
    assert page.test_connection_button.isEnabled() is False
    assert page.save_pending_button.isEnabled() is False
    assert page.cancel_pending_button.isEnabled() is False


def test_non_admin_cannot_bypass_disabled_button_by_calling_handler_directly(login_as, qtbot) -> None:
    """Vérifie que désactiver le bouton n'est pas la seule protection : un
    appel direct au gestionnaire (ce qu'un bouton activé par erreur
    provoquerait) est quand même refusé par le service lui-même."""
    stack, _ = login_as("Vendeur")
    page = DatabaseAdminPage(stack.database_admin, stack.permissions)
    qtbot.addWidget(page)

    with pytest.raises(PermissionDeniedError):
        stack.database_admin.prepare_sqlite_pending_config()


def test_preparing_postgresql_config_from_the_page_shows_pending_and_restart_notice(
    login_as, qtbot, fake_vault
) -> None:
    stack, _ = login_as("Administrateur")
    page = DatabaseAdminPage(stack.database_admin, stack.permissions)
    qtbot.addWidget(page)

    page.postgresql_radio.setChecked(True)
    page.host_edit.setText("pg.example.com")
    page.port_spin.setValue(5432)
    page.database_edit.setText("stockmanager")
    page.username_edit.setText("smuser")
    page.password_edit.setText("s3cret-value")

    qtbot.mouseClick(page.save_pending_button, Qt.MouseButton.LeftButton)

    assert "PostgreSQL" in page.pending_label.text()
    assert "pg.example.com" in page.pending_label.text()
    assert "s3cret-value" not in page.pending_label.text()
    assert page.active_label.text() == "SQLite"  # jamais modifié.


def test_cancel_pending_preserves_active_and_clears_pending_label(login_as, qtbot, fake_vault) -> None:
    stack, _ = login_as("Administrateur")
    stack.database_admin.prepare_postgresql_pending_config(
        host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret",
    )
    page = DatabaseAdminPage(stack.database_admin, stack.permissions)
    qtbot.addWidget(page)
    assert "PostgreSQL" in page.pending_label.text()

    qtbot.mouseClick(page.cancel_pending_button, Qt.MouseButton.LeftButton)

    assert page.pending_label.text() == "Aucune configuration en attente."
    assert page.active_label.text() == "SQLite"


def test_password_field_cleared_after_saving(login_as, qtbot, fake_vault) -> None:
    stack, _ = login_as("Administrateur")
    page = DatabaseAdminPage(stack.database_admin, stack.permissions)
    qtbot.addWidget(page)
    page.postgresql_radio.setChecked(True)
    page.host_edit.setText("pg.example.com")
    page.database_edit.setText("stockmanager")
    page.username_edit.setText("smuser")
    page.password_edit.setText("s3cret-value")

    qtbot.mouseClick(page.save_pending_button, Qt.MouseButton.LeftButton)

    assert page.password_edit.text() == ""
