from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models.enums import TypeMouvement
from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError


def _make_article(stack, reference="ART-1", stock_initial=Decimal("50")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def _create_and_validate_sale(stack, article, quantite=Decimal("3"), prix=Decimal("150"), client_id=None):
    from app.services.sales.sale_service import VenteLigneInput

    sale = stack.sales.create_sale(
        date(2026, 1, 15), [VenteLigneInput(article.id, quantite, prix)], client_id=client_id
    )
    return stack.sales.validate_sale(sale.id)


# -- permissions ---------------------------------------------------------------------


def test_gestionnaire_stock_without_sale_view_is_denied(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)
    sale = _create_and_validate_sale(admin_stack, article)

    stack, _ = login_as("Gestionnaire de stock")
    with pytest.raises(PermissionDeniedError):
        stack.documents.build_sale_receipt(sale.id)


def test_vendeur_can_generate_receipt_without_settings_view(login_as) -> None:
    """Écart de permission corrigé par ce lot : un Vendeur a SALE_VIEW mais
    pas SETTINGS_VIEW — il doit tout de même pouvoir imprimer le reçu de sa
    propre vente (le profil entreprise est lu via une fonction dédiée, sans
    permission, voir get_company_profile())."""
    admin_stack, _ = login_as("Administrateur")
    admin_stack.parameters.update_config(
        nom="Boutique Test", adresse=None, telephone=None, email=None, devise="XOF"
    )
    article = _make_article(admin_stack)

    stack, current_user = login_as("Vendeur")
    assert stack.permissions.has_permission("SALE_VIEW")
    assert not stack.permissions.has_permission("SETTINGS_VIEW")

    sale = _create_and_validate_sale(stack, article)
    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.entreprise_nom == "Boutique Test"
    assert receipt.username == current_user.username


def test_vendeur_can_generate_receipt_without_stock_movement_view(login_as) -> None:
    """Corollaire : l'heure du reçu est dérivée du mouvement VENTE en
    interne (accès direct au repository), jamais via SaleService.get_sale_movements
    qui exige STOCK_MOVEMENT_VIEW — absente du rôle Vendeur."""
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)

    stack, _ = login_as("Vendeur")
    assert not stack.permissions.has_permission("STOCK_MOVEMENT_VIEW")
    sale = _create_and_validate_sale(stack, article)

    receipt = stack.documents.build_sale_receipt(sale.id)
    assert receipt.heure is not None


# -- statut de la vente ----------------------------------------------------------------


def test_receipt_refused_for_brouillon(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    from app.services.sales.sale_service import VenteLigneInput

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])

    with pytest.raises(ValidationError):
        stack.documents.build_sale_receipt(sale.id)


def test_receipt_refused_for_annulee(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article)
    stack.sales.cancel_sale(sale.id)

    with pytest.raises(ValidationError):
        stack.documents.build_sale_receipt(sale.id)


def test_receipt_refused_for_unknown_sale(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.documents.build_sale_receipt(999999)


# -- contenu du reçu ------------------------------------------------------------------


def test_receipt_data_matches_sale(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article, quantite=Decimal("4"), prix=Decimal("200"))

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.numero == sale.numero
    assert receipt.date == sale.date
    assert receipt.total == Decimal("800.00") or receipt.total == Decimal("800")
    assert len(receipt.lignes) == 1
    line = receipt.lignes[0]
    assert line.article_reference == article.reference
    assert line.quantite == Decimal("4")
    assert line.prix_unitaire == Decimal("200")


def test_receipt_includes_effective_currency(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.update_config(nom="Société", adresse=None, telephone=None, email=None, devise="EUR")
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article)

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.devise == "EUR"


def test_receipt_includes_company_profile(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.update_config(
        nom="Boutique Étoile", adresse="12 rue X", telephone="0102030405", email="a@b.com", devise="XOF"
    )
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article)

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.entreprise_nom == "Boutique Étoile"
    assert receipt.entreprise_adresse == "12 rue X"
    assert receipt.entreprise_telephone == "0102030405"
    assert receipt.entreprise_email == "a@b.com"


def test_receipt_handles_missing_company_profile(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article)

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.entreprise_nom is None
    assert receipt.entreprise_adresse is None
    assert receipt.entreprise_logo_path is None


def test_receipt_heure_is_derived_from_vente_movement(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    before = datetime.now(timezone.utc).replace(microsecond=0)
    sale = _create_and_validate_sale(stack, article)
    after = datetime.now(timezone.utc)

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.heure is not None
    movements = stack.movements.list_movements(article_id=article.id, type_mouvement=TypeMouvement.VENTE)
    assert movements
    assert receipt.heure == movements[0].date_heure.time()
    assert before.time() <= receipt.heure <= after.time()


# -- intégrité des données --------------------------------------------------------------


def test_generating_receipt_does_not_change_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = _create_and_validate_sale(stack, article, quantite=Decimal("3"))

    stock_before = stack.articles.get_article(article.id).stock_actuel
    stack.documents.build_sale_receipt(sale.id)
    stack.documents.build_sale_receipt(sale.id)
    stock_after = stack.articles.get_article(article.id).stock_actuel

    assert stock_before == stock_after


def test_generating_receipt_does_not_create_movements(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article)

    count_before = len(stack.movements.list_movements(article_id=article.id))
    stack.documents.build_sale_receipt(sale.id)
    count_after = len(stack.movements.list_movements(article_id=article.id))

    assert count_before == count_after


def test_generating_receipt_does_not_change_sale_statut(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article)

    stack.documents.build_sale_receipt(sale.id)

    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.statut == sale.statut
    assert reloaded.total == sale.total


# -- client (lot Intégration du client dans les reçus et PDF) --------------------------


def test_receipt_includes_full_client_info(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client(
        "Jean Dupont", telephone="0102030405", email="jean@example.com", adresse="12 rue X"
    )
    sale = _create_and_validate_sale(stack, article, client_id=client.id)

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.client_nom == "Jean Dupont"
    assert receipt.client_telephone == "0102030405"
    assert receipt.client_email == "jean@example.com"
    assert receipt.client_adresse == "12 rue X"


def test_receipt_without_client_has_no_client_fields(login_as) -> None:
    """client_id = NULL -> reçu sans informations client (§ règle métier
    principale de ce lot)."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article)  # pas de client_id

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.client_nom is None
    assert receipt.client_telephone is None
    assert receipt.client_adresse is None
    assert receipt.client_email is None


def test_receipt_with_client_missing_optional_fields(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client minimal")  # aucun champ optionnel renseigné
    sale = _create_and_validate_sale(stack, article, client_id=client.id)

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.client_nom == "Client minimal"
    assert receipt.client_telephone is None
    assert receipt.client_adresse is None
    assert receipt.client_email is None


def test_receipt_client_accented_name_preserved(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Éric Ndiaye-Côté")
    sale = _create_and_validate_sale(stack, article, client_id=client.id)

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.client_nom == "Éric Ndiaye-Côté"


def test_receipt_still_available_for_deactivated_client(login_as) -> None:
    """§8 : un client désactivé associé à une vente historique doit
    continuer à fournir ses informations sur le reçu."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client historique", telephone="0102030405")
    sale = _create_and_validate_sale(stack, article, client_id=client.id)

    stack.clients.deactivate_client(client.id)

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.client_nom == "Client historique"
    assert receipt.client_telephone == "0102030405"


def test_receipt_generation_does_not_mutate_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client")
    sale = _create_and_validate_sale(stack, article, client_id=client.id)

    stack.documents.build_sale_receipt(sale.id)

    reloaded_client = stack.clients.get_client(client.id)
    assert reloaded_client.nom == "Client"
    assert reloaded_client.actif is True


def test_receipt_handles_invalid_client_reference_without_crash(login_as) -> None:
    """§9 : une référence client invalide ne peut normalement pas exister
    (FK ventes.client_id + PRAGMA foreign_keys=ON + ClientService sans
    suppression physique). Ce test simule malgré tout l'anomalie en cassant
    volontairement la référence en base (foreign_keys désactivées le temps
    de l'opération), pour prouver que ReceiptService ne plante jamais,
    n'invente aucun client, et retombe simplement sur le comportement
    « vente sans client »."""
    from app.config.settings import get_settings
    from app.db.session import session_scope
    from sqlalchemy import text

    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client éphémère")
    sale = _create_and_validate_sale(stack, article, client_id=client.id)

    settings = get_settings()
    with session_scope(settings) as session:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        session.execute(text("DELETE FROM clients WHERE id = :id"), {"id": client.id})
        session.execute(text("PRAGMA foreign_keys=ON"))

    receipt = stack.documents.build_sale_receipt(sale.id)

    assert receipt.client_nom is None
    assert receipt.client_telephone is None
    assert receipt.client_adresse is None
    assert receipt.client_email is None
    # La vente elle-même reste intacte (référence orpheline, mais aucune
    # donnée métier corrompue par la génération du reçu).
    reloaded_sale = stack.sales.get_sale(sale.id)
    assert reloaded_sale.total == sale.total


# -- ventes à crédit / paiements partiels (§5.8) --------------------------------------


def test_receipt_shows_full_payment_for_comptant_sale(login_as) -> None:
    from app.models.enums import StatutPaiement

    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 15), [])
    from app.services.sales.sale_service import VenteLigneInput
    sale = stack.sales.update_sale(sale.id, date(2026, 1, 15), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])
    validated = stack.sales.validate_sale(sale.id, paiement_initial=Decimal("300"))

    receipt = stack.documents.build_sale_receipt(validated.id)

    assert receipt.total == Decimal("300")
    assert receipt.montant_paye == Decimal("300")
    assert receipt.reste_a_payer == Decimal("0")
    assert receipt.statut_paiement == StatutPaiement.PAYEE


def test_receipt_shows_partial_payment(login_as) -> None:
    from app.models.enums import StatutPaiement
    from app.services.sales.sale_service import VenteLigneInput

    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 15), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])
    validated = stack.sales.validate_sale(sale.id, paiement_initial=Decimal("100"))

    receipt = stack.documents.build_sale_receipt(validated.id)

    assert receipt.total == Decimal("300")
    assert receipt.montant_paye == Decimal("100")
    assert receipt.reste_a_payer == Decimal("200")
    assert receipt.statut_paiement == StatutPaiement.PARTIELLEMENT_PAYEE


def test_build_payment_receipt_reflects_state_at_that_payment(login_as) -> None:
    from app.services.sales.sale_service import VenteLigneInput

    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client Crédit")
    sale = stack.sales.create_sale(
        date(2026, 1, 15), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )
    validated = stack.sales.validate_sale(sale.id)  # vente à crédit, aucun paiement initial
    stack.sales.record_payment(validated.id, Decimal("100"))
    updated = stack.sales.record_payment(validated.id, Decimal("50"))
    payments = stack.sales.list_payments(validated.id)
    assert len(payments) == 2

    first_receipt = stack.documents.build_payment_receipt(validated.id, payments[0].id)
    assert first_receipt.montant == Decimal("100")
    assert first_receipt.total_paye_apres == Decimal("100")
    assert first_receipt.reste_a_payer == Decimal("200")
    assert first_receipt.client_nom == "Client Crédit"

    second_receipt = stack.documents.build_payment_receipt(validated.id, payments[1].id)
    assert second_receipt.montant == Decimal("50")
    assert second_receipt.total_paye_apres == Decimal("150")
    assert second_receipt.reste_a_payer == Decimal("150")
    assert updated.montant_paye == Decimal("150")


def test_build_payment_receipt_unknown_payment_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = _create_and_validate_sale(stack, article)

    with pytest.raises(NotFoundError):
        stack.documents.build_payment_receipt(sale.id, 999999)
