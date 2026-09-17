from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from app.services.entries.entry_service import EntreeLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.views.pages.reports_page import ReportsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.reports_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.reports_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> ReportsPage:
    return ReportsPage(
        stack.reports, stack.categories, stack.articles, stack.exit_reasons, stack.permissions
    )


def _make_article(stack, reference="ART-1", stock_initial=Decimal("50"), stock_min=Decimal("0")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), stock_min, stock_initial=stock_initial,
    )


def test_default_report_is_stock_state(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.report_combo.currentText() == "État du stock"
    assert page.table.rowCount() == 1


def test_stock_state_shows_valeur_stock_column(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, stock_initial=Decimal("10"))

    page = _build_page(stack)
    qtbot.addWidget(page)

    headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    assert "Valeur stock" in headers


def test_switching_to_low_stock_report_updates_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, reference="ART-LOW", stock_initial=Decimal("1"), stock_min=Decimal("10"))
    _make_article(stack, reference="ART-OK", stock_initial=Decimal("50"), stock_min=Decimal("10"))

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.report_combo.setCurrentText("Stock faible")

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert references == {"ART-LOW"}


def test_out_of_stock_report(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, reference="ART-ZERO", stock_initial=Decimal("0"))
    _make_article(stack, reference="ART-POS", stock_initial=Decimal("5"))

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.report_combo.setCurrentText("Ruptures")

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert references == {"ART-ZERO"}


def test_valorisation_report_shows_total_in_summary(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, stock_initial=Decimal("10"))

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.report_combo.setCurrentText("Valorisation")

    assert "Valeur totale" in page.summary_label.text()


def test_movements_report_lists_entries(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack, stock_initial=Decimal("0"))
    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))])
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.report_combo.setCurrentText("Mouvements")

    assert page.table.rowCount() == 1


def test_movements_report_filters_by_article(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article_1 = stack.articles.create_article(
        "ART-1", "A", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("10")
    )
    article_2 = stack.articles.create_article(
        "ART-2", "B", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("20")
    )

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.report_combo.setCurrentText("Mouvements")

    index = page.article_combo.findData(article_1.id)
    page.article_combo.setCurrentIndex(index)
    page.refresh()

    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "ART-1"


def test_entries_report_lists_and_filters_by_statut(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack)
    stack.entries.create_entry(supplier.id, date(2026, 1, 1), [])
    to_validate = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))])
    stack.entries.validate_entry(to_validate.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.report_combo.setCurrentText("Entrées")

    assert page.table.rowCount() == 2

    index = page.statut_combo.findText("Validée")
    page.statut_combo.setCurrentIndex(index)
    page.refresh()

    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == to_validate.numero


def test_sales_report_shows_historized_total(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.report_combo.setCurrentText("Ventes")

    assert page.table.rowCount() == 1
    assert "300" in page.table.item(0, 4).text()


def test_inventories_report_shows_ecart_counts(qtbot, login_as) -> None:
    from app.services.inventory.inventory_service import InventaireLigneInput

    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))
    stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.report_combo.setCurrentText("Inventaires")

    assert page.table.rowCount() == 1
    assert page.table.item(0, 6).text() == "1"  # écarts négatifs


def test_reset_filters_clears_search_and_refreshes(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, reference="ART-EAU")
    _make_article(stack, reference="ART-RIZ")

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("EAU")
    page.refresh()
    assert page.table.rowCount() == 1

    page._on_reset_filters_clicked()

    assert page.search_edit.text() == ""
    assert page.table.rowCount() == 2


def test_export_button_disabled_without_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.export_button.isEnabled() is False


def test_export_button_enabled_with_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.export_button.isEnabled() is True


def test_export_to_writes_csv_file(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, stock_initial=Decimal("10"))

    page = _build_page(stack)
    qtbot.addWidget(page)

    out_file = tmp_path / "export.csv"
    result = page._export_to(str(out_file))

    assert result is True
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8-sig")
    assert "Référence" in content


def test_reports_never_modify_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("42"))

    page = _build_page(stack)
    qtbot.addWidget(page)
    for report_name in ["État du stock", "Stock faible", "Ruptures", "Mouvements", "Entrées", "Sorties", "Ventes", "Inventaires", "Valorisation"]:
        page.report_combo.setCurrentText(report_name)

    assert stack.articles.get_article(article.id).stock_actuel == Decimal("42")
