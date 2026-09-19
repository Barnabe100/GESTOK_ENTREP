"""Page Dashboard (§10-12 du cahier des charges de cette phase) : rendu des
KPI, visibilité des accès rapides selon les permissions, actualisation.

Complété par le Lot D (UX) : présence du QScrollArea, messages "aucune
donnée" par section, et renommage du libellé KPI ventes -> chiffre
d'affaires."""
from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox, QScrollArea

from app.services.entries.entry_service import EntreeLigneInput
from app.services.sales.sale_service import VenteLigneInput
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


# -- Lot D : QScrollArea ---------------------------------------------------------------


def test_dashboard_content_wrapped_in_scroll_area(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    scroll_areas = page.findChildren(QScrollArea)
    assert len(scroll_areas) == 1
    scroll_area = scroll_areas[0]
    assert scroll_area.widgetResizable() is True
    assert scroll_area.widget() is not None
    # Le contenu existant (cartes KPI, etc.) a bien été déplacé dans le
    # widget porté par le QScrollArea, pas perdu ni dupliqué.
    assert scroll_area.widget().isAncestorOf(page.kpi_articles_card)


def test_scroll_area_never_shows_horizontal_scrollbar_policy(qtbot, login_as) -> None:
    from PySide6.QtCore import Qt as QtCore_Qt

    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    scroll_area = page.findChildren(QScrollArea)[0]
    assert scroll_area.horizontalScrollBarPolicy() == QtCore_Qt.ScrollBarPolicy.ScrollBarAlwaysOff


# -- Lot D : messages "aucune donnée" ----------------------------------------------------


def test_sales_chart_shows_message_when_no_sales_in_period(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.sales_empty_label.isHidden() is False
    assert page.sales_chart_view.isHidden() is True
    assert page.sales_empty_label.text() == "Aucune vente sur cette période."


def test_sales_chart_message_disappears_when_sale_exists(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5"), stock_initial=Decimal("50")
    )
    sale = stack.sales.create_sale(date.today(), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.sales_empty_label.isHidden() is True
    assert page.sales_chart_view.isHidden() is False


def test_movement_chart_shows_message_when_no_movements(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.movement_empty_label.isHidden() is False
    assert page.movement_chart_view.isHidden() is True
    assert page.movement_empty_label.text() == "Aucun mouvement sur cette période."


def test_movement_chart_message_disappears_when_movement_exists(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5")
    )
    entry = stack.entries.create_entry(
        supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.movement_empty_label.isHidden() is True
    assert page.movement_chart_view.isHidden() is False


def test_category_chart_shows_message_when_no_catalog(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.category_value_empty_label.isHidden() is False
    assert page.category_value_chart_view.isHidden() is True
    assert page.category_value_empty_label.text() == "Aucune donnée de stock par catégorie."


def test_category_chart_message_disappears_when_article_exists(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5"), stock_initial=Decimal("2")
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.category_value_empty_label.isHidden() is True
    assert page.category_value_chart_view.isHidden() is False


def test_low_stock_table_shows_message_when_empty(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.low_stock_empty_label.isHidden() is False
    assert page.low_stock_table.isHidden() is True
    assert page.low_stock_empty_label.text() == "Aucun article en stock faible."


def test_low_stock_table_message_disappears_when_article_below_minimum(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.low_stock_empty_label.isHidden() is True
    assert page.low_stock_table.isHidden() is False


def test_recent_activity_shows_message_when_no_movements(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.recent_activity_empty_label.isHidden() is False
    assert page.recent_activity_table.isHidden() is True
    assert page.recent_activity_empty_label.text() == "Aucune activité récente."


def test_recent_activity_message_disappears_when_movement_exists(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5")
    )
    entry = stack.entries.create_entry(
        supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.recent_activity_empty_label.isHidden() is True
    assert page.recent_activity_table.isHidden() is False


# -- Lot D : libellé KPI chiffre d'affaires -----------------------------------------------


def test_kpi_sales_card_title_renamed_to_chiffre_affaires(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.kpi_sales_card.title() == "Chiffre d'affaires (période)"


def test_kpi_sales_value_unchanged_after_rename(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5"), stock_initial=Decimal("50")
    )
    sale = stack.sales.create_sale(date.today(), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert "300" in page.kpi_sales_label.text()  # 2 x 150 = 300, valeur/calcul inchangés
