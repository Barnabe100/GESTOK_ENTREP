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


# -- Lot 11 : validation directe (bouton « Valider » du formulaire) ----------
#
# Pour Location, « Valider » appelle uniquement LocationService.confirm_location
# (BROUILLON -> CONFIRMEE, sans effet stock) — jamais depart_location, qui
# exige une date de départ absente de ce formulaire. Ces tests vérifient
# explicitement que le cycle de vie n'est jamais poussé au-delà de la
# confirmation initiale.

def test_submit_form_validate_action_confirms_location_without_stock_effect(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": client.id, "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("2"), "tarif_jour": Decimal("500")}],
    }

    result = page._submit_form(None, values, "validate")

    assert result is True
    created = stack.rentals.list_locations()[0]
    assert created.statut == StatutLocation.CONFIRMEE
    # Jamais EN_COURS : depart_location n'est jamais déclenché par ce bouton.
    assert created.statut != StatutLocation.EN_COURS
    reloaded = stack.rentals.get_location(created.id)
    assert reloaded.date_depart is None
    assert reloaded.lignes[0].qte_en_location == Decimal("0")
    assert reloaded.lignes[0].qte_reservee == Decimal("2")
    # confirm_location ne modifie jamais le stock.
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")


def test_submit_form_validate_action_rejects_empty_lines_without_creating_stock_effect(qtbot, login_as) -> None:
    """confirm_location refuse une location sans ligne ; la création réussit
    (un brouillon peut être vide), la confirmation échoue ensuite — le
    brouillon vide créé reste retrouvable, sans doublon."""
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {"date": date(2026, 1, 1), "client_id": client.id, "commentaire": "", "lignes": []}

    result = page._submit_form(None, values, "validate")

    assert result is True
    locations = stack.rentals.list_locations()
    assert len(locations) == 1
    assert locations[0].statut == StatutLocation.BROUILLON


def test_submit_form_validate_action_rejects_article_no_longer_rental_without_creating(qtbot, login_as) -> None:
    """Contrairement à la rupture de stock, un article qui n'est plus en
    mode Location est déjà rejeté dès ``create_location``/``update_location``
    (même contrôle que ``confirm_location``, voir ``_build_lignes``) : il
    n'existe donc pas de fenêtre où la création réussirait puis la
    confirmation échouerait pour ce motif précis — la création elle-même
    est refusée, sans rien enregistrer."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.VENTE)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": client.id, "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("2"), "tarif_jour": Decimal("500")}],
    }

    result = page._submit_form(None, values, "validate")

    assert result is False
    assert stack.rentals.list_locations() == []


def test_submit_form_validate_action_denied_without_permission_keeps_draft_recoverable(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_rental_article(admin_stack, stock_initial=Decimal("10"))
    client = _make_client(admin_stack)

    role_id = next(r.id for r in admin_stack.roles.list_roles() if r.nom == "Vendeur")
    codes = admin_stack.roles.get_role_permissions(role_id)
    admin_stack.roles.update_role_permissions(role_id, [c for c in codes if c != "LOCATION_CONFIRM"])

    vendeur_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": client.id, "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("2"), "tarif_jour": Decimal("500")}],
    }

    result = page._submit_form(None, values, "validate")

    assert result is True
    locations = admin_stack.rentals.list_locations()
    assert len(locations) == 1
    assert locations[0].statut == StatutLocation.BROUILLON
    assert admin_stack.articles.get_article(article.id).stock_actuel == Decimal("10")


def test_submit_form_allows_missing_client(qtbot, login_as) -> None:
    """Lot « Client facultatif... » : le client n'est plus obligatoire —
    seule l'absence de ligne fait encore échouer la validation directe
    (``confirm_location`` exige au moins une ligne), jamais l'absence de
    client (voir ``test_submit_form_validate_action_rejects_empty_lines_...``
    pour ce cas, déjà couvert séparément)."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {"date": date(2026, 1, 1), "client_id": None, "commentaire": "", "lignes": []}

    result = page._submit_form(None, values)

    assert result is True
    created = stack.rentals.list_locations()[0]
    assert created.client_id is None
    assert created.client_nom is None


# -- Lot 13 : client facultatif + création rapide ----------------------------

def test_submit_form_creates_location_with_existing_client(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": client.id, "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("1"), "tarif_jour": Decimal("500")}],
    }

    result = page._submit_form(None, values)

    assert result is True
    created = stack.rentals.list_locations()[0]
    assert created.client_id == client.id
    assert created.client_nom == client.nom


def test_create_client_from_values_persists_and_returns_tuple(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._create_client_from_values(
        {"nom": "Client Location Rapide", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )

    assert result is not None
    client_id, client_nom = result
    assert client_nom == "Client Location Rapide"
    assert stack.clients.get_client(client_id).nom == "Client Location Rapide"


def test_create_client_from_values_shows_warning_on_invalid_data_and_preserves_location(qtbot, login_as) -> None:
    """§5-7 du lot : un échec de création du client ne doit ni créer de
    client, ni affecter la location en cours (ici simulée par des valeurs
    de formulaire non transmises au service, puisque la création échoue
    avant toute écriture)."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._create_client_from_values(
        {"nom": "", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )

    assert result is None
    assert stack.clients.list_clients() == []


def test_submit_form_with_new_client_selects_and_persists_it(qtbot, login_as) -> None:
    """Scénario complet de création rapide depuis le formulaire de
    location : le client créé via le callback est bien celui enregistré
    sur la location."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    created_client = page._create_client_from_values(
        {"nom": "Client Créé Pendant Location", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )
    assert created_client is not None
    client_id, _client_nom = created_client

    values = {
        "date": date(2026, 1, 1), "client_id": client_id, "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("1"), "tarif_jour": Decimal("500")}],
    }
    result = page._submit_form(None, values)

    assert result is True
    created_location = stack.rentals.list_locations()[0]
    assert created_location.client_id == client_id


def test_create_client_denied_without_permission(qtbot, login_as) -> None:
    """§6 du lot : sans CLIENT_CREATE, la création échoue côté service —
    jamais contournée côté vue."""
    admin_stack, _ = login_as("Administrateur")
    role_id = next(r.id for r in admin_stack.roles.list_roles() if r.nom == "Vendeur")
    codes = admin_stack.roles.get_role_permissions(role_id)
    admin_stack.roles.update_role_permissions(role_id, [c for c in codes if c != "CLIENT_CREATE"])

    vendeur_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_stack)
    qtbot.addWidget(page)

    result = page._create_client_from_values(
        {"nom": "Client Refusé", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )

    assert result is None
    assert admin_stack.clients.list_clients() == []


def test_location_without_client_follows_full_lifecycle(qtbot, login_as) -> None:
    """§9 du lot : confirmation, départ, retour, caution et paiement doivent
    fonctionner normalement sur une location sans client."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": None, "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("2"), "tarif_jour": Decimal("500")}],
    }
    page._submit_form(None, values)
    location = stack.rentals.list_locations()[0]
    assert location.client_id is None

    confirmed = stack.rentals.confirm_location(location.id)
    assert confirmed.statut == StatutLocation.CONFIRMEE
    stack.rentals.set_caution_montant(location.id, Decimal("1000"))

    departed = stack.rentals.depart_location(location.id, date(2026, 1, 1))
    assert departed.statut == StatutLocation.EN_COURS
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("8")

    ligne_id = stack.rentals.get_location(location.id).lignes[0].id
    returned = stack.rentals.return_location_line(
        location.id, ligne_id, date(2026, 1, 2), quantite_bon_etat=Decimal("2"), quantite_immobilisee=Decimal("0")
    )
    assert returned.statut == StatutLocation.RETOURNEE
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")

    stack.rentals.record_payment(location.id, Decimal("500"))
    assert stack.rentals.get_location(location.id).montant_paye == Decimal("500")


def test_locations_page_list_shows_neutral_label_when_client_absent(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": None, "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("1"), "tarif_jour": Decimal("500")}],
    }
    page._submit_form(None, values)
    page.refresh()

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "LOC-000001")
    assert page.table.item(row, 2).text() == "Client non renseigné"


def test_load_edit_initial_returns_none_client_id_when_absent(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    location = stack.rentals.create_location(date(2026, 1, 1), None, [])
    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(location.id)

    assert initial is not None
    assert initial["client_id"] is None


def test_submit_form_can_clear_client_on_update(qtbot, login_as) -> None:
    """§4 du lot : un client déjà associé peut être retiré via le
    formulaire de modification (sélection « Aucun client »)."""
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {"date": date(2026, 1, 1), "client_id": None, "commentaire": "", "lignes": []}

    result = page._submit_form(location.id, values)

    assert result is True
    assert stack.rentals.get_location(location.id).client_id is None
