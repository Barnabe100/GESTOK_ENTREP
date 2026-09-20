from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import StatutOperation, TypeMouvement
from app.services.sales.sale_service import VenteLigneInput
from app.services.stock.stock_service import StockService
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def _make_category(stack, nom="Boissons"):
    return stack.categories.create_category(nom)


def _make_article(stack, reference="ART-0001", stock_initial=Decimal("0"), category_id=None,
                   cmup=None, prix_vente=Decimal("150")):
    if category_id is None:
        category_id = _make_category(stack).id
    return stack.articles.create_article(
        reference, "Article de test", category_id, "unité",
        cmup if cmup is not None else Decimal("100"), prix_vente,
        Decimal("0"), stock_initial=stock_initial,
    )


# -- création -----------------------------------------------------------------


def test_create_draft_sale(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("10"), Decimal("150"))])

    assert sale.statut == StatutOperation.BROUILLON
    assert sale.numero == "VNT-000001"


def test_create_sale_with_multiple_lines(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", stock_initial=Decimal("50"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-2", stock_initial=Decimal("50"), category_id=category.id)

    sale = stack.sales.create_sale(
        date(2026, 1, 1),
        [
            VenteLigneInput(article_1.id, Decimal("2"), Decimal("100")),
            VenteLigneInput(article_2.id, Decimal("3"), Decimal("200")),
        ],
    )

    assert len(sale.lignes) == 2


def test_create_sale_computes_correct_total_using_decimal(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", stock_initial=Decimal("50"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-2", stock_initial=Decimal("50"), category_id=category.id)

    sale = stack.sales.create_sale(
        date(2026, 1, 1),
        [
            VenteLigneInput(article_1.id, Decimal("2"), Decimal("100.50")),
            VenteLigneInput(article_2.id, Decimal("3"), Decimal("200.25")),
        ],
    )

    assert isinstance(sale.total, Decimal)
    # 2*100.50 + 3*200.25 = 201.00 + 600.75 = 801.75
    assert sale.total == Decimal("801.75")
    assert sale.lignes[0].sous_total == Decimal("201.00")
    assert sale.lignes[1].sous_total == Decimal("600.75")


def test_create_sale_rejects_unknown_article(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(999999, Decimal("1"), Decimal("100"))])


def test_create_sale_rejects_inactive_article(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    stack.articles.deactivate_article(article.id)

    with pytest.raises(ValidationError):
        stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("100"))])


def test_create_sale_rejects_zero_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    with pytest.raises(ValidationError):
        stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("0"), Decimal("100"))])


def test_create_sale_rejects_negative_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    with pytest.raises(ValidationError):
        stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("-1"), Decimal("100"))])


def test_create_sale_auto_generates_sequential_numero(login_as) -> None:
    stack, _ = login_as("Administrateur")

    first = stack.sales.create_sale(date(2026, 1, 1), [])
    second = stack.sales.create_sale(date(2026, 1, 1), [])

    assert first.numero == "VNT-000001"
    assert second.numero == "VNT-000002"


# -- stock ----------------------------------------------------------------------


def test_validate_simple_sale_reduces_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("80")


def test_validate_sale_creates_vente_movement(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("500"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("800"))])
    stack.sales.validate_sale(sale.id)

    movements = stack.sales.get_sale_movements(sale.id)
    assert len(movements) == 1
    movement = movements[0]
    assert movement.type == TypeMouvement.VENTE
    assert movement.quantite == Decimal("-20")
    assert movement.stock_avant == Decimal("100")
    assert movement.stock_apres == Decimal("80")


def test_validate_sale_does_not_recompute_cmup(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("500"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("800"))])
    stack.sales.validate_sale(sale.id)

    updated = stack.articles.get_article(article.id)
    assert updated.cout_moyen_pondere == Decimal("500.00")


def test_validate_sale_keeps_invoiced_price_not_catalog_price(login_as) -> None:
    """Le prix facturé conservé sur la ligne ne doit jamais être recalculé à
    partir du prix catalogue actuel de l'article, même si celui-ci change
    entre la création du brouillon et la validation."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"), prix_vente=Decimal("150"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("10"), Decimal("150"))])

    stack.articles.update_article(
        article.id, article.reference, article.designation, article.category_id, article.unite,
        article.prix_achat, Decimal("999"), article.stock_min,
    )

    validated = stack.sales.validate_sale(sale.id)
    assert validated.lignes[0].prix_unitaire == Decimal("150.00")


def test_validate_sale_refused_when_stock_insufficient(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("150"))])

    with pytest.raises(ValidationError):
        stack.sales.validate_sale(sale.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("10")
    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.statut == StatutOperation.BROUILLON


def test_validate_sale_stock_exactly_equal_to_quantity_is_allowed(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("20"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("0")


def test_validate_sale_with_multiple_lines(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", stock_initial=Decimal("50"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-2", stock_initial=Decimal("50"), category_id=category.id)

    sale = stack.sales.create_sale(
        date(2026, 1, 1),
        [
            VenteLigneInput(article_1.id, Decimal("10"), Decimal("100")),
            VenteLigneInput(article_2.id, Decimal("5"), Decimal("200")),
        ],
    )
    stack.sales.validate_sale(sale.id)

    assert stack.articles.get_article(article_1.id).stock_actuel == Decimal("40")
    assert stack.articles.get_article(article_2.id).stock_actuel == Decimal("45")


# -- transaction ------------------------------------------------------------------


def test_validate_sale_rolls_back_entirely_on_mid_transaction_error(login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-TX-1", stock_initial=Decimal("50"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-TX-2", stock_initial=Decimal("50"), category_id=category.id)

    sale = stack.sales.create_sale(
        date(2026, 1, 1),
        [
            VenteLigneInput(article_1.id, Decimal("10"), Decimal("100")),
            VenteLigneInput(article_2.id, Decimal("5"), Decimal("200")),
        ],
    )

    original_apply_movement = StockService.apply_movement
    call_count = {"n": 0}

    def _flaky_apply_movement(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("Panne simulée en cours de transaction")
        return original_apply_movement(self, *args, **kwargs)

    monkeypatch.setattr(StockService, "apply_movement", _flaky_apply_movement)

    with pytest.raises(RuntimeError):
        stack.sales.validate_sale(sale.id)

    monkeypatch.setattr(StockService, "apply_movement", original_apply_movement)

    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.statut == StatutOperation.BROUILLON

    assert stack.articles.get_article(article_1.id).stock_actuel == Decimal("50")
    assert stack.articles.get_article(article_2.id).stock_actuel == Decimal("50")
    assert stack.sales.get_sale_movements(sale.id) == []


# -- workflow -----------------------------------------------------------------------


def test_sale_workflow_brouillon_to_validee(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    assert sale.statut == StatutOperation.BROUILLON

    validated = stack.sales.validate_sale(sale.id)
    assert validated.statut == StatutOperation.VALIDEE


def test_cannot_update_a_validated_sale(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    with pytest.raises(ConflictError):
        stack.sales.update_sale(sale.id, date(2026, 1, 2), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])


def test_cannot_revalidate_a_validated_sale(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    with pytest.raises(ConflictError):
        stack.sales.validate_sale(sale.id)


def test_cannot_delete_a_validated_sale(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    with pytest.raises(ConflictError):
        stack.sales.delete_sale(sale.id)


def test_can_delete_a_draft_sale(login_as) -> None:
    stack, _ = login_as("Administrateur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [])

    stack.sales.delete_sale(sale.id)

    with pytest.raises(NotFoundError):
        stack.sales.get_sale(sale.id)


def test_validate_sale_requires_at_least_one_line(login_as) -> None:
    stack, _ = login_as("Administrateur")

    sale = stack.sales.create_sale(date(2026, 1, 1), [])

    with pytest.raises(ValidationError):
        stack.sales.validate_sale(sale.id)


# -- annulation -----------------------------------------------------------------


def test_cancel_sale_restores_stock_and_creates_annulation_movement(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("80")

    cancelled = stack.sales.cancel_sale(sale.id)
    assert cancelled.statut == StatutOperation.ANNULEE

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("100")

    movements = stack.sales.get_sale_movements(sale.id)
    assert len(movements) == 2
    assert movements[0].type == TypeMouvement.VENTE
    assert movements[1].type == TypeMouvement.ANNULATION
    assert movements[1].quantite == Decimal("20")


def test_cancel_sale_keeps_original_sale(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)
    stack.sales.cancel_sale(sale.id)

    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.numero == sale.numero
    assert len(reloaded.lignes) == 1


def test_cannot_cancel_a_sale_twice(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)
    stack.sales.cancel_sale(sale.id)

    with pytest.raises(ConflictError):
        stack.sales.cancel_sale(sale.id)


def test_cancel_sale_requires_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("100"))

    stack, _ = login_as("Vendeur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("20"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    with pytest.raises(PermissionDeniedError):
        stack.sales.cancel_sale(sale.id)


# -- permissions ----------------------------------------------------------------


def test_view_permission_enforced(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")

    with pytest.raises(PermissionDeniedError):
        stack.sales.list_sales()


def test_create_permission_enforced(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")

    with pytest.raises(PermissionDeniedError):
        stack.sales.create_sale(date(2026, 1, 1), [])


def test_update_permission_enforced(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    sale = admin_stack.sales.create_sale(date(2026, 1, 1), [])

    stack, _ = login_as("Gestionnaire de stock")
    with pytest.raises(PermissionDeniedError):
        stack.sales.update_sale(sale.id, date(2026, 1, 1), [])


def test_validate_permission_enforced(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("50"))
    sale = admin_stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])

    stack, _ = login_as("Gestionnaire de stock")
    with pytest.raises(PermissionDeniedError):
        stack.sales.validate_sale(sale.id)


def test_vendeur_can_create_update_and_validate_but_not_cancel(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("50"))

    stack, _ = login_as("Vendeur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.update_sale(sale.id, date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("6"), Decimal("150"))])
    validated = stack.sales.validate_sale(sale.id)
    assert validated.statut == StatutOperation.VALIDEE

    with pytest.raises(PermissionDeniedError):
        stack.sales.cancel_sale(sale.id)


def test_administrateur_has_full_access(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.update_sale(sale.id, date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("6"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)
    cancelled = stack.sales.cancel_sale(sale.id)
    assert cancelled.statut == StatutOperation.ANNULEE


# -- ventes à crédit et paiements partiels (§5) ---------------------------------------


from app.models.enums import StatutPaiement  # noqa: E402


def _create_validated_sale(stack, article, quantite=Decimal("2"), prix=Decimal("150"), client_id=None, paiement_initial=Decimal("0")):
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, quantite, prix)], client_id=client_id)
    return stack.sales.validate_sale(sale.id, paiement_initial)


def test_comptant_sale_is_paid_in_full_at_validation(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("300"))

    assert validated.total == Decimal("300")
    assert validated.montant_paye == Decimal("300")
    assert validated.reste_a_payer == Decimal("0")
    assert validated.statut_paiement == StatutPaiement.PAYEE


def test_sale_without_payment_is_non_payee(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    validated = _create_validated_sale(stack, article)

    assert validated.montant_paye == Decimal("0")
    assert validated.reste_a_payer == Decimal("300")
    assert validated.statut_paiement == StatutPaiement.NON_PAYEE


def test_credit_sale_with_partial_initial_payment(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("100"))

    assert validated.montant_paye == Decimal("100")
    assert validated.reste_a_payer == Decimal("200")
    assert validated.statut_paiement == StatutPaiement.PARTIELLEMENT_PAYEE


def test_initial_payment_exceeding_total_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])

    with pytest.raises(ValidationError):
        stack.sales.validate_sale(sale.id, Decimal("301"))


def test_record_payment_after_validation(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article)

    updated = stack.sales.record_payment(validated.id, Decimal("120"))

    assert updated.montant_paye == Decimal("120")
    assert updated.reste_a_payer == Decimal("180")
    assert updated.statut_paiement == StatutPaiement.PARTIELLEMENT_PAYEE


def test_multiple_successive_payments_accumulate(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article)  # total = 300

    stack.sales.record_payment(validated.id, Decimal("40"))
    stack.sales.record_payment(validated.id, Decimal("30"))
    final = stack.sales.record_payment(validated.id, Decimal("30"))

    assert final.montant_paye == Decimal("100")
    assert final.reste_a_payer == Decimal("200")
    assert final.statut_paiement == StatutPaiement.PARTIELLEMENT_PAYEE


def test_final_payment_transitions_to_payee(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("40"))  # total 300

    stack.sales.record_payment(validated.id, Decimal("60"))
    final = stack.sales.record_payment(validated.id, Decimal("200"))

    assert final.montant_paye == Decimal("300")
    assert final.reste_a_payer == Decimal("0")
    assert final.statut_paiement == StatutPaiement.PAYEE


def test_payment_exceeding_remaining_balance_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("100"))  # reste 200

    with pytest.raises(ValidationError):
        stack.sales.record_payment(validated.id, Decimal("201"))

    # Rien n'a été enregistré : aucune modification malgré le refus.
    reloaded = stack.sales.get_sale(validated.id)
    assert reloaded.montant_paye == Decimal("100")


def test_remaining_balance_never_negative(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("300"))

    assert validated.reste_a_payer == Decimal("0")
    assert validated.reste_a_payer >= Decimal("0")


def test_payment_amounts_are_decimal(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"), prix_vente=Decimal("33.33"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("3"), Decimal("33.33"))])
    validated = stack.sales.validate_sale(sale.id)  # total = 99.99

    updated = stack.sales.record_payment(validated.id, Decimal("33.33"))

    assert isinstance(updated.montant_paye, Decimal)
    assert isinstance(updated.reste_a_payer, Decimal)
    assert updated.montant_paye == Decimal("33.33")
    assert updated.reste_a_payer == Decimal("66.66")


def test_client_receivable_summary_aggregates_validated_sales(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    client = stack.clients.create_client("Client Créance")

    _create_validated_sale(stack, article, quantite=Decimal("2"), client_id=client.id, paiement_initial=Decimal("100"))
    v2 = _create_validated_sale(stack, article, quantite=Decimal("1"), client_id=client.id)
    stack.sales.record_payment(v2.id, Decimal("50"))

    summary = stack.sales.get_client_receivable_summary(client.id)

    assert summary.total_ventes == Decimal("450")  # 300 + 150
    assert summary.total_paye == Decimal("150")  # 100 + 50
    assert summary.total_reste_a_payer == Decimal("300")


def test_client_receivable_summary_excludes_cancelled_sales(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    client = stack.clients.create_client("Client Créance 2")

    validated = _create_validated_sale(stack, article, client_id=client.id)
    stack.sales.cancel_sale(validated.id)

    summary = stack.sales.get_client_receivable_summary(client.id)

    assert summary.total_ventes == Decimal("0")
    assert summary.total_paye == Decimal("0")


def test_payment_history_preserves_each_payment_separately(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article)

    stack.sales.record_payment(validated.id, Decimal("40"), mode_paiement="Espèces")
    stack.sales.record_payment(validated.id, Decimal("30"), mode_paiement="Mobile Money", reference="MM-123")

    history = stack.sales.list_payments(validated.id)

    assert len(history) == 2
    assert history[0].montant == Decimal("40")
    assert history[0].mode_paiement == "Espèces"
    assert history[1].montant == Decimal("30")
    assert history[1].reference == "MM-123"


def test_payment_creates_audit_entry(login_as) -> None:
    from app.config.settings import get_settings
    from app.db.session import session_scope
    from app.models.audit import AuditLog

    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article)

    stack.sales.record_payment(validated.id, Decimal("50"))

    with session_scope(get_settings()) as session:
        entries = session.query(AuditLog).filter_by(action="SALE_PAYMENT_CREATE", entite_id=validated.id).all()
    assert len(entries) == 1
    assert entries[0].resultat.value == "SUCCES"


def test_receipt_of_partially_paid_sale_still_available(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("100"))

    receipt = stack.documents.build_sale_receipt(validated.id)

    assert receipt.montant_paye == Decimal("100")
    assert receipt.reste_a_payer == Decimal("200")


def test_payment_on_fully_paid_sale_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("300"))

    with pytest.raises(ConflictError):
        stack.sales.record_payment(validated.id, Decimal("1"))


def test_recording_payment_does_not_change_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article, quantite=Decimal("2"))  # stock -> 48 à la validation
    stock_after_validation = stack.articles.get_article(article.id).stock_actuel

    stack.sales.record_payment(validated.id, Decimal("100"))

    assert stack.articles.get_article(article.id).stock_actuel == stock_after_validation


def test_vendeur_can_record_payment(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("50"))

    stack, _ = login_as("Vendeur")
    validated = _create_validated_sale(stack, article)

    updated = stack.sales.record_payment(validated.id, Decimal("50"))
    assert updated.montant_paye == Decimal("50")


def test_gestionnaire_stock_cannot_record_payment(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(admin_stack, article)

    stack, _ = login_as("Gestionnaire de stock")
    with pytest.raises(PermissionDeniedError):
        stack.sales.record_payment(validated.id, Decimal("50"))


def test_consultation_cannot_record_payment(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(admin_stack, article)

    stack, _ = login_as("Consultation")
    with pytest.raises(PermissionDeniedError):
        stack.sales.record_payment(validated.id, Decimal("50"))


def test_payment_history_survives_cancellation(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("100"))

    stack.sales.cancel_sale(validated.id)

    history = stack.sales.list_payments(validated.id)
    assert len(history) == 1
    assert history[0].montant == Decimal("100")
    reloaded = stack.sales.get_sale(validated.id)
    assert reloaded.montant_paye == Decimal("100")  # figé, jamais effacé par l'annulation
    assert reloaded.statut == StatutOperation.ANNULEE


# -- cas limites -----------------------------------------------------------------------


def test_zero_total_sale_is_payee_by_construction(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("0"))])

    validated = stack.sales.validate_sale(sale.id)

    assert validated.total == Decimal("0")
    assert validated.montant_paye == Decimal("0")
    assert validated.reste_a_payer == Decimal("0")
    assert validated.statut_paiement == StatutPaiement.PAYEE


def test_minimal_payment_amount_accepted(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article)

    updated = stack.sales.record_payment(validated.id, Decimal("0.01"))

    assert updated.montant_paye == Decimal("0.01")
    assert updated.statut_paiement == StatutPaiement.PARTIELLEMENT_PAYEE


def test_payment_exactly_matching_remaining_balance(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article, paiement_initial=Decimal("100"))  # reste 200

    final = stack.sales.record_payment(validated.id, Decimal("200"))

    assert final.montant_paye == Decimal("300")
    assert final.reste_a_payer == Decimal("0")
    assert final.statut_paiement == StatutPaiement.PAYEE


def test_zero_or_negative_payment_amount_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article)

    with pytest.raises(ValidationError):
        stack.sales.record_payment(validated.id, Decimal("0"))
    with pytest.raises(ValidationError):
        stack.sales.record_payment(validated.id, Decimal("-10"))


def test_payment_on_draft_sale_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])

    with pytest.raises(ConflictError):
        stack.sales.record_payment(sale.id, Decimal("10"))


def test_payment_on_cancelled_sale_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    validated = _create_validated_sale(stack, article)
    stack.sales.cancel_sale(validated.id)

    with pytest.raises(ConflictError):
        stack.sales.record_payment(validated.id, Decimal("10"))
