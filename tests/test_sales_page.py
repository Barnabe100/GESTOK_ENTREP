from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from app.models.enums import StatutOperation
from app.services.sales.sale_service import VenteLigneInput
from app.views.pages.sales_page import SalesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.sales_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.sales_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> SalesPage:
    return SalesPage(stack.sales, stack.articles, stack.clients, stack.documents, stack.permissions)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("50")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def test_sales_page_lists_sales(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("10"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "VNT-000001" in numeros


def test_sales_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.sales.create_sale(date(2026, 1, 1), [])
    stack.sales.create_sale(date(2026, 1, 1), [])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("VNT-000001")

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {"VNT-000001"}


def test_sales_page_status_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.sales.create_sale(date(2026, 1, 1), [])
    to_validate = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(to_validate.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    index = page.status_filter_combo.findData(StatutOperation.VALIDEE)
    page.status_filter_combo.setCurrentIndex(index)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {to_validate.numero}


def test_add_button_enabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True


def test_add_button_disabled_for_gestionnaire_de_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is False


def test_action_buttons_reflect_selected_row_status_for_brouillon(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    draft = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == draft.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is True
    assert page.delete_button.isEnabled() is True
    assert page.validate_button.isEnabled() is True
    assert page.cancel_button.isEnabled() is False


def test_action_buttons_reflect_selected_row_status_for_validee(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is False
    assert page.delete_button.isEnabled() is False
    assert page.validate_button.isEnabled() is False
    assert page.cancel_button.isEnabled() is True


def test_submit_form_creates_draft_sale_without_stock_impact(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1),
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("10"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(None, values)
    page.refresh()

    assert result is True
    created = stack.sales.list_sales()[0]
    assert created.statut == StatutOperation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")


def test_submit_form_updates_existing_draft(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    sale = stack.sales.create_sale(date(2026, 1, 1), [])

    values = {
        "date": date(2026, 2, 1),
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("3"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(sale.id, values)

    assert result is True
    updated = stack.sales.get_sale(sale.id)
    assert len(updated.lignes) == 1


def test_load_edit_initial_returns_lines(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(sale.id)

    assert initial is not None
    assert initial["date"] == date(2026, 1, 1)
    assert len(initial["lignes"]) == 1
    assert initial["lignes"][0]["article_id"] == article.id


def test_load_edit_initial_returns_none_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._load_edit_initial(999999) is None


def test_delete_selected_removes_draft(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._delete_selected(sale.id)

    assert result is True
    from app.utils.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        stack.sales.get_sale(sale.id)


def test_delete_selected_refused_for_validated_sale(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._delete_selected(sale.id)

    assert result is False
    assert stack.sales.get_sale(sale.id).statut == StatutOperation.VALIDEE


def test_load_sale_for_detail_includes_movements_after_validation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._load_sale_for_detail(sale.id)

    assert result is not None
    loaded_sale, movements = result
    assert loaded_sale.numero == sale.numero
    assert len(movements) == 1


def test_validate_selected_updates_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(sale.id)

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("43")


def test_validate_selected_refused_on_insufficient_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("5"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("50"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(sale.id)

    assert result is False
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("5")


def test_cancel_selected_restores_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._cancel_selected(sale.id)

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")


def test_cancel_selected_denied_without_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)

    stack, _ = login_as("Vendeur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._cancel_selected(sale.id)

    assert result is False
    assert stack.sales.get_sale(sale.id).statut == StatutOperation.VALIDEE


def test_load_clients_for_form_excludes_inactive(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    active = stack.clients.create_client("Client actif")
    inactive = stack.clients.create_client("Client inactif")
    stack.clients.deactivate_client(inactive.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    clients = page._load_clients_for_form()

    ids = {client_id for client_id, _ in clients}
    assert active.id in ids
    assert inactive.id not in ids


def test_create_client_from_values_persists_and_returns_tuple(qtbot, login_as) -> None:
    """§5 : la création à la volée doit persister immédiatement le client et
    retourner (id, nom) pour sélection dans le formulaire de vente."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._create_client_from_values(
        {"nom": "Client à la volée", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )

    assert result is not None
    client_id, client_nom = result
    assert client_nom == "Client à la volée"
    assert stack.clients.get_client(client_id).nom == "Client à la volée"


def test_create_client_from_values_shows_warning_on_invalid_data(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._create_client_from_values(
        {"nom": "", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )

    assert result is None


def test_submit_form_with_client_id_associates_sale_to_client(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1),
        "client_id": client.id,
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("2"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(None, values)

    assert result is True
    created = stack.sales.list_sales()[0]
    assert created.client_id == client.id


def test_confirmation_dialog_no_cancels_validate(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_validate_clicked()

    assert stack.sales.get_sale(sale.id).statut == StatutOperation.BROUILLON
