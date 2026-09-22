"""Page Administration → Licence (§14)."""
import pytest
from PySide6.QtWidgets import QMessageBox

from app.services.licensing.activation_mode import ActivationMode
from app.views.pages.licenses_page import LicensesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.licenses_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.licenses_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> LicensesPage:
    return LicensesPage(stack.licenses, stack.activation, stack.permissions)


def test_status_reflects_active_full_access_test_license(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.state_label.text() == "Valide"
    assert page.edition_label.text() == "ENTREPRISE"
    assert page.license_id_label.text() == "TEST-FULL-ACCESS"
    assert page.max_users_label.text() == "9999"


def test_activate_button_disabled_without_license_activate_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.activate_button.isEnabled() is False


def test_activate_button_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.activate_button.isEnabled() is True


def test_activate_from_file_success_updates_status(qtbot, login_as, license_envelope_factory, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    envelope = license_envelope_factory(license_id="STK-UI-TEST", client="Client UI", edition="PROFESSIONAL")
    license_file = tmp_path / "licence.lic"
    license_file.write_text(envelope, encoding="utf-8")

    result = page._activate_from_file(str(license_file))

    assert result is True
    assert page.state_label.text() == "Valide"
    assert page.license_id_label.text() == "STK-UI-TEST"
    assert page.client_label.text() == "Client UI"


def test_activate_from_file_shows_error_on_invalid_license(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    bad_file = tmp_path / "licence_invalide.lic"
    bad_file.write_text("pas un fichier de licence valide", encoding="utf-8")

    result = page._activate_from_file(str(bad_file))

    assert result is False


def test_activate_from_file_missing_file_shows_error(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._activate_from_file(str(tmp_path / "introuvable.lic"))

    assert result is False


# -- mode d'activation (lot LOCAL/SERVER) ----------------------------------------------


def test_mode_defaults_to_local_in_ui(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.mode_combo.currentData() == ActivationMode.LOCAL
    assert page.mode_description_label.text() == "Activation hors ligne"


def test_selecting_server_mode_updates_description_and_persists(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    server_index = page.mode_combo.findData(ActivationMode.SERVER)
    page.mode_combo.setCurrentIndex(server_index)

    assert page.mode_description_label.text() == "Activation via serveur TechNova — Internet requis"
    assert stack.activation.get_mode() == ActivationMode.SERVER


def test_activate_from_file_in_server_mode_shows_explicit_refusal(
    qtbot, login_as, license_envelope_factory, tmp_path
) -> None:
    """En mode SERVER, sans serveur configuré, l'activation doit être
    refusée explicitement — jamais silencieusement réussie."""
    stack, _ = login_as("Administrateur")
    stack.activation.set_mode(ActivationMode.SERVER)
    page = _build_page(stack)
    qtbot.addWidget(page)

    envelope = license_envelope_factory(license_id="STK-SERVER-UI", client="Client Serveur")
    license_file = tmp_path / "licence.lic"
    license_file.write_text(envelope, encoding="utf-8")

    result = page._activate_from_file(str(license_file))

    assert result is False
    # Aucune activation ne doit avoir été enregistrée : la licence de test à
    # accès complet reste la licence courante, jamais STK-SERVER-UI.
    assert page.license_id_label.text() == "TEST-FULL-ACCESS"


def test_mode_selector_disabled_without_license_activate_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.mode_combo.isEnabled() is False
