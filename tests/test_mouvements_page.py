from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox, QTableWidget

from app.services.entries.entry_service import EntreeLigneInput
from app.views.pages.mouvements_page import MouvementsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.mouvements_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.mouvements_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> MouvementsPage:
    return MouvementsPage(stack.movements, stack.permissions)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("50")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def test_page_lists_movements_on_load(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, stock_initial=Decimal("10"))

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 1
    assert "1 mouvement" in page.summary_label.text()


def test_columns_include_required_fields(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    for expected in [
        "Date/heure", "Article", "Type", "Quantité", "Stock avant", "Stock après",
        "Référence opération", "Utilisateur",
    ]:
        assert expected in headers


def test_reference_operation_column_shows_entry_numero(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack, stock_initial=Decimal("0"))
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    references = {page.table.item(row, 6).text() for row in range(page.table.rowCount())}
    assert entry.numero in references


def test_type_filter_narrows_results(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack, stock_initial=Decimal("0"))
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    index = page.type_filter_combo.findText("Entrée")
    assert index != -1
    page.type_filter_combo.setCurrentIndex(index)
    page.refresh()
    assert page.table.rowCount() == 1

    index_sortie = page.type_filter_combo.findText("Sortie")
    page.type_filter_combo.setCurrentIndex(index_sortie)
    page.refresh()
    assert page.table.rowCount() == 0


def test_search_filters_by_article_reference(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Cat")
    stack.articles.create_article(
        "ART-ALPHA", "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("5"),
    )
    stack.articles.create_article(
        "ART-BETA", "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("5"),
    )

    page = _build_page(stack)
    qtbot.addWidget(page)
    assert page.table.rowCount() == 2

    page.search_edit.setText("ALPHA")
    page.refresh()

    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "ART-ALPHA"


def test_reset_filters_clears_search_and_reloads(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Cat")
    stack.articles.create_article(
        "ART-ALPHA", "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("5"),
    )
    stack.articles.create_article(
        "ART-BETA", "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("5"),
    )

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("ALPHA")
    page.refresh()
    assert page.table.rowCount() == 1

    page._on_reset_filters_clicked()

    assert page.search_edit.text() == ""
    assert page.table.rowCount() == 2


def test_page_has_no_edit_or_delete_controls(qtbot, login_as) -> None:
    """Les mouvements ne doivent pas être modifiables directement (§1) :
    aucune action de modification/suppression sur cette page."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert not hasattr(page, "edit_button")
    assert not hasattr(page, "delete_button")
    assert page.table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers


def test_consultation_role_can_view_movements(qtbot, login_as) -> None:
    stack, _ = login_as("Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0
