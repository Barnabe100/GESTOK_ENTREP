"""Page Dashboard (§10-12 du cahier des charges de cette phase) : rendu des
KPI, visibilité des accès rapides selon les permissions, actualisation.

Complété par le Lot D (UX) : présence du QScrollArea, messages "aucune
donnée" par section, et renommage du libellé KPI ventes -> chiffre
d'affaires. Complété par le Lot E-B.2 : QDateEdit obligatoires pour la
période (plus de saisie texte, donc plus de QMessageBox d'avertissement
sur une période invalide — ce cas n'existe plus)."""
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDateEdit, QScrollArea, QToolTip

from app.services.entries.entry_service import EntreeLigneInput
from app.services.exits.exit_service import SortieLigneInput
from app.services.inventory.inventory_service import InventaireLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.money import format_money
from app.views.pages.dashboard_page import DashboardPage


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


# -- Lot E-B.2 : QDateEdit obligatoires pour la période ----------------------------------


def test_period_fields_are_qdateedit_with_calendar_popup_and_format(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert isinstance(page.date_from_edit, QDateEdit)
    assert isinstance(page.date_to_edit, QDateEdit)
    for widget in (page.date_from_edit, page.date_to_edit):
        assert widget.calendarPopup() is True
        assert widget.displayFormat() == "yyyy-MM-dd"


def test_period_defaults_to_first_day_of_month_and_today(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    today = date.today()
    assert page.date_from_edit.date() == QDate(today.year, today.month, 1)
    assert page.date_to_edit.date() == QDate(today.year, today.month, today.day)


def test_read_period_returns_python_date_objects(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    period_from, period_to = page._read_period()

    assert isinstance(period_from, date)
    assert isinstance(period_to, date)
    today = date.today()
    assert period_from == today.replace(day=1)
    assert period_to == today


def test_changing_dates_is_reflected_by_read_period(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.date_from_edit.setDate(QDate(2026, 3, 1))
    page.date_to_edit.setDate(QDate(2026, 3, 17))

    period_from, period_to = page._read_period()

    assert period_from == date(2026, 3, 1)
    assert period_to == date(2026, 3, 17)


def test_changing_dates_and_refreshing_transmits_selected_period_to_service(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5"), stock_initial=Decimal("50")
    )
    # Une vente hors de la période par défaut (mois courant) : ne doit
    # apparaître dans le chiffre d'affaires qu'une fois la période élargie
    # pour l'inclure, preuve que la période sélectionnée est bien transmise
    # au service plutôt qu'une valeur figée.
    past_date = date(2020, 1, 15)
    sale = stack.sales.create_sale(past_date, [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    assert "300" not in page.kpi_sales_label.text()  # hors période par défaut (mois courant)

    page.date_from_edit.setDate(QDate(2020, 1, 1))
    page.date_to_edit.setDate(QDate(2020, 1, 31))
    page.refresh_button.click()

    assert "300" in page.kpi_sales_label.text()


def test_refresh_still_works_after_selecting_a_date_range(qtbot, login_as) -> None:
    """Non-régression : le Dashboard reste fonctionnel (aucun crash, aucun
    statut d'erreur) après une modification manuelle des deux dates."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.date_from_edit.setDate(QDate(2025, 6, 1))
    page.date_to_edit.setDate(QDate(2025, 6, 30))
    page.refresh_button.click()

    assert page.status_label.isHidden() is True


def test_dashboard_works_for_vendeur_role_with_selected_period(qtbot, login_as) -> None:
    """Non-régression des permissions (Lot D/§9 du Lot D) : un Vendeur sans
    REPORT_VIEW continue de voir un Dashboard partiel, y compris après
    changement de période."""
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.date_from_edit.setDate(QDate(2025, 1, 1))
    page.date_to_edit.setDate(QDate(2025, 12, 31))
    page.refresh_button.click()

    assert page.kpi_stock_value_label.text() == "—"  # section REPORT_VIEW toujours masquée


# -- Lot D.1 : KPI secondaires (déjà calculés, jusqu'ici non affichés) -----------------


def _setup_full_activity(stack):
    """Une entrée, une sortie, une vente et un inventaire validés
    aujourd'hui — même patron que
    test_dashboard_service.py::test_activity_kpis_counts_only_validated_documents."""
    category = stack.categories.create_category("Boissons")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("50")
    )
    today = date.today()

    entry = stack.entries.create_entry(
        supplier.id, today, [EntreeLigneInput(article.id, Decimal("10"), Decimal("10"))]
    )
    stack.entries.validate_entry(entry.id)

    exit_doc = stack.exits.create_exit(motif.id, today, [SortieLigneInput(article.id, Decimal("5"))])
    stack.exits.validate_exit(exit_doc.id)

    sale = stack.sales.create_sale(today, [VenteLigneInput(article.id, Decimal("2"), Decimal("15"))])
    stack.sales.validate_sale(sale.id)

    inventory = stack.inventory.create_inventory(today, [InventaireLigneInput(article.id, Decimal("100"))])
    stack.inventory.validate_inventory(inventory.id)

    return article


def test_secondary_kpi_cards_exist(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    for attr in (
        "kpi_stock_quantity_label", "kpi_entries_label", "kpi_exits_label",
        "kpi_sales_count_label", "kpi_inventories_label",
    ):
        assert hasattr(page, attr)


def test_secondary_kpi_stock_quantity_matches_service(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    from app.utils.quantity import format_quantity

    expected = format_quantity(stack.dashboard.get_stock_kpis().total_quantity)
    assert page.kpi_stock_quantity_label.text() == expected


def test_secondary_kpi_activity_counts_reflect_validated_documents(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_full_activity(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.kpi_entries_label.text() == "1"
    assert page.kpi_exits_label.text() == "1"
    assert page.kpi_sales_count_label.text() == "1"
    assert page.kpi_inventories_label.text() == "1"


def test_existing_sales_amount_kpi_unaffected_by_new_sales_count_kpi(qtbot, login_as) -> None:
    """Non-régression : le KPI existant « Chiffre d'affaires (période) »
    (montant) reste distinct du nouveau « Ventes (période) » (nombre)."""
    stack, _ = login_as("Administrateur")
    _setup_full_activity(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.kpi_sales_label.text() == format_money(Decimal("30.00"), page._currency_code)
    assert page.kpi_sales_count_label.text() == "1"


def test_secondary_kpi_cards_show_dash_without_report_view(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.kpi_stock_quantity_label.text() == "—"
    assert page.kpi_entries_label.text() == "—"
    assert page.kpi_exits_label.text() == "—"
    assert page.kpi_sales_count_label.text() == "—"
    assert page.kpi_inventories_label.text() == "—"


def test_secondary_kpi_cards_show_zero_with_no_activity_in_period(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.kpi_entries_label.text() == "0"
    assert page.kpi_exits_label.text() == "0"
    assert page.kpi_sales_count_label.text() == "0"
    assert page.kpi_inventories_label.text() == "0"


# -- Lot D.1 : tooltips natifs Qt Charts ------------------------------------------------


def test_sales_chart_tooltip_shows_exact_amount_on_hover(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_full_activity(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert len(page._sales_chart_points) == 1
    page._on_sales_bar_hovered(True, 0, None)

    point = page._sales_chart_points[0]
    expected = f"{point.label} : {format_money(point.amount, page._currency_code)}"
    assert QToolTip.text() == expected
    assert "FCFA" in QToolTip.text()  # XOF par défaut : vérifie le format monétaire


def test_sales_chart_tooltip_out_of_range_index_hides_without_crash(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_full_activity(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    page._on_sales_bar_hovered(True, 999, None)
    page._on_sales_bar_hovered(False, 0, None)


def test_movement_chart_tooltip_reuses_real_slice_label_on_hover(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_full_activity(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    series = page.movement_chart_view.chart().series()[0]
    slices = series.slices()
    assert slices  # au moins la VENTE générée par _setup_full_activity
    target_slice = slices[0]

    page._on_movement_slice_hovered(target_slice, True)

    assert QToolTip.text() == target_slice.label()
    page._on_movement_slice_hovered(target_slice, False)


def test_category_chart_tooltip_shows_exact_value_on_hover(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert len(page._category_chart_rows) == 1
    page._on_category_bar_hovered(True, 0, None)

    row = page._category_chart_rows[0]
    expected = f"{row.category_nom} : {format_money(row.valeur_stock, page._currency_code)}"
    assert QToolTip.text() == expected
    assert "FCFA" in QToolTip.text()


# -- Lot D.1 : rafraîchissement de la devise --------------------------------------------


def test_currency_defaults_to_xof(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert "FCFA" in page.kpi_stock_value_label.text()


def test_refresh_reloads_currency_and_updates_displayed_amounts(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    assert "FCFA" in page.kpi_stock_value_label.text()

    stack.parameters.update_config(nom="Ma Société", adresse=None, telephone=None, email=None, devise="EUR")
    page.refresh()

    assert "€" in page.kpi_stock_value_label.text()
    assert "FCFA" not in page.kpi_stock_value_label.text()
    assert page._currency_code == "EUR"
