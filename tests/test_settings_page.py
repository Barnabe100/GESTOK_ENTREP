from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from app.views.pages.settings_page import SettingsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.settings_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.settings_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> SettingsPage:
    return SettingsPage(stack.parameters, stack.permissions)


def _make_test_image(path: Path, width: int = 20, height: int = 20) -> None:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(path))


def test_form_prefilled_with_current_config(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.update_config(
        nom="Ma Société", adresse="12 rue X", telephone="0102030405", email="a@b.com", devise="EUR"
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.nom_edit.text() == "Ma Société"
    assert page.adresse_edit.text() == "12 rue X"
    assert page.telephone_edit.text() == "0102030405"
    assert page.email_edit.text() == "a@b.com"
    assert page.devise_combo.currentText() == "EUR"


def test_default_currency_is_preselected_when_unconfigured(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.devise_combo.currentText() == "XOF"


def test_save_profile_persists_form_values(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.nom_edit.setText("Nouvelle Société")
    page.adresse_edit.setText("Nouvelle adresse")
    page.telephone_edit.setText("0102030405")
    page.email_edit.setText("contact@societe.com")
    page.devise_combo.setCurrentText("USD")

    result = page._save_profile()

    assert result is True
    config = stack.parameters.get_config()
    assert config.nom == "Nouvelle Société"
    assert config.devise == "USD"


def test_save_profile_shows_warning_on_invalid_email(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.nom_edit.setText("Société")
    page.email_edit.setText("pas-un-email")

    result = page._save_profile()

    assert result is False


def test_choose_logo_updates_preview_and_persists(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    logo_file = tmp_path / "logo.png"
    _make_test_image(logo_file)

    result = page._set_logo_from_file(str(logo_file))

    assert result is True
    assert not page.logo_preview_label.pixmap().isNull()
    config = stack.parameters.get_config()
    assert config.logo_path is not None


def test_choose_logo_rejects_invalid_format(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    bad_file = tmp_path / "logo.gif"
    bad_file.write_bytes(b"not a real image")

    result = page._set_logo_from_file(str(bad_file))

    assert result is False
    assert stack.parameters.get_config().logo_path is None


def test_clear_logo_removes_preview(qtbot, login_as, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    logo_file = tmp_path / "logo.png"
    _make_test_image(logo_file)
    page._set_logo_from_file(str(logo_file))
    assert stack.parameters.get_config().logo_path is not None

    monkeypatch.setattr("app.views.pages.settings_page.confirm_action", lambda *a, **k: True)
    result = page._clear_logo()

    assert result is True
    assert stack.parameters.get_config().logo_path is None


def test_non_admin_role_sees_disabled_form(qtbot, login_as) -> None:
    stack, _ = login_as("Consultation")

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.nom_edit.isEnabled() is False
    assert page.save_profile_button.isEnabled() is False
    assert page.choose_logo_button.isEnabled() is False
