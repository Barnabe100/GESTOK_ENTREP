import inspect
from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import StatutInventaire, TypeMouvement
from app.services.inventory.inventory_service import InventaireLigneInput, InventoryService
from app.services.stock.stock_service import StockService
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def _make_category(stack, nom="Boissons"):
    return stack.categories.create_category(nom)


def _make_article(stack, reference="ART-0001", stock_initial=Decimal("0"), category_id=None,
                   cmup=None):
    if category_id is None:
        category_id = _make_category(stack).id
    return stack.articles.create_article(
        reference, "Article de test", category_id, "unité",
        cmup if cmup is not None else Decimal("100"), Decimal("150"),
        Decimal("0"), stock_initial=stock_initial,
    )


# -- création -----------------------------------------------------------------


def test_create_draft_inventory(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("48"))])

    assert inv.statut == StatutInventaire.BROUILLON
    assert inv.numero == "INV-000001"


def test_create_inventory_with_multiple_lines(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", stock_initial=Decimal("50"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-2", stock_initial=Decimal("20"), category_id=category.id)

    inv = stack.inventory.create_inventory(
        date(2026, 1, 1),
        [
            InventaireLigneInput(article_1.id, Decimal("48")),
            InventaireLigneInput(article_2.id, Decimal("25")),
        ],
    )

    assert len(inv.lignes) == 2


def test_create_inventory_captures_stock_theorique_from_current_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    assert inv.lignes[0].stock_theorique == Decimal("100")
    assert inv.lignes[0].stock_physique == Decimal("97")


def test_create_inventory_accepts_zero_counted_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("0"))])

    assert inv.lignes[0].stock_physique == Decimal("0")
    assert inv.lignes[0].ecart == Decimal("-10")


def test_create_inventory_rejects_negative_counted_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))

    with pytest.raises(ValidationError):
        stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("-1"))])


def test_create_inventory_rejects_unknown_article(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(999999, Decimal("5"))])


def test_create_inventory_rejects_inactive_article(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))
    stack.articles.deactivate_article(article.id)

    with pytest.raises(ValidationError):
        stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("5"))])


def test_create_inventory_auto_generates_sequential_numero(login_as) -> None:
    stack, _ = login_as("Administrateur")

    first = stack.inventory.create_inventory(date(2026, 1, 1), [])
    second = stack.inventory.create_inventory(date(2026, 1, 1), [])

    assert first.numero == "INV-000001"
    assert second.numero == "INV-000002"


# -- calcul des écarts ----------------------------------------------------------


def test_ecart_positive(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("105"))])

    assert inv.lignes[0].ecart == Decimal("5")


def test_ecart_negative(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    assert inv.lignes[0].ecart == Decimal("-3")


def test_ecart_zero(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("100"))])

    assert inv.lignes[0].ecart == Decimal("0")


def test_ecart_computed_correctly_for_multiple_lines(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", stock_initial=Decimal("100"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-2", stock_initial=Decimal("50"), category_id=category.id)
    article_3 = _make_article(stack, reference="ART-3", stock_initial=Decimal("10"), category_id=category.id)

    inv = stack.inventory.create_inventory(
        date(2026, 1, 1),
        [
            InventaireLigneInput(article_1.id, Decimal("105")),
            InventaireLigneInput(article_2.id, Decimal("47")),
            InventaireLigneInput(article_3.id, Decimal("10")),
        ],
    )

    ecarts = {l.article_reference: l.ecart for l in inv.lignes}
    assert ecarts["ART-1"] == Decimal("5")
    assert ecarts["ART-2"] == Decimal("-3")
    assert ecarts["ART-3"] == Decimal("0")


# -- validation -------------------------------------------------------------------


def test_validate_inventory_with_positive_ecart_increases_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("500"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("105"))])
    stack.inventory.validate_inventory(inv.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("105")
    assert updated.cout_moyen_pondere == Decimal("500.00")  # jamais recalculé


def test_validate_inventory_with_negative_ecart_decreases_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("500"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])
    stack.inventory.validate_inventory(inv.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("97")
    assert updated.cout_moyen_pondere == Decimal("500.00")  # jamais recalculé


def test_validate_inventory_with_zero_ecart_creates_no_movement(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("100"))])
    stack.inventory.validate_inventory(inv.id)

    assert stack.articles.get_article(article.id).stock_actuel == Decimal("100")
    assert stack.inventory.get_inventory_movements(inv.id) == []


def test_validate_inventory_creates_ajustement_movement(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("500"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])
    stack.inventory.validate_inventory(inv.id)

    movements = stack.inventory.get_inventory_movements(inv.id)
    assert len(movements) == 1
    movement = movements[0]
    assert movement.type == TypeMouvement.AJUSTEMENT
    assert movement.quantite == Decimal("-3")
    assert movement.stock_avant == Decimal("100")
    assert movement.stock_apres == Decimal("97")
    assert movement.cout_unitaire == Decimal("500.00")


def test_validate_inventory_with_multiple_lines(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", stock_initial=Decimal("100"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-2", stock_initial=Decimal("50"), category_id=category.id)

    inv = stack.inventory.create_inventory(
        date(2026, 1, 1),
        [
            InventaireLigneInput(article_1.id, Decimal("105")),
            InventaireLigneInput(article_2.id, Decimal("47")),
        ],
    )
    stack.inventory.validate_inventory(inv.id)

    assert stack.articles.get_article(article_1.id).stock_actuel == Decimal("105")
    assert stack.articles.get_article(article_2.id).stock_actuel == Decimal("47")


def test_validate_inventory_refused_when_it_would_cause_negative_stock(login_as) -> None:
    """Le stock théorique figé (100) date de la création du brouillon ; le
    stock réel a chuté à 2 entre-temps (une sortie a été validée) : appliquer
    l'écart figé (-97) ferait passer le stock réel à -95, ce qui doit être
    refusé sans aucune modification."""
    stack, _ = login_as("Administrateur")
    motif = stack.exit_reasons.create_exit_reason("Perte")
    article = _make_article(stack, stock_initial=Decimal("100"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("3"))])
    assert inv.lignes[0].ecart == Decimal("-97")

    from app.services.exits.exit_service import SortieLigneInput

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("98"))])
    stack.exits.validate_exit(exit_.id)
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("2")

    with pytest.raises(ValidationError):
        stack.inventory.validate_inventory(inv.id)

    assert stack.articles.get_article(article.id).stock_actuel == Decimal("2")
    reloaded = stack.inventory.get_inventory(inv.id)
    assert reloaded.statut == StatutInventaire.BROUILLON
    assert stack.inventory.get_inventory_movements(inv.id) == []


def test_validate_inventory_requires_at_least_one_line(login_as) -> None:
    stack, _ = login_as("Administrateur")

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [])

    with pytest.raises(ValidationError):
        stack.inventory.validate_inventory(inv.id)


# -- transaction ------------------------------------------------------------------


def test_validate_inventory_rolls_back_entirely_on_mid_transaction_error(login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-TX-1", stock_initial=Decimal("100"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-TX-2", stock_initial=Decimal("50"), category_id=category.id)

    inv = stack.inventory.create_inventory(
        date(2026, 1, 1),
        [
            InventaireLigneInput(article_1.id, Decimal("90")),
            InventaireLigneInput(article_2.id, Decimal("40")),
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
        stack.inventory.validate_inventory(inv.id)

    monkeypatch.setattr(StockService, "apply_movement", original_apply_movement)

    reloaded = stack.inventory.get_inventory(inv.id)
    assert reloaded.statut == StatutInventaire.BROUILLON

    assert stack.articles.get_article(article_1.id).stock_actuel == Decimal("100")
    assert stack.articles.get_article(article_2.id).stock_actuel == Decimal("50")
    assert stack.inventory.get_inventory_movements(inv.id) == []


# -- workflow -----------------------------------------------------------------------


def test_inventory_workflow_brouillon_to_valide(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("48"))])
    assert inv.statut == StatutInventaire.BROUILLON

    validated = stack.inventory.validate_inventory(inv.id)
    assert validated.statut == StatutInventaire.VALIDE


def test_cannot_update_a_validated_inventory(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("48"))])
    stack.inventory.validate_inventory(inv.id)

    with pytest.raises(ConflictError):
        stack.inventory.update_inventory(inv.id, date(2026, 1, 2), [InventaireLigneInput(article.id, Decimal("1"))])


def test_cannot_revalidate_a_validated_inventory(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("48"))])
    stack.inventory.validate_inventory(inv.id)

    with pytest.raises(ConflictError):
        stack.inventory.validate_inventory(inv.id)


def test_no_deletion_mechanism_exists_for_inventories(login_as) -> None:
    """Aucun inventaire, brouillon ou validé, ne peut être supprimé
    physiquement : le service n'expose volontairement aucune méthode de
    suppression (contrairement aux Ventes)."""
    assert not hasattr(InventoryService, "delete_inventory")
    assert not hasattr(InventoryService, "delete")


def test_no_cancellation_mechanism_exists_for_inventories(login_as) -> None:
    """Aucune permission INVENTORY_CANCEL, aucune méthode d'annulation : un
    inventaire validé est définitif en V1."""
    from app.db.seed import PERMISSIONS

    assert not hasattr(InventoryService, "cancel_inventory")
    assert "INVENTORY_CANCEL" not in {code for code, _, _ in PERMISSIONS}


def test_update_inventory_rejects_unknown_inventory(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.inventory.update_inventory(999999, date(2026, 1, 1), [])


# -- permissions (RBAC) ----------------------------------------------------------


def test_view_permission_enforced(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.inventory.list_inventories()


def test_create_permission_enforced(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.inventory.create_inventory(date(2026, 1, 1), [])


def test_update_permission_enforced(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    inv = admin_stack.inventory.create_inventory(date(2026, 1, 1), [])

    stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        stack.inventory.update_inventory(inv.id, date(2026, 1, 1), [])


def test_validate_permission_enforced(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("50"))
    inv = admin_stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("48"))])

    stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        stack.inventory.validate_inventory(inv.id)


def test_gestionnaire_de_stock_has_full_inventory_access(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")
    article = _make_article(stack, stock_initial=Decimal("50"))

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("48"))])
    stack.inventory.update_inventory(inv.id, date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("47"))])
    validated = stack.inventory.validate_inventory(inv.id)
    assert validated.statut == StatutInventaire.VALIDE


# -- audit --------------------------------------------------------------------------


def test_validate_inventory_is_audited(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("48"))])
    stack.inventory.validate_inventory(inv.id)

    from app.config.settings import get_settings
    from app.db.session import session_scope
    from app.models.audit import AuditLog

    with session_scope(get_settings()) as session:
        logs = session.query(AuditLog).filter_by(entite="inventaires", action="INVENTORY_VALIDATE").all()
        assert len(logs) == 1
        assert logs[0].user_id == current_user.id
        assert logs[0].entite_id == inv.id


def test_create_and_update_inventory_are_audited(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("48"))])
    stack.inventory.update_inventory(inv.id, date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("47"))])

    from app.config.settings import get_settings
    from app.db.session import session_scope
    from app.models.audit import AuditLog

    with session_scope(get_settings()) as session:
        create_logs = session.query(AuditLog).filter_by(entite="inventaires", action="INVENTORY_CREATE").all()
        update_logs = session.query(AuditLog).filter_by(entite="inventaires", action="INVENTORY_UPDATE").all()
        assert len(create_logs) == 1
        assert len(update_logs) == 1
