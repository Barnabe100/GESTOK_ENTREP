from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from app.models.enums import StatutInventaire
from app.services.inventory.inventory_service import InventaireLigneInput
from app.views.pages.inventories_page import InventoriesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.inventories_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.inventories_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> InventoriesPage:
    return InventoriesPage(stack.inventory, stack.articles, stack.permissions)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("100")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def test_inventories_page_lists_inventories(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "INV-000001" in numeros


def test_inventories_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.inventory.create_inventory(date(2026, 1, 1), [])
    stack.inventory.create_inventory(date(2026, 1, 1), [])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("INV-000001")

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {"INV-000001"}


def test_inventories_page_status_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.inventory.create_inventory(date(2026, 1, 1), [])
    to_validate = stack.inventory.create_inventory(
        date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))]
    )
    stack.inventory.validate_inventory(to_validate.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    index = page.status_filter_combo.findData(StatutInventaire.VALIDE)
    page.status_filter_combo.setCurrentIndex(index)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {to_validate.numero}


def test_table_shows_line_count_and_global_ecart(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article_1 = stack.articles.create_article(
        "ART-1", "A", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("100")
    )
    article_2 = stack.articles.create_article(
        "ART-2", "B", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("50")
    )
    stack.inventory.create_inventory(
        date(2026, 1, 1),
        [InventaireLigneInput(article_1.id, Decimal("97")), InventaireLigneInput(article_2.id, Decimal("55"))],
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.item(0, 3).text() == "2"
    assert page.table.item(0, 4).text() == "+2.000"  # -3 + 5


def test_add_button_enabled_for_gestionnaire_de_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True


def test_add_button_disabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is False


def test_no_cancel_button_exists(qtbot, login_as) -> None:
    """Aucun bouton d'annulation ne doit exister pour les inventaires (§3)."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert not hasattr(page, "cancel_button")


def test_action_buttons_reflect_selected_row_status_for_brouillon(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    draft = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == draft.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is True
    assert page.validate_button.isEnabled() is True


def test_action_buttons_reflect_selected_row_status_for_valide(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])
    stack.inventory.validate_inventory(inv.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == inv.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is False
    assert page.validate_button.isEnabled() is False


def test_submit_form_creates_draft_inventory_without_stock_impact(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": "2026-01-01",
        "lignes": [{"article_id": article.id, "article_label": "x", "stock_theorique": Decimal("100"), "stock_physique": Decimal("97")}],
    }

    result = page._submit_form(None, values)
    page.refresh()

    assert result is True
    created = stack.inventory.list_inventories()[0]
    assert created.statut == StatutInventaire.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("100")


def test_submit_form_rejects_invalid_date(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {"date": "pas une date", "lignes": []}

    result = page._submit_form(None, values)

    assert result is False


def test_submit_form_updates_existing_draft(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [])

    values = {
        "date": "2026-02-01",
        "lignes": [{"article_id": article.id, "article_label": "x", "stock_theorique": Decimal("100"), "stock_physique": Decimal("90")}],
    }

    result = page._submit_form(inv.id, values)

    assert result is True
    updated = stack.inventory.get_inventory(inv.id)
    assert len(updated.lignes) == 1


def test_load_edit_initial_returns_lines(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(inv.id)

    assert initial is not None
    assert len(initial["lignes"]) == 1
    assert initial["lignes"][0]["article_id"] == article.id


def test_load_edit_initial_returns_none_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._load_edit_initial(999999) is None


def test_load_inventory_for_detail_includes_movements_after_validation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])
    stack.inventory.validate_inventory(inv.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._load_inventory_for_detail(inv.id)

    assert result is not None
    loaded_inventory, movements = result
    assert loaded_inventory.numero == inv.numero
    assert len(movements) == 1


def test_validate_selected_updates_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(inv.id)

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("97")


def test_validate_selected_refused_for_already_validated_inventory(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])
    stack.inventory.validate_inventory(inv.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(inv.id)

    assert result is False


def test_validation_confirmation_message_shows_ecart_details(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])
    full = stack.inventory.get_inventory(inv.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    message = page._build_validation_confirmation_message(full)

    assert "théorique 100" in message
    assert "compté 97" in message
    assert "-3" in message


def test_confirmation_dialog_no_cancels_validate(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == inv.numero)
    page.table.selectRow(row)
    page._on_validate_clicked()

    assert stack.inventory.get_inventory(inv.id).statut == StatutInventaire.BROUILLON
