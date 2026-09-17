"""Page Dashboard (§10-12 du cahier des charges de cette phase) : rendu des
KPI, visibilité des accès rapides selon les permissions, actualisation."""
from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from app.views.pages.dashboard_page import DashboardPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.dashboard_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack, on_navigate=None) -> DashboardPage:
    return DashboardPage(stack.dashboard, stack.permissions, on_navigate=on_navigate)


def _setup_catalog(stack):
    category = stack.categories.create_category("Boissons")
    stack.suppliers.create_supplier("Fournisseur A")
    stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5"), stock_initial=Decimal("2")
    )
    stack.articles.create_article(
        "ART-2", "Soda", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5"), stock_initial=Decimal("0")
    )


def test_kpi_cards_reflect_service_data(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.kpi_articles_label.text() == "2"
    assert page.kpi_low_stock_label.text() == "2"
    assert page.kpi_out_of_stock_label.text() == "1"


def test_low_stock_table_populated(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.low_stock_table.rowCount() == 2


def test_navigation_buttons_hidden_for_role_without_target_permission(qtbot, login_as) -> None:
    """Le Vendeur n'a ni STOCK_ENTRY_VIEW, ni STOCK_EXIT_VIEW, ni
    STOCK_MOVEMENT_VIEW, ni REPORT_VIEW (voir app/db/seed.py) : les boutons
    correspondants ne doivent pas être affichés (§12)."""
    stack, _ = login_as("Vendeur")

    page = _build_page(stack)
    qtbot.addWidget(page)

    # isHidden() reflète l'indicateur de visibilité propre au widget, sans
    # dépendre de l'affichage réel de la fenêtre (jamais appelée en test) —
    # contrairement à isVisible(), qui serait toujours False ici.
    assert page.navigation_buttons["Ventes"].isHidden() is False
    assert page.navigation_buttons["Entrées"].isHidden() is True
    assert page.navigation_buttons["Sorties"].isHidden() is True
    assert page.navigation_buttons["Mouvements"].isHidden() is True
    assert page.low_stock_alert_button.isHidden() is True
    assert page.out_of_stock_alert_button.isHidden() is True


def test_navigation_buttons_all_visible_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")

    page = _build_page(stack)
    qtbot.addWidget(page)

    for target in ("Ventes", "Entrées", "Sorties", "Mouvements"):
        assert page.navigation_buttons[target].isHidden() is False
    assert page.low_stock_alert_button.isHidden() is False
    assert page.out_of_stock_alert_button.isHidden() is False


def test_clicking_navigation_button_calls_on_navigate_callback(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    calls = []

    page = _build_page(stack, on_navigate=lambda module, preset: calls.append((module, preset)))
    qtbot.addWidget(page)

    page.navigation_buttons["Ventes"].click()

    assert calls == [("Ventes", None)]


def test_clicking_low_stock_alert_navigates_to_reports_with_preset(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    calls = []

    page = _build_page(stack, on_navigate=lambda module, preset: calls.append((module, preset)))
    qtbot.addWidget(page)

    page.low_stock_alert_button.click()

    assert calls == [("Rapports", "Stock faible")]


def test_refresh_button_reloads_kpis_after_change(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")

    page = _build_page(stack)
    qtbot.addWidget(page)
    assert page.kpi_articles_label.text() == "0"

    stack.articles.create_article("ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"))
    page.refresh_button.click()

    assert page.kpi_articles_label.text() == "1"


def test_invalid_period_shows_warning_and_does_not_crash(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    warnings = []
    monkeypatch.setattr(
        "app.views.pages.dashboard_page.QMessageBox.warning",
        lambda *a, **k: warnings.append(a) or QMessageBox.StandardButton.Ok,
    )

    page.date_from_edit.setText("pas une date")
    page.refresh_button.click()

    assert len(warnings) == 1


def test_dashboard_page_never_modifies_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("7")
    )
    before = stack.articles.get_article(article.id).stock_actuel

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.refresh_button.click()

    after = stack.articles.get_article(article.id).stock_actuel
    assert after == before


def test_status_message_shown_when_license_blocks_dashboard(qtbot, login_as, license_envelope_factory) -> None:
    from app.models.enums import EditionLicence
    from app.services.licensing.license_payload import DEFAULT_FEATURES_BY_EDITION

    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(
        edition="DEMO", features=sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.DEMO])
    )
    stack.licenses.activate_license(envelope)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.status_label.isHidden() is False
