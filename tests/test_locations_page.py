from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import ModeGestionArticle, StatutLocation
from app.services.rentals.location_service import LocationLigneInput
from app.views.pages.locations_page import LocationsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.locations_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.locations_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> LocationsPage:
    return LocationsPage(stack.rentals, stack.articles, stack.clients, stack.permissions)


def _make_rental_article(stack, reference="ART-LOC", stock_initial=Decimal("10"), tarif_jour=Decimal("500")):
    category = stack.categories.create_category(f"Cat-{reference}")
    article = stack.articles.create_article(
        reference, "Article de location", category.id, "unité",
        Decimal("1000"), Decimal("0"), Decimal("0"),
        stock_initial=stock_initial, tarif_location_jour=tarif_jour,
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    return stack.articles.get_article(article.id)


def _make_client(stack, nom="Client Location"):
    return stack.clients.create_client(nom)


def test_locations_page_lists_locations(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "LOC-000001" in numeros


def test_locations_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    stack.rentals.create_location(date(2026, 1, 1), client.id, [])
    stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("LOC-000001")

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {"LOC-000001"}


def test_locations_page_status_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    stack.rentals.create_location(date(2026, 1, 1), client.id, [])
    to_confirm = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.confirm_location(to_confirm.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    index = page.status_filter_combo.findData(StatutLocation.CONFIRMEE)
    page.status_filter_combo.setCurrentIndex(index)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {to_confirm.numero}


def test_locations_page_client_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client_a = _make_client(stack, "Client A")
    client_b = _make_client(stack, "Client B")
    stack.rentals.create_location(date(2026, 1, 1), client_a.id, [])
    loc_b = stack.rentals.create_location(date(2026, 1, 1), client_b.id, [])

    page = _build_page(stack)
    qtbot.addWidget(page)
    index = page.client_filter_combo.findData(client_b.id)
    page.client_filter_combo.setCurrentIndex(index)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {loc_b.numero}


def test_add_button_enabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True


def test_add_button_disabled_for_consultation(qtbot, login_as) -> None:
    stack, _ = login_as("Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is False


def test_action_buttons_reflect_brouillon_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.table.selectRow(0)

    assert page.edit_button.isEnabled() is True
    assert page.delete_button.isEnabled() is True


def test_action_buttons_disabled_once_confirmed(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.confirm_location(location.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.table.selectRow(0)

    assert page.edit_button.isEnabled() is False
    assert page.delete_button.isEnabled() is False


def test_only_location_mode_articles_are_proposed_in_form(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    rental_article = _make_rental_article(stack, reference="ART-LOC")
    category = stack.categories.create_category("Cat-vente")
    sale_article = stack.articles.create_article(
        "ART-VENTE", "Article de vente", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("10"),
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    articles = page._load_articles_for_form()
    article_ids = {a[0] for a in articles}
    assert rental_article.id in article_ids
    assert sale_article.id not in article_ids


def test_submit_form_creates_draft_location(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1),
        "client_id": client.id,
        "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("2"), "tarif_jour": Decimal("500")}],
    }

    result = page._submit_form(None, values)

    assert result is True
    created = stack.rentals.list_locations()[0]
    assert created.statut == StatutLocation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")


def test_submit_form_updates_existing_draft(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    values = {
        "date": date(2026, 2, 1),
        "client_id": client.id,
        "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("3"), "tarif_jour": Decimal("500")}],
    }

    result = page._submit_form(location.id, values)

    assert result is True
    updated = stack.rentals.get_location(location.id)
    assert len(updated.lignes) == 1


def test_load_edit_initial_returns_lines(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("4"))]
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(location.id)

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
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._delete_selected(location.id)

    assert result is True
    assert stack.rentals.list_locations() == []


def test_delete_selected_refused_once_confirmed(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.confirm_location(location.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._delete_selected(location.id)

    assert result is False


def test_load_location_for_detail(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._load_location_for_detail(location.id)

    assert result is not None
    assert result.numero == location.numero


def test_load_location_for_detail_returns_none_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._load_location_for_detail(999999) is None
