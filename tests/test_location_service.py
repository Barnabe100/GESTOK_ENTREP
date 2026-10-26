import threading
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.config.settings import get_settings
from app.db.session import session_scope
from app.models.enums import ModeGestionArticle, StatutActifInactif, StatutLocation, TypeMouvement
from app.models.rental import Location
from app.services.rentals.location_service import LocationLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def _make_category(stack, nom="Matériel"):
    return stack.categories.create_category(nom)


def _make_rental_article(
    stack, reference="ART-LOC", stock_initial=Decimal("10"), tarif_jour=Decimal("500"), category_id=None,
):
    if category_id is None:
        category_id = _make_category(stack, f"Cat-{reference}").id
    article = stack.articles.create_article(
        reference, "Article de location", category_id, "unité",
        Decimal("1000"), Decimal("0"), Decimal("0"),
        stock_initial=stock_initial, tarif_location_jour=tarif_jour,
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    return stack.articles.get_article(article.id)


def _make_client(stack, nom="Client Location"):
    return stack.clients.create_client(nom)


def _create_and_confirm(stack, article, client, quantite=Decimal("2")):
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, quantite)]
    )
    return stack.rentals.confirm_location(location.id)


def _create_confirm_depart(stack, article, client, quantite=Decimal("2"), date_depart=date(2026, 1, 1)):
    location = _create_and_confirm(stack, article, client, quantite)
    return stack.rentals.depart_location(location.id, date_depart)


# -- création -------------------------------------------------------------------


def test_create_draft_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)

    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("2"))])

    assert location.statut == StatutLocation.BROUILLON
    assert location.numero == "LOC-000001"
    assert len(location.lignes) == 1
    assert location.lignes[0].qte_prevue == Decimal("2")
    assert location.lignes[0].qte_reservee == Decimal("2")
    assert location.lignes[0].qte_en_location == Decimal("0")
    assert location.lignes[0].tarif_jour == Decimal("500")


def test_create_location_draft_does_not_touch_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)

    stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("2"))])

    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")


def test_create_location_rejects_unknown_article(login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)

    with pytest.raises(NotFoundError):
        stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(999999, Decimal("1"))])


def test_create_location_rejects_article_not_in_location_mode(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article = stack.articles.create_article(
        "ART-VENTE", "Article de vente", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("10"),
    )
    client = _make_client(stack)

    with pytest.raises(ValidationError):
        stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])


def test_create_location_rejects_article_without_tarif(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article = stack.articles.create_article(
        "ART-SANS-TARIF", "Sans tarif", category.id, "unité", Decimal("100"), Decimal("0"), Decimal("0"),
        stock_initial=Decimal("10"),
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    client = _make_client(stack)

    with pytest.raises(ValidationError):
        stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])


def test_create_location_line_can_override_tarif(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, tarif_jour=Decimal("500"))
    client = _make_client(stack)

    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"), tarif_jour=Decimal("750"))]
    )

    assert location.lignes[0].tarif_jour == Decimal("750")


def test_create_location_rejects_inactive_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    stack.clients.deactivate_client(client.id)

    with pytest.raises(ValidationError):
        stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])


def test_create_location_rejects_zero_or_negative_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)

    with pytest.raises(ValidationError):
        stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("0"))])
    with pytest.raises(ValidationError):
        stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("-1"))])


def test_create_location_rejects_future_date(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)

    with pytest.raises(ValidationError):
        stack.rentals.create_location(date(2099, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])


# -- modification / suppression ------------------------------------------------


def test_update_draft_location_replaces_lines(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article_1 = _make_rental_article(stack, reference="ART-1")
    article_2 = _make_rental_article(stack, reference="ART-2")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article_1.id, Decimal("1"))])

    updated = stack.rentals.update_location(
        location.id, date(2026, 1, 2), client.id, [LocationLigneInput(article_2.id, Decimal("3"))]
    )

    assert len(updated.lignes) == 1
    assert updated.lignes[0].article_id == article_2.id
    assert updated.date == date(2026, 1, 2)


def test_update_confirmed_location_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = _create_and_confirm(stack, article, client)

    with pytest.raises(ConflictError):
        stack.rentals.update_location(location.id, date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])


def test_delete_draft_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])

    stack.rentals.delete_location(location.id)

    with pytest.raises(NotFoundError):
        stack.rentals.get_location(location.id)


def test_delete_confirmed_location_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = _create_and_confirm(stack, article, client)

    with pytest.raises(ConflictError):
        stack.rentals.delete_location(location.id)


# -- confirmation -----------------------------------------------------------------


def test_confirm_draft_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("2"))])

    confirmed = stack.rentals.confirm_location(location.id)

    assert confirmed.statut == StatutLocation.CONFIRMEE
    # Confirmation : aucun mouvement de stock, qte_reservee inchangée.
    assert confirmed.lignes[0].qte_reservee == Decimal("2")
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")


def test_confirm_location_without_lines_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    with pytest.raises(ValidationError):
        stack.rentals.confirm_location(location.id)


def test_confirm_already_confirmed_location_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = _create_and_confirm(stack, article, client)

    with pytest.raises(ConflictError):
        stack.rentals.confirm_location(location.id)


def test_confirm_location_rechecks_article_still_in_location_mode(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.VENTE)

    with pytest.raises(ValidationError):
        stack.rentals.confirm_location(location.id)


# -- départ -----------------------------------------------------------------------


def test_depart_location_decrements_stock_and_moves_quantities(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)
    location = _create_and_confirm(stack, article, client, quantite=Decimal("3"))

    departed = stack.rentals.depart_location(location.id, date(2026, 1, 1))

    assert departed.statut == StatutLocation.EN_COURS
    assert departed.date_depart == date(2026, 1, 1)
    assert departed.lignes[0].qte_reservee == Decimal("0")
    assert departed.lignes[0].qte_en_location == Decimal("3")
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("7")


def test_depart_location_creates_location_sortie_movement(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)
    location = _create_and_confirm(stack, article, client, quantite=Decimal("3"))

    stack.rentals.depart_location(location.id, date(2026, 1, 1))

    movements = stack.movements.list_movements(article_id=article.id)
    sortie_movements = [m for m in movements if m.type == TypeMouvement.LOCATION_SORTIE]
    assert len(sortie_movements) == 1
    assert sortie_movements[0].quantite == Decimal("-3")


def test_depart_refuses_negative_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("1"))
    client = _make_client(stack)
    location = _create_and_confirm(stack, article, client, quantite=Decimal("5"))

    with pytest.raises(ValidationError):
        stack.rentals.depart_location(location.id, date(2026, 1, 1))

    assert stack.articles.get_article(article.id).stock_actuel == Decimal("1")


def test_depart_draft_location_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])

    with pytest.raises(ConflictError):
        stack.rentals.depart_location(location.id, date(2026, 1, 1))


def test_depart_rejects_date_before_location_date(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 10), client.id, [LocationLigneInput(article.id, Decimal("1"))])
    confirmed = stack.rentals.confirm_location(location.id)

    with pytest.raises(ValidationError):
        stack.rentals.depart_location(confirmed.id, date(2026, 1, 5))


# -- retours ------------------------------------------------------------------------


def test_full_return_in_good_condition_restores_stock_and_closes_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"), tarif_jour=Decimal("500"))
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("2"), date_depart=date(2026, 1, 1))

    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 3), quantite_bon_etat=Decimal("2")
    )

    assert returned.statut == StatutLocation.RETOURNEE
    assert returned.lignes[0].qte_en_location == Decimal("0")
    assert returned.lignes[0].qte_immobilisee == Decimal("0")
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")
    # 2 jours (1 -> 3 janvier) * 500 * 2 unités = 2000
    assert returned.lignes[0].montant_facture_total == Decimal("2000")
    assert returned.montant_total_facture == Decimal("2000")


def test_return_creates_location_retour_movement_for_good_condition_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("2"))

    stack.rentals.return_location_line(departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("2"))

    movements = stack.movements.list_movements(article_id=article.id)
    retour_movements = [m for m in movements if m.type == TypeMouvement.LOCATION_RETOUR]
    assert len(retour_movements) == 1
    assert retour_movements[0].quantite == Decimal("2")


def test_partial_return_keeps_location_en_cours(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("5"))

    partial = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("2")
    )

    assert partial.statut == StatutLocation.EN_COURS
    assert partial.lignes[0].qte_en_location == Decimal("3")

    final = stack.rentals.return_location_line(
        partial.id, partial.lignes[0].id, date(2026, 1, 3), quantite_bon_etat=Decimal("3")
    )

    assert final.statut == StatutLocation.RETOURNEE
    assert final.lignes[0].qte_en_location == Decimal("0")
    assert len(final.lignes[0].retours) == 2


def test_return_with_immobilized_quantity_never_restores_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("2"))

    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2),
        quantite_bon_etat=Decimal("1"), quantite_immobilisee=Decimal("1"),
    )

    assert returned.lignes[0].qte_immobilisee == Decimal("1")
    assert returned.lignes[0].qte_en_location == Decimal("0")
    assert returned.statut == StatutLocation.RETOURNEE
    # stock_actuel : 10 - 2 (départ) + 1 (retour bon état seulement) = 9
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("9")


def test_immobilized_quantity_is_still_billed(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, tarif_jour=Decimal("500"))
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("2"), date_depart=date(2026, 1, 1))

    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_immobilisee=Decimal("2")
    )

    # 1 jour * 500 * 2 unités (bon état + immobilisée) = 1000
    assert returned.lignes[0].montant_facture_total == Decimal("1000")


def test_return_minimum_billed_duration_is_one_day(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, tarif_jour=Decimal("500"))
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("1"), date_depart=date(2026, 1, 1))

    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 1), quantite_bon_etat=Decimal("1")
    )

    assert returned.lignes[0].montant_facture_total == Decimal("500")


def test_return_rejects_quantity_exceeding_qte_en_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("2"))

    with pytest.raises(ValidationError):
        stack.rentals.return_location_line(
            departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("3")
        )


def test_return_rejects_zero_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("2"))

    with pytest.raises(ValidationError):
        stack.rentals.return_location_line(departed.id, departed.lignes[0].id, date(2026, 1, 2))


def test_return_on_draft_or_confirmed_location_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    confirmed = _create_and_confirm(stack, article, client)

    with pytest.raises(ConflictError):
        stack.rentals.return_location_line(
            confirmed.id, confirmed.lignes[0].id, date(2026, 1, 1), quantite_bon_etat=Decimal("1")
        )


def test_return_rejects_date_before_depart(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, date_depart=date(2026, 1, 5))

    with pytest.raises(ValidationError):
        stack.rentals.return_location_line(
            departed.id, departed.lignes[0].id, date(2026, 1, 1), quantite_bon_etat=Decimal("1")
        )


def test_return_rejects_unknown_line_for_this_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client)

    with pytest.raises(NotFoundError):
        stack.rentals.return_location_line(departed.id, 999999, date(2026, 1, 2), quantite_bon_etat=Decimal("1"))


# -- annulation ---------------------------------------------------------------------


def test_cancel_draft_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])

    cancelled = stack.rentals.cancel_location(location.id, "Client s'est désisté")

    assert cancelled.statut == StatutLocation.ANNULEE
    assert cancelled.annulation_motif == "Client s'est désisté"


def test_cancel_confirmed_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    confirmed = _create_and_confirm(stack, article, client)

    cancelled = stack.rentals.cancel_location(confirmed.id, "Annulation avant départ")

    assert cancelled.statut == StatutLocation.ANNULEE


def test_cancel_after_depart_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client)

    with pytest.raises(ConflictError):
        stack.rentals.cancel_location(departed.id, "Tentative d'annulation après départ")

    # Aucun effet : le stock décrémenté au départ reste inchangé.
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("8")


def test_cancel_requires_a_motif(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])

    with pytest.raises(ValidationError):
        stack.rentals.cancel_location(location.id, "")
    with pytest.raises(ValidationError):
        stack.rentals.cancel_location(location.id, "abc")  # trop court


# -- caution --------------------------------------------------------------------------


def test_set_caution_montant_on_draft(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])

    updated = stack.rentals.set_caution_montant(location.id, Decimal("10000"))

    assert updated.caution_montant == Decimal("10000")


def test_set_caution_montant_after_depart_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client)

    with pytest.raises(ConflictError):
        stack.rentals.set_caution_montant(departed.id, Decimal("5000"))


def test_record_caution_return_full(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])
    stack.rentals.set_caution_montant(location.id, Decimal("10000"))

    updated = stack.rentals.record_caution_return(location.id, Decimal("10000"))

    assert updated.caution_rendue == Decimal("10000")


def test_record_caution_return_exceeding_montant_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])
    stack.rentals.set_caution_montant(location.id, Decimal("10000"))

    with pytest.raises(ValidationError):
        stack.rentals.record_caution_return(location.id, Decimal("10001"))


def test_record_caution_return_can_be_partial_then_completed(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])
    stack.rentals.set_caution_montant(location.id, Decimal("10000"))

    stack.rentals.record_caution_return(location.id, Decimal("4000"))
    final = stack.rentals.record_caution_return(location.id, Decimal("6000"))

    assert final.caution_rendue == Decimal("10000")


# -- paiements --------------------------------------------------------------------


def test_record_payment_on_returned_location(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, tarif_jour=Decimal("500"))
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("2"), date_depart=date(2026, 1, 1))
    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("2")
    )
    assert returned.montant_total_facture == Decimal("1000")

    paid = stack.rentals.record_payment(returned.id, Decimal("600"), mode_paiement="Espèces")

    assert paid.montant_paye == Decimal("600")
    assert paid.reste_a_payer == Decimal("400")


def test_record_payment_exceeding_invoiced_amount_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, tarif_jour=Decimal("500"))
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("2"), date_depart=date(2026, 1, 1))
    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("2")
    )

    with pytest.raises(ValidationError):
        stack.rentals.record_payment(returned.id, Decimal("1000.01"))


def test_record_payment_before_depart_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    confirmed = _create_and_confirm(stack, article, client)

    with pytest.raises(ConflictError):
        stack.rentals.record_payment(confirmed.id, Decimal("100"))


def test_record_payment_while_still_en_cours_before_any_return(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client)

    # Rien n'est encore facturé (aucun retour) -> tout paiement dépasserait 0.
    with pytest.raises(ValidationError):
        stack.rentals.record_payment(departed.id, Decimal("1"))


# -- permissions ----------------------------------------------------------------------


def test_consultation_can_view_but_not_create(login_as) -> None:
    stack, _ = login_as("Consultation")

    assert stack.rentals.list_locations() == []
    with pytest.raises(PermissionDeniedError):
        stack.rentals.create_location(date(2026, 1, 1), 1, [])


@pytest.mark.parametrize("role", ["Gestionnaire de stock", "Vendeur"])
def test_operational_roles_can_run_full_lifecycle(login_as, role) -> None:
    # Catalogue/client préparés par un Administrateur : ARTICLE_CREATE et
    # CATEGORY_CREATE ne sont pas accordées au Vendeur (décision métier
    # préexistante, hors périmètre de ce lot) — seul le cycle de vie de la
    # location elle-même est testé sous l'identité du rôle opérationnel.
    admin_stack, _ = login_as("Administrateur")
    article = _make_rental_article(admin_stack, tarif_jour=Decimal("500"))
    client = _make_client(admin_stack)

    stack, _ = login_as(role)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])
    stack.rentals.set_caution_montant(location.id, Decimal("1000"))
    confirmed = stack.rentals.confirm_location(location.id)
    departed = stack.rentals.depart_location(confirmed.id, date(2026, 1, 1))
    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("1")
    )
    stack.rentals.record_payment(returned.id, Decimal("100"))
    stack.rentals.record_caution_return(returned.id, Decimal("500"))

    assert returned.statut == StatutLocation.RETOURNEE


@pytest.mark.parametrize("role", ["Gestionnaire de stock", "Vendeur"])
def test_operational_roles_cannot_cancel(login_as, role) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_rental_article(admin_stack)
    client = _make_client(admin_stack)

    stack, _ = login_as(role)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])

    with pytest.raises(PermissionDeniedError):
        stack.rentals.cancel_location(location.id, "Motif quelconque")


# -- intégrité avec le module Ventes (mode_gestion) --------------------------------


def test_article_in_location_mode_cannot_be_sold(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    with pytest.raises(ValidationError):
        stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("100"))])


def test_switching_back_to_vente_mode_is_blocked_while_location_active(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    _create_confirm_depart(stack, article, client, quantite=Decimal("1"))

    with pytest.raises(ConflictError):
        stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.VENTE)


def test_switching_back_to_vente_mode_succeeds_once_fully_returned(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    departed = _create_confirm_depart(stack, article, client, quantite=Decimal("1"))
    stack.rentals.return_location_line(departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("1"))

    updated = stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.VENTE)

    assert updated.mode_gestion == ModeGestionArticle.VENTE


# -- accès concurrent -----------------------------------------------------------------


def test_concurrent_returns_on_different_lines_do_not_lose_updates(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_rental_article(stack, reference="ART-C1", category_id=category.id)
    article_2 = _make_rental_article(stack, reference="ART-C2", category_id=category.id)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id,
        [LocationLigneInput(article_1.id, Decimal("1")), LocationLigneInput(article_2.id, Decimal("1"))],
    )
    confirmed = stack.rentals.confirm_location(location.id)
    departed = stack.rentals.depart_location(confirmed.id, date(2026, 1, 1))
    ligne_1, ligne_2 = departed.lignes[0].id, departed.lignes[1].id

    errors = []

    def _return(ligne_id):
        try:
            stack.rentals.return_location_line(departed.id, ligne_id, date(2026, 1, 2), quantite_bon_etat=Decimal("1"))
        except Exception as exc:  # pragma: no cover - uniquement si échec réel
            errors.append(exc)

    threads = [threading.Thread(target=_return, args=(ligne_1,)), threading.Thread(target=_return, args=(ligne_2,))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    final = stack.rentals.get_location(departed.id)
    assert final.statut == StatutLocation.RETOURNEE
    assert all(l.qte_en_location == Decimal("0") for l in final.lignes)


# -- Lot 13 : client facultatif ----------------------------------------------

def test_create_location_without_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)

    created = stack.rentals.create_location(
        date(2026, 1, 1), None, [LocationLigneInput(article.id, Decimal("1"))]
    )

    assert created.client_id is None
    assert created.client_nom is None


def test_create_location_with_existing_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)

    created = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )

    assert created.client_id == client.id
    assert created.client_nom == client.nom


def test_update_location_can_clear_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    updated = stack.rentals.update_location(location.id, date(2026, 1, 1), None, [])

    assert updated.client_id is None


def test_update_location_can_assign_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), None, [])

    updated = stack.rentals.update_location(location.id, date(2026, 1, 1), client.id, [])

    assert updated.client_id == client.id


def test_create_location_without_client_rejects_inactive_lines_normally(login_as) -> None:
    """Non-régression : l'absence de client ne relâche aucune autre
    validation (ici, article non géré en mode Location)."""
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel vente")
    article = stack.articles.create_article(
        "ART-VENTE-SEUL", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
    )

    with pytest.raises(ValidationError):
        stack.rentals.create_location(
            date(2026, 1, 1), None, [LocationLigneInput(article.id, Decimal("1"))]
        )


def test_location_without_client_supports_full_lifecycle_at_service_level(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("5"))

    location = stack.rentals.create_location(
        date(2026, 1, 1), None, [LocationLigneInput(article.id, Decimal("2"))]
    )
    stack.rentals.confirm_location(location.id)
    stack.rentals.depart_location(location.id, date(2026, 1, 1))
    ligne = stack.rentals.get_location(location.id).lignes[0]
    returned = stack.rentals.return_location_line(
        location.id, ligne.id, date(2026, 1, 2),
        quantite_bon_etat=Decimal("2"), quantite_immobilisee=Decimal("0"),
    )

    assert returned.statut == StatutLocation.RETOURNEE
    assert returned.client_id is None
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("5")


def test_list_locations_orders_by_creation_date_not_business_date(login_as) -> None:
    """Chantier B : voir le test équivalent dans tests/test_vente_repository.py
    — une location enregistrée à l'instant mais datée d'hier doit apparaître
    avant une location plus ancienne mais datée d'aujourd'hui."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)

    older_creation = stack.rentals.create_location(
        date(2026, 6, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    newer_creation = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )

    with session_scope(get_settings()) as session:
        session.query(Location).filter_by(id=older_creation.id).update(
            {"date_creation": datetime(2026, 1, 1, 8, 0, 0)}
        )
        session.query(Location).filter_by(id=newer_creation.id).update(
            {"date_creation": datetime(2026, 6, 1, 8, 0, 0)}
        )

    results = stack.rentals.list_locations()

    assert [r.id for r in results] == [newer_creation.id, older_creation.id]
