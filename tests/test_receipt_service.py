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


def _create_and_validate_sale(stack, article, quantite=Decimal("3"), prix=Decimal("150")):
    from app.services.sales.sale_service import VenteLigneInput

    sale = stack.sales.create_sale(date(2026, 1, 15), [VenteLigneInput(article.id, quantite, prix)])
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
