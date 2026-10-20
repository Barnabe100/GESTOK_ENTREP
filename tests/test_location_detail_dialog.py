from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import ModeGestionArticle, StatutLocation
from app.services.rentals.location_service import LocationLigneInput
from app.views.location_detail_dialog import LocationDetailDialog


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.location_detail_dialog.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.location_detail_dialog.QMessageBox.warning", lambda *a, **k: None)


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


def _build_dialog(stack, location):
    return LocationDetailDialog(location, "XOF", stack.rentals, stack.permissions)


def test_detail_dialog_shows_numero_in_title(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    assert location.numero in dialog.windowTitle()


def test_detail_dialog_shows_lines(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("2"))]
    )

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.rowCount() == 1
    assert "ART-LOC" in dialog.lines_table.item(0, 0).text()


def test_confirm_button_enabled_only_for_draft_with_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    assert dialog.confirm_button.isEnabled() is True
    assert dialog.depart_button.isEnabled() is False
    assert dialog.return_button.isEnabled() is False
    assert dialog.cancel_location_button.isEnabled() is True


def test_confirm_action_transitions_to_confirmee(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    result = dialog._confirm()
    dialog._refresh()

    assert result is True
    assert dialog._location.statut == StatutLocation.CONFIRMEE
    assert dialog.depart_button.isEnabled() is True


def test_depart_action_decrements_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("3"))]
    )
    stack.rentals.confirm_location(location.id)

    dialog = _build_dialog(stack, stack.rentals.get_location(location.id))
    qtbot.addWidget(dialog)

    result = dialog._depart(date(2026, 1, 1))
    dialog._refresh()

    assert result is True
    assert dialog._location.statut == StatutLocation.EN_COURS
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("7")
    assert dialog.return_button.isEnabled() is True


def test_return_action_records_retour_and_bills_correctly(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, tarif_jour=Decimal("500"))
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("2"))]
    )
    stack.rentals.confirm_location(location.id)
    stack.rentals.depart_location(location.id, date(2026, 1, 1))

    dialog = _build_dialog(stack, stack.rentals.get_location(location.id))
    qtbot.addWidget(dialog)
    ligne_id = dialog._location.lignes[0].id

    result = dialog._submit_return(
        {
            "location_ligne_id": ligne_id,
            "date_retour": date(2026, 1, 2),
            "quantite_bon_etat": "2",
            "quantite_immobilisee": "0",
            "commentaire": None,
        }
    )
    dialog._refresh()

    assert result is True
    assert dialog._location.statut == StatutLocation.RETOURNEE
    assert dialog._location.montant_total_facture == Decimal("1000")
    assert dialog.retours_table.rowCount() == 1


def test_cancel_action_before_depart(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    result = dialog._cancel("Motif de test valide")
    dialog._refresh()

    assert result is True
    assert dialog._location.statut == StatutLocation.ANNULEE


def test_cancel_button_disabled_after_depart(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.confirm_location(location.id)
    stack.rentals.depart_location(location.id, date(2026, 1, 1))

    dialog = _build_dialog(stack, stack.rentals.get_location(location.id))
    qtbot.addWidget(dialog)

    assert dialog.cancel_location_button.isEnabled() is False


def test_caution_set_before_depart(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    result = dialog._submit_caution({"montant": "10000"}, peut_modifier_montant=True)
    dialog._refresh()

    assert result is True
    assert dialog._location.caution_montant == Decimal("10000")


def test_caution_return_after_depart(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.set_caution_montant(location.id, Decimal("10000"))
    stack.rentals.confirm_location(location.id)
    stack.rentals.depart_location(location.id, date(2026, 1, 1))

    dialog = _build_dialog(stack, stack.rentals.get_location(location.id))
    qtbot.addWidget(dialog)

    result = dialog._submit_caution({"montant": "4000"}, peut_modifier_montant=False)
    dialog._refresh()

    assert result is True
    assert dialog._location.caution_rendue == Decimal("4000")


def test_payment_action_after_return(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, tarif_jour=Decimal("500"))
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.confirm_location(location.id)
    stack.rentals.depart_location(location.id, date(2026, 1, 1))
    returned = stack.rentals.return_location_line(
        location.id, stack.rentals.get_location(location.id).lignes[0].id,
        date(2026, 1, 2), quantite_bon_etat=Decimal("1"),
    )

    dialog = _build_dialog(stack, returned)
    qtbot.addWidget(dialog)

    result = dialog._submit_payment({"montant": "300", "mode_paiement": None, "reference": None, "commentaire": None})
    dialog._refresh()

    assert result is True
    assert dialog._location.montant_paye == Decimal("300")


# -- désactivation après solde (Lot 17) ----------------------------------------------


def _depart_with_return(stack, tarif_jour=Decimal("500"), quantite=Decimal("1"), caution_montant=None):
    """Location EN_COURS puis entièrement retournée (donc facturée) —
    base commune aux tests de désactivation du bouton de paiement.
    ``caution_montant``, si fourni, est fixé tant que la location est
    encore en BROUILLON (seul moment où set_caution_montant l'autorise)."""
    article = _make_rental_article(stack, tarif_jour=tarif_jour)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, quantite)]
    )
    if caution_montant is not None:
        stack.rentals.set_caution_montant(location.id, caution_montant)
    stack.rentals.confirm_location(location.id)
    stack.rentals.depart_location(location.id, date(2026, 1, 1))
    ligne_id = stack.rentals.get_location(location.id).lignes[0].id
    return stack.rentals.return_location_line(
        location.id, ligne_id, date(2026, 1, 2), quantite_bon_etat=quantite,
    )


def test_payment_button_enabled_with_positive_balance(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    returned = _depart_with_return(stack, tarif_jour=Decimal("500"))

    dialog = _build_dialog(stack, returned)
    qtbot.addWidget(dialog)

    assert dialog._location.reste_a_payer > 0
    assert dialog.payment_button.isEnabled() is True


def test_payment_button_disabled_when_balance_reaches_zero(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    returned = _depart_with_return(stack, tarif_jour=Decimal("500"))

    dialog = _build_dialog(stack, returned)
    qtbot.addWidget(dialog)

    result = dialog._submit_payment(
        {"montant": str(dialog._location.reste_a_payer), "mode_paiement": None, "reference": None, "commentaire": None}
    )
    dialog._refresh()

    assert result is True
    assert dialog._location.reste_a_payer == Decimal("0")
    assert dialog.payment_button.isEnabled() is False


def test_payment_button_stays_disabled_after_refresh_when_balance_still_zero(qtbot, login_as) -> None:
    """Le bouton ne doit pas redevenir actif après un rafraîchissement
    supplémentaire si le solde reste nul, même si le statut évolue."""
    stack, _ = login_as("Administrateur")
    returned = _depart_with_return(stack, tarif_jour=Decimal("500"))

    dialog = _build_dialog(stack, returned)
    qtbot.addWidget(dialog)
    dialog._submit_payment(
        {"montant": str(dialog._location.reste_a_payer), "mode_paiement": None, "reference": None, "commentaire": None}
    )

    dialog._refresh()

    assert dialog._location.statut == StatutLocation.RETOURNEE
    assert dialog.payment_button.isEnabled() is False


def test_payment_button_disabled_when_nothing_billed_yet_even_if_en_cours(qtbot, login_as) -> None:
    """EN_COURS mais aucun retour encore enregistré : rien n'est facturé,
    ``reste_a_payer`` est donc nul par construction — le bouton ne doit
    pas être actif avant toute facturation."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.confirm_location(location.id)
    stack.rentals.depart_location(location.id, date(2026, 1, 1))

    dialog = _build_dialog(stack, stack.rentals.get_location(location.id))
    qtbot.addWidget(dialog)

    assert dialog._location.statut == StatutLocation.EN_COURS
    assert dialog._location.montant_total_facture == Decimal("0")
    assert dialog.payment_button.isEnabled() is False


def test_caution_button_enabled_with_remaining_deposit(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])
    stack.rentals.set_caution_montant(location.id, Decimal("10000"))

    dialog = _build_dialog(stack, stack.rentals.get_location(location.id))
    qtbot.addWidget(dialog)

    assert dialog.caution_button.isEnabled() is True


def test_caution_button_disabled_when_fully_restituted(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])
    stack.rentals.set_caution_montant(location.id, Decimal("10000"))
    stack.rentals.record_caution_return(location.id, Decimal("10000"))

    dialog = _build_dialog(stack, stack.rentals.get_location(location.id))
    qtbot.addWidget(dialog)

    assert dialog._location.caution_montant - dialog._location.caution_rendue == Decimal("0")
    assert dialog.caution_button.isEnabled() is False


def test_caution_button_disabled_when_no_caution_defined(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    assert dialog._location.caution_montant == Decimal("0")
    assert dialog.caution_button.isEnabled() is False


@pytest.mark.parametrize("role_name", ["Consultation"])
def test_payment_and_caution_buttons_disabled_without_permission(qtbot, login_as, role_name) -> None:
    """Même avec un solde et une caution restants, l'absence de permission
    doit désactiver les boutons — non-régression du contrôle existant."""
    admin_stack, _ = login_as("Administrateur")
    returned = _depart_with_return(admin_stack, tarif_jour=Decimal("500"), caution_montant=Decimal("10000"))
    reloaded = admin_stack.rentals.get_location(returned.id)

    stack, _ = login_as(role_name)
    dialog = LocationDetailDialog(reloaded, "XOF", stack.rentals, stack.permissions)
    qtbot.addWidget(dialog)

    assert dialog._location.reste_a_payer > 0
    assert (dialog._location.caution_montant - dialog._location.caution_rendue) > 0
    assert dialog.payment_button.isEnabled() is False
    assert dialog.caution_button.isEnabled() is False


def test_other_buttons_unaffected_by_balance_based_gating(qtbot, login_as) -> None:
    """Les autres boutons (confirmer/départ/retour/annuler) conservent
    exactement leur comportement — non affectés par le Lot 17."""
    stack, _ = login_as("Administrateur")
    returned = _depart_with_return(stack, tarif_jour=Decimal("500"))
    dialog = _build_dialog(stack, returned)
    qtbot.addWidget(dialog)
    dialog._submit_payment(
        {"montant": str(dialog._location.reste_a_payer), "mode_paiement": None, "reference": None, "commentaire": None}
    )
    dialog._refresh()

    assert dialog.confirm_button.isEnabled() is False
    assert dialog.depart_button.isEnabled() is False
    assert dialog.return_button.isEnabled() is False
    assert dialog.cancel_location_button.isEnabled() is False


def test_read_only_still_disables_payment_and_caution_regardless_of_balance(qtbot, login_as) -> None:
    """Le mode lecture seule du Lot 16 doit continuer à primer : même avec
    un solde/une caution restants, aucune action mutante disponible."""
    stack, _ = login_as("Administrateur")
    returned = _depart_with_return(stack, tarif_jour=Decimal("500"), caution_montant=Decimal("10000"))
    reloaded = stack.rentals.get_location(returned.id)

    dialog = LocationDetailDialog(reloaded, "XOF", stack.rentals, stack.permissions, read_only=True)
    qtbot.addWidget(dialog)

    assert dialog._location.reste_a_payer > 0
    assert dialog.payment_button.isEnabled() is False
    assert dialog.caution_button.isEnabled() is False


def test_permission_denied_action_shows_warning_not_crash(qtbot, login_as) -> None:
    stack, _ = login_as("Consultation")
    admin_stack, _ = login_as("Administrateur")
    client = _make_client(admin_stack)
    location = admin_stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    dialog = LocationDetailDialog(location, "XOF", stack.rentals, stack.permissions)
    qtbot.addWidget(dialog)

    result = dialog._confirm()

    assert result is False


# -- Lot 13 : client facultatif ----------------------------------------------

def test_detail_dialog_shows_neutral_label_when_client_absent(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    location = stack.rentals.create_location(date(2026, 1, 1), None, [])

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    labels = [
        dialog._header_form.itemAt(i, dialog._header_form.ItemRole.FieldRole).widget().text()
        for i in range(dialog._header_form.rowCount())
    ]
    assert "Client non renseigné" in labels


def test_detail_dialog_shows_client_name_when_present(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    client = _make_client(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [])

    dialog = _build_dialog(stack, location)
    qtbot.addWidget(dialog)

    labels = [
        dialog._header_form.itemAt(i, dialog._header_form.ItemRole.FieldRole).widget().text()
        for i in range(dialog._header_form.rowCount())
    ]
    assert client.nom in labels


# -- chemin de consultation en lecture seule (Lot 16) --------------------------------


def test_read_only_disables_all_mutating_actions_regardless_of_status(qtbot, login_as) -> None:
    """Quel que soit le statut et quelle que soit la permission accordée,
    aucune action mutante ne doit rester disponible en lecture seule."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("2"))]
    )

    dialog = LocationDetailDialog(location, "XOF", stack.rentals, stack.permissions, read_only=True)
    qtbot.addWidget(dialog)

    assert dialog.confirm_button.isEnabled() is False
    assert dialog.depart_button.isEnabled() is False
    assert dialog.return_button.isEnabled() is False
    assert dialog.cancel_location_button.isEnabled() is False
    assert dialog.caution_button.isEnabled() is False
    assert dialog.payment_button.isEnabled() is False


def test_read_only_still_shows_consultation_data(qtbot, login_as) -> None:
    """La consultation (lignes, statut, paiements, caution) reste
    entièrement disponible — seules les actions mutantes sont retirées."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("2"))]
    )

    dialog = LocationDetailDialog(location, "XOF", stack.rentals, stack.permissions, read_only=True)
    qtbot.addWidget(dialog)

    assert location.numero in dialog.windowTitle()
    assert dialog.lines_table.rowCount() == 1


def test_not_read_only_by_default_preserves_existing_behaviour(qtbot, login_as) -> None:
    """Non-régression explicite : l'absence du paramètre reproduit
    exactement le comportement d'avant le Lot 16."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack)
    client = _make_client(stack)
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    confirmed = stack.rentals.confirm_location(location.id)

    dialog = LocationDetailDialog(confirmed, "XOF", stack.rentals, stack.permissions)
    qtbot.addWidget(dialog)

    assert dialog.confirm_button.isEnabled() is False  # déjà confirmée
    assert dialog.cancel_location_button.isEnabled() is True  # toujours annulable
