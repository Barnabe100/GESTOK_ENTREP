from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from app.models.enums import ModeGestionArticle
from app.services.rentals.location_service import LocationLigneInput
from app.services.settings.company_settings_service import is_rental_module_enabled
from app.views.pages.settings_page import SettingsPage
from tests.ui_test_helpers import (
    assert_field_is_marked_required,
    assert_field_is_not_marked_required,
    assert_has_required_field_legend,
)


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.settings_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.settings_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> SettingsPage:
    return SettingsPage(stack.parameters, stack.permissions, stack.account_recovery, stack.rentals)


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


def test_required_fields_are_marked_required(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert_field_is_marked_required(page, page.nom_edit)
    assert_field_is_marked_required(page, page.devise_combo)


def test_optional_fields_are_not_marked_required(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert_field_is_not_marked_required(page, page.adresse_edit)
    assert_field_is_not_marked_required(page, page.telephone_edit)
    assert_field_is_not_marked_required(page, page.email_edit)


def test_page_shows_required_field_legend(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert_has_required_field_legend(page)


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
    assert page.receipt_footer_edit.isEnabled() is False
    assert page.save_receipt_footer_button.isEnabled() is False


# -- pied de reçu (Lot 21 — reçu unifié) ------------------------------------------------


def test_receipt_footer_field_prefilled_with_default_when_unconfigured(qtbot, login_as) -> None:
    from app.services.settings.company_settings_service import DEFAULT_RECEIPT_FOOTER

    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.receipt_footer_edit.text() == DEFAULT_RECEIPT_FOOTER


def test_receipt_footer_field_prefilled_with_configured_value(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_receipt_footer("Phrase personnalisée")

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.receipt_footer_edit.text() == "Phrase personnalisée"


def test_save_receipt_footer_persists_value(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.receipt_footer_edit.setText("Nouvelle phrase de fin")
    result = page._save_receipt_footer()

    assert result is True
    assert stack.parameters.get_config().recu_pied_de_page == "Nouvelle phrase de fin"


def test_save_receipt_footer_empty_disables_footer(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_receipt_footer("Phrase initiale")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.receipt_footer_edit.setText("")
    result = page._save_receipt_footer()

    assert result is True
    assert stack.parameters.get_config().recu_pied_de_page == ""


def test_save_receipt_footer_does_not_touch_sales_or_payments(qtbot, login_as) -> None:
    """§7 du lot : modifier la phrase de pied de reçu ne doit jamais
    affecter les ventes ou paiements déjà enregistrés."""
    from datetime import date
    from decimal import Decimal

    from app.services.sales.sale_service import VenteLigneInput

    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Cat-1")
    article = stack.articles.create_article(
        "ART-1", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("10"),
    )
    sale = stack.sales.create_sale(date(2026, 1, 15), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])
    validated = stack.sales.validate_sale(sale.id, paiement_initial=Decimal("150"))

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.receipt_footer_edit.setText("Nouvelle phrase")
    page._save_receipt_footer()

    reloaded = stack.sales.get_sale(validated.id)
    assert reloaded.montant_paye == Decimal("150")
    assert reloaded.statut.value == "VALIDEE"


# -- génération du code de récupération administrateur -----------------------------


def test_generate_recovery_code_button_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.generate_recovery_code_button.isEnabled() is True


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_generate_recovery_code_button_disabled_for_non_administrateur(qtbot, login_as, role_name) -> None:
    stack, _ = login_as(role_name)
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.generate_recovery_code_button.isEnabled() is False


def test_generate_recovery_code_returns_code_and_shows_dialog(qtbot, login_as, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    shown_codes = []
    monkeypatch.setattr(
        "app.views.pages.settings_page.RecoveryCodeDisplayDialog",
        lambda code, parent=None: shown_codes.append(code) or type("_FakeDialog", (), {"exec": lambda self: None})(),
    )

    code = page._generate_recovery_code()

    assert code is not None and len(code) >= 32
    assert shown_codes == [code]


# -- module Location (Lot 16) -------------------------------------------------------


def _make_rental_article(stack, reference="ART-LOC"):
    category = stack.categories.create_category(f"Cat-{reference}")
    article = stack.articles.create_article(
        reference, "Article de location", category.id, "unité",
        Decimal("1000"), Decimal("0"), Decimal("0"),
        stock_initial=Decimal("10"), tarif_location_jour=Decimal("500"),
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    return stack.articles.get_article(article.id)


def _make_draft_location(stack):
    """BROUILLON : ne réserve ni ne modifie jamais le stock (voir docstring
    de module de ``LocationService``) — ne doit donc jamais déclencher
    l'avertissement de désactivation (seul EN_COURS le doit)."""
    article = _make_rental_article(stack)
    client = stack.clients.create_client("Client Location")
    return stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("2"))])


def _make_confirmed_location(stack):
    """CONFIRMEE : toujours sans effet sur le stock (le départ n'a pas eu
    lieu) — ne doit pas non plus déclencher l'avertissement."""
    return stack.rentals.confirm_location(_make_draft_location(stack).id)


def _make_ongoing_location(stack):
    """EN_COURS : le seul statut où le départ a réellement décrémenté le
    stock (voir docstring de module de ``LocationService``) — c'est le
    seul cas où l'avertissement de désactivation doit se déclencher."""
    confirmed = _make_confirmed_location(stack)
    return stack.rentals.depart_location(confirmed.id, date(2026, 1, 1))


def test_modules_checkbox_reflects_real_value_at_opening(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_rental_module_enabled(False)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.locations_module_checkbox.isChecked() is False


def test_modules_checkbox_defaults_to_checked_when_key_absent(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.locations_module_checkbox.isChecked() is True


def test_save_modules_allowed_with_settings_update(qtbot, login_as, test_settings) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.locations_module_checkbox.setChecked(False)
    result = page._save_modules()

    assert result is True
    assert is_rental_module_enabled(test_settings) is False


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_modules_controls_disabled_without_settings_update(qtbot, login_as, role_name) -> None:
    stack, _ = login_as(role_name)
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.locations_module_checkbox.isEnabled() is False
    assert page.save_modules_button.isEnabled() is False


def test_warning_shown_when_deactivating_with_ongoing_locations(qtbot, login_as, monkeypatch, test_settings) -> None:
    stack, _ = login_as("Administrateur")
    _make_ongoing_location(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    confirm_calls = []
    monkeypatch.setattr(
        "app.views.pages.settings_page.confirm_action",
        lambda *a, **k: confirm_calls.append(1) or True,
    )

    page.locations_module_checkbox.setChecked(False)
    result = page._save_modules()

    assert confirm_calls == [1]
    assert result is True
    assert is_rental_module_enabled(test_settings) is False


def test_cancelling_warning_does_not_save_deactivation(qtbot, login_as, monkeypatch, test_settings) -> None:
    stack, _ = login_as("Administrateur")
    _make_ongoing_location(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr("app.views.pages.settings_page.confirm_action", lambda *a, **k: False)

    page.locations_module_checkbox.setChecked(False)
    result = page._save_modules()

    assert result is False
    assert is_rental_module_enabled(test_settings) is True


def test_no_warning_when_no_ongoing_locations(qtbot, login_as, monkeypatch, test_settings) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    confirm_calls = []
    monkeypatch.setattr(
        "app.views.pages.settings_page.confirm_action",
        lambda *a, **k: confirm_calls.append(1) or True,
    )

    page.locations_module_checkbox.setChecked(False)
    result = page._save_modules()

    assert confirm_calls == []
    assert result is True
    assert is_rental_module_enabled(test_settings) is False


@pytest.mark.parametrize("make_location", [_make_draft_location, _make_confirmed_location])
def test_no_warning_for_draft_or_confirmed_locations_only(qtbot, login_as, monkeypatch, test_settings, make_location) -> None:
    """Revue Lot 16, point A : seul EN_COURS déclenche l'avertissement — un
    BROUILLON ou une location CONFIRMEE (sans départ, donc sans aucun effet
    sur le stock) ne doit jamais le déclencher, conformément à la décision
    métier initiale (« locations encore en cours »)."""
    stack, _ = login_as("Administrateur")
    make_location(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    confirm_calls = []
    monkeypatch.setattr(
        "app.views.pages.settings_page.confirm_action",
        lambda *a, **k: confirm_calls.append(1) or True,
    )

    page.locations_module_checkbox.setChecked(False)
    result = page._save_modules()

    assert confirm_calls == []
    assert result is True
    assert is_rental_module_enabled(test_settings) is False


def test_no_warning_when_activating_module(qtbot, login_as, monkeypatch, test_settings) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_rental_module_enabled(False)
    _make_ongoing_location(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    confirm_calls = []
    monkeypatch.setattr(
        "app.views.pages.settings_page.confirm_action",
        lambda *a, **k: confirm_calls.append(1) or True,
    )

    page.locations_module_checkbox.setChecked(True)
    result = page._save_modules()

    assert confirm_calls == []
    assert result is True
    assert is_rental_module_enabled(test_settings) is True
