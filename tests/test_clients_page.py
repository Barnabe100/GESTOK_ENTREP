from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from app.services.sales.sale_service import VenteLigneInput
from app.views.pages.clients_page import ClientsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.clients_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.clients_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> ClientsPage:
    return ClientsPage(stack.clients, stack.sales, stack.permissions)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("50")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def test_clients_page_lists_clients_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.clients.create_client("Client A")

    page = _build_page(stack)
    qtbot.addWidget(page)

    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "Client A" in names


def test_clients_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.clients.create_client("Martin SARL")
    stack.clients.create_client("Dupont SA")

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("martin")

    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert names == {"Martin SARL"}


def test_clients_page_shows_status_and_contact_columns(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client", telephone="0102030405")
    stack.clients.deactivate_client(created.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "Client")
    assert page.table.item(row, 1).text() == "0102030405"
    assert page.table.item(row, 3).text() == "Inactif"


def test_clients_page_buttons_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True
    assert page.edit_button.isEnabled() is True
    assert page.toggle_button.isEnabled() is True


def test_clients_page_toggle_disabled_for_vendeur(qtbot, login_as) -> None:
    """Décision métier : le Vendeur peut créer/modifier mais jamais
    activer/désactiver un client."""
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True
    assert page.edit_button.isEnabled() is True
    assert page.toggle_button.isEnabled() is False


def test_clients_page_table_empty_for_consultation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.clients.create_client("Client")

    consultation_stack, _ = login_as("Consultation")
    page = _build_page(consultation_stack)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0


def test_submit_form_creates_client_and_refreshes(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_form(
        None, {"nom": "Nouveau client", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )
    page.refresh()

    assert result is True
    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "Nouveau client" in names


def test_submit_form_shows_error_on_invalid_email_and_does_not_crash(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_form(
        None, {"nom": "Client", "telephone": "", "email": "invalide", "adresse": "", "observations": ""}
    )

    assert result is False
    assert stack.clients.list_clients(search="Client") == []


def test_submit_form_updates_existing_client(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_form(
        created.id, {"nom": "Client renommé", "telephone": "", "email": "", "adresse": "Nantes", "observations": ""}
    )

    assert result is True
    updated = stack.clients.get_client(created.id)
    assert updated.nom == "Client renommé"
    assert updated.adresse == "Nantes"


def test_load_edit_initial_returns_full_client_details(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client", adresse="12 rue des Fleurs", observations="Confidentiel")
    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(created.id)

    assert initial is not None
    assert initial["nom"] == "Client"
    assert initial["adresse"] == "12 rue des Fleurs"
    assert initial["observations"] == "Confidentiel"


def test_load_edit_initial_returns_none_and_warns_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(999999)

    assert initial is None


def test_toggle_status_deactivates_and_reactivates(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._toggle_status(created.id, currently_active=True) is True
    assert stack.clients.get_client(created.id).actif is False

    assert page._toggle_status(created.id, currently_active=False) is True
    assert stack.clients.get_client(created.id).actif is True


def test_toggle_status_denied_without_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.clients.create_client("Client")

    vendeur_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_stack)
    qtbot.addWidget(page)

    result = page._toggle_status(created.id, currently_active=True)

    assert result is False
    assert admin_stack.clients.get_client(created.id).actif is True


def test_confirmation_dialog_no_cancels_toggle(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client")
    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    page.table.selectRow(0)
    page._on_toggle_clicked()

    assert stack.clients.get_client(created.id).actif is True


# -- détail / historique -------------------------------------------------------------


def test_load_client_for_detail_includes_sales_history(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client acheteur")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._load_client_for_detail(client.id)

    assert result is not None
    loaded_client, sales = result
    assert loaded_client.nom == "Client acheteur"
    assert len(sales) == 1
    assert sales[0].client_id == client.id


def test_load_client_for_detail_keeps_history_after_deactivation(qtbot, login_as) -> None:
    """§8 : l'historique des ventes doit rester consultable après
    désactivation du client."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client acheteur")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )
    stack.sales.validate_sale(sale.id)
    stack.clients.deactivate_client(client.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._load_client_for_detail(client.id)

    assert result is not None
    loaded_client, sales = result
    assert loaded_client.actif is False
    assert len(sales) == 1


def test_load_client_for_detail_returns_empty_sales_without_sale_view(qtbot, login_as) -> None:
    """Un rôle avec CLIENT_VIEW mais sans SALE_VIEW (ex. Gestionnaire de
    stock) consulte le client sans échouer, historique vide."""
    admin_stack, _ = login_as("Administrateur")
    client = admin_stack.clients.create_client("Client")

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    assert not gestionnaire_stack.permissions.has_permission("SALE_VIEW")
    page = _build_page(gestionnaire_stack)
    qtbot.addWidget(page)

    result = page._load_client_for_detail(client.id)

    assert result is not None
    loaded_client, sales = result
    assert loaded_client.nom == "Client"
    assert sales == []
