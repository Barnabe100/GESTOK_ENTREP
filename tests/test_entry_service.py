from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import StatutOperation, TypeMouvement
from app.services.entries.entry_service import EntreeLigneInput
from app.services.stock.stock_service import StockService
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def _make_supplier(stack, nom="Fournisseur Test"):
    return stack.suppliers.create_supplier(nom)


def _make_category(stack, nom="Boissons"):
    return stack.categories.create_category(nom)


def _make_article(stack, reference="ART-0001", stock_initial=Decimal("0"), category_id=None):
    if category_id is None:
        category_id = _make_category(stack).id
    return stack.articles.create_article(
        reference, "Article de test", category_id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=stock_initial,
    )


# -- entrée simple : stock 0 -> 10 -------------------------------------------------


def test_simple_entry_from_zero_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )
    stack.entries.validate_entry(entry.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("10")


# -- plusieurs entrées : évolution du stock ----------------------------------------


def test_multiple_entries_stock_evolution(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)

    for quantite in (Decimal("10"), Decimal("5"), Decimal("20")):
        entry = stack.entries.create_entry(
            supplier.id, date(2026, 1, 1),
            [EntreeLigneInput(article.id, quantite, Decimal("100"))],
        )
        stack.entries.validate_entry(entry.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("35")


# -- CMUP ---------------------------------------------------------------------------


def test_cmup_matches_worked_example_through_validate_entry(login_as) -> None:
    """Stock 100 @ 1000, entrée 50 @ 1200 -> CMUP 1066.67 (exemple du cahier des charges)."""
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    category = _make_category(stack)
    article = stack.articles.create_article(
        "ART-CMUP", "Article CMUP", category.id, "unité",
        Decimal("1000"), Decimal("1500"), Decimal("0"), stock_initial=Decimal("100"),
    )
    # Le CMUP initial (prix d'achat à la création) doit être ajusté à 1000 pour l'exemple.
    assert article.cout_moyen_pondere == Decimal("1000.00")

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("50"), Decimal("1200"))],
    )
    stack.entries.validate_entry(entry.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("150")
    assert updated.cout_moyen_pondere == Decimal("1066.67")


def test_cmup_on_zero_initial_stock_equals_purchase_price(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack, stock_initial=Decimal("0"))

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("500"))],
    )
    stack.entries.validate_entry(entry.id)

    updated = stack.articles.get_article(article.id)
    assert updated.cout_moyen_pondere == Decimal("500.00")


# -- entrée en brouillon : stock inchangé -------------------------------------------


def test_draft_entry_does_not_modify_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack, stock_initial=Decimal("5"))

    stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("5")


def test_updating_a_draft_entry_does_not_modify_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack, stock_initial=Decimal("5"))

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )
    stack.entries.update_entry(
        entry.id, supplier.id, date(2026, 1, 2),
        [EntreeLigneInput(article.id, Decimal("25"), Decimal("110"))],
    )

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("5")


def test_cannot_update_a_validated_entry(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )
    stack.entries.validate_entry(entry.id)

    with pytest.raises(ConflictError):
        stack.entries.update_entry(
            entry.id, supplier.id, date(2026, 1, 2),
            [EntreeLigneInput(article.id, Decimal("99"), Decimal("100"))],
        )


# -- validation : mouvement créé + stock modifié + CMUP recalculé -------------------


def test_validate_entry_creates_movement_updates_stock_and_recomputes_cmup(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack, stock_initial=Decimal("0"))

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("500"))],
    )
    validated = stack.entries.validate_entry(entry.id)
    assert validated.statut == StatutOperation.VALIDEE

    movements = stack.entries.get_entry_movements(entry.id)
    assert len(movements) == 1
    movement = movements[0]
    assert movement.type == TypeMouvement.ENTREE
    assert movement.quantite == Decimal("10")
    assert movement.stock_avant == Decimal("0")
    assert movement.stock_apres == Decimal("10")

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("10")
    assert updated.cout_moyen_pondere == Decimal("500.00")


def test_validate_entry_requires_at_least_one_line(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)

    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [])

    with pytest.raises(ValidationError):
        stack.entries.validate_entry(entry.id)


def test_validate_entry_only_allowed_from_brouillon(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )
    stack.entries.validate_entry(entry.id)

    with pytest.raises(ConflictError):
        stack.entries.validate_entry(entry.id)


# -- transaction : rollback intégral en cas d'erreur en cours d'opération -----------


def test_validate_entry_rolls_back_entirely_on_mid_transaction_error(login_as, monkeypatch) -> None:
    """Provoque volontairement une erreur sur la 2e ligne et vérifie que
    l'opération entière est annulée : ni le stock ni le statut ne changent,
    aucun mouvement n'est créé pour la 1ère ligne pourtant traitée avant
    l'échec (§4 du cahier des charges de cette phase)."""
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-TX-1", stock_initial=Decimal("0"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-TX-2", stock_initial=Decimal("0"), category_id=category.id)

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [
            EntreeLigneInput(article_1.id, Decimal("10"), Decimal("100")),
            EntreeLigneInput(article_2.id, Decimal("5"), Decimal("50")),
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
        stack.entries.validate_entry(entry.id)

    monkeypatch.setattr(StockService, "apply_movement", original_apply_movement)

    # Rien n'a été modifié : ni le statut, ni le stock des deux articles, ni
    # le mouvement de la 1ère ligne (pourtant traitée avec succès avant l'échec).
    reloaded_entry = stack.entries.get_entry(entry.id)
    assert reloaded_entry.statut == StatutOperation.BROUILLON

    reloaded_article_1 = stack.articles.get_article(article_1.id)
    reloaded_article_2 = stack.articles.get_article(article_2.id)
    assert reloaded_article_1.stock_actuel == Decimal("0")
    assert reloaded_article_2.stock_actuel == Decimal("0")

    assert stack.entries.get_entry_movements(entry.id) == []


# -- annulation -----------------------------------------------------------------


def test_cancel_entry_authorized(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack, stock_initial=Decimal("0"))

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )
    stack.entries.validate_entry(entry.id)

    cancelled = stack.entries.cancel_entry(entry.id)
    assert cancelled.statut == StatutOperation.ANNULEE

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("0")

    movements = stack.entries.get_entry_movements(entry.id)
    assert len(movements) == 2
    assert movements[1].type == TypeMouvement.ANNULATION
    assert movements[1].quantite == Decimal("-10")


def test_cancel_entry_refused_when_it_would_cause_negative_stock(login_as, initialized_db) -> None:
    """Le stock a été partiellement « consommé » entre-temps (simulé ici par un
    ajustement, les Sorties étant hors périmètre de cette phase) : l'annulation
    doit être intégralement refusée, sans modifier aucune donnée."""
    stack, current_user = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack, stock_initial=Decimal("0"))

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )
    stack.entries.validate_entry(entry.id)

    # Consommation externe simulée : il ne reste que 4 unités, l'annulation
    # complète de l'entrée (-10) ferait donc passer le stock à -6.
    from app.db.session import session_scope
    from app.repositories.article_repository import ArticleRepository

    with session_scope(initialized_db) as session:
        repo = ArticleRepository(session)
        db_article = repo.get_by_id(article.id)
        StockService().apply_movement(
            session, db_article, TypeMouvement.AJUSTEMENT, Decimal("-6"), user_id=current_user.id
        )

    with pytest.raises(ValidationError):
        stack.entries.cancel_entry(entry.id)

    # Rien n'a été modifié : l'entrée reste validée, le stock reste à 4.
    reloaded_entry = stack.entries.get_entry(entry.id)
    assert reloaded_entry.statut == StatutOperation.VALIDEE

    reloaded_article = stack.articles.get_article(article.id)
    assert reloaded_article.stock_actuel == Decimal("4")


def test_cancel_entry_only_allowed_from_validee(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )

    with pytest.raises(ConflictError):
        stack.entries.cancel_entry(entry.id)


# -- permissions ----------------------------------------------------------------


def test_gestionnaire_de_stock_can_create_and_validate_but_not_cancel(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")
    supplier = _make_supplier(stack)
    article = _make_article(stack)

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )
    stack.entries.validate_entry(entry.id)

    with pytest.raises(PermissionDeniedError):
        stack.entries.cancel_entry(entry.id)


def test_vendeur_cannot_view_or_create_entries(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.entries.list_entries()

    with pytest.raises(PermissionDeniedError):
        stack.entries.create_entry(1, date(2026, 1, 1), [])


def test_consultation_cannot_view_or_create_entries_but_can_view_movements(login_as) -> None:
    """Consultation reçoit STOCK_MOVEMENT_VIEW mais pas STOCK_ENTRY_VIEW (matrice
    de permissions validée, cf. app/db/seed.py)."""
    admin_stack, _ = login_as("Administrateur")
    supplier = _make_supplier(admin_stack)
    article = _make_article(admin_stack)
    entry = admin_stack.entries.create_entry(
        supplier.id, date(2026, 1, 1),
        [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))],
    )
    admin_stack.entries.validate_entry(entry.id)

    stack, _ = login_as("Consultation")

    with pytest.raises(PermissionDeniedError):
        stack.entries.list_entries()

    with pytest.raises(PermissionDeniedError):
        stack.entries.create_entry(1, date(2026, 1, 1), [])

    movements = stack.entries.get_entry_movements(entry.id)
    assert len(movements) == 1


# -- validations diverses --------------------------------------------------------


def test_create_entry_rejects_non_positive_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)

    with pytest.raises(ValidationError):
        stack.entries.create_entry(
            supplier.id, date(2026, 1, 1),
            [EntreeLigneInput(article.id, Decimal("0"), Decimal("100"))],
        )


def test_create_entry_unknown_supplier_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.entries.create_entry(999999, date(2026, 1, 1), [])


def test_create_entry_auto_generates_sequential_numero(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)

    first = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [])
    second = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [])

    assert first.numero == "ENT-000001"
    assert second.numero == "ENT-000002"
