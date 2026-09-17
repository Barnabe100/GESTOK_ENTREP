from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import StatutOperation, TypeMouvement
from app.services.exits.exit_service import SortieLigneInput
from app.services.stock.stock_service import StockService
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def _make_motif(stack, libelle="Perte"):
    return stack.exit_reasons.create_exit_reason(libelle)


def _make_category(stack, nom="Boissons"):
    return stack.categories.create_category(nom)


def _make_article(stack, reference="ART-0001", stock_initial=Decimal("0"), category_id=None, cmup=None):
    if category_id is None:
        category_id = _make_category(stack).id
    article = stack.articles.create_article(
        reference, "Article de test", category_id, "unité",
        cmup if cmup is not None else Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=stock_initial,
    )
    return article


# -- sortie simple : stock 100 -> 80 -------------------------------------------------


def test_simple_exit_reduces_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("100"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("20"))])
    stack.exits.validate_exit(exit_.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("80")


# -- stock insuffisant ---------------------------------------------------------------


def test_exit_refused_when_stock_insufficient(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("10"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("20"))])

    with pytest.raises(ValidationError):
        stack.exits.validate_exit(exit_.id)

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("10")
    reloaded_exit = stack.exits.get_exit(exit_.id)
    assert reloaded_exit.statut == StatutOperation.BROUILLON


# -- brouillon : stock inchangé -------------------------------------------------------


def test_draft_exit_does_not_modify_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))

    stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("50")


def test_updating_a_draft_exit_does_not_modify_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])
    stack.exits.update_exit(
        exit_.id, motif.id, date(2026, 1, 2), [SortieLigneInput(article.id, Decimal("25"))]
    )

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("50")


def test_cannot_update_a_validated_exit(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])
    stack.exits.validate_exit(exit_.id)

    with pytest.raises(ConflictError):
        stack.exits.update_exit(
            exit_.id, motif.id, date(2026, 1, 2), [SortieLigneInput(article.id, Decimal("5"))]
        )


# -- validation : mouvement créé + stock modifié + stock avant/après correct ---------


def test_validate_exit_creates_movement_and_updates_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("500"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("20"))])
    validated = stack.exits.validate_exit(exit_.id)
    assert validated.statut == StatutOperation.VALIDEE

    movements = stack.exits.get_exit_movements(exit_.id)
    assert len(movements) == 1
    movement = movements[0]
    assert movement.type == TypeMouvement.SORTIE
    assert movement.quantite == Decimal("-20")
    assert movement.stock_avant == Decimal("100")
    assert movement.stock_apres == Decimal("80")
    assert movement.cout_unitaire == Decimal("500.00")

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("80")


def test_validate_exit_does_not_recompute_cmup(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("500"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("20"))])
    stack.exits.validate_exit(exit_.id)

    updated = stack.articles.get_article(article.id)
    assert updated.cout_moyen_pondere == Decimal("500.00")


def test_validate_exit_uses_current_cmup_at_validation_time(login_as) -> None:
    """Le coût de valorisation d'une sortie est le CMUP au moment de la
    validation, pas celui figé à la création du brouillon (une entrée peut
    avoir modifié le CMUP entre-temps)."""
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur Test")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("500"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("20"))])
    assert exit_.lignes[0].cout_unitaire == Decimal("500.00")

    from app.services.entries.entry_service import EntreeLigneInput

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("100"), Decimal("900"))]
    )
    stack.entries.validate_entry(entry.id)
    new_cmup = stack.articles.get_article(article.id).cout_moyen_pondere
    assert new_cmup == Decimal("700.00")  # (100*500 + 100*900) / 200

    validated = stack.exits.validate_exit(exit_.id)
    assert validated.lignes[0].cout_unitaire == new_cmup


def test_validate_exit_requires_at_least_one_line(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [])

    with pytest.raises(ValidationError):
        stack.exits.validate_exit(exit_.id)


def test_validate_exit_only_allowed_from_brouillon(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])
    stack.exits.validate_exit(exit_.id)

    with pytest.raises(ConflictError):
        stack.exits.validate_exit(exit_.id)


# -- transaction : rollback intégral en cas d'erreur en cours d'opération -----------


def test_validate_exit_rolls_back_entirely_on_mid_transaction_error(login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-TX-1", stock_initial=Decimal("50"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-TX-2", stock_initial=Decimal("50"), category_id=category.id)

    exit_ = stack.exits.create_exit(
        motif.id, date(2026, 1, 1),
        [SortieLigneInput(article_1.id, Decimal("10")), SortieLigneInput(article_2.id, Decimal("5"))],
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
        stack.exits.validate_exit(exit_.id)

    monkeypatch.setattr(StockService, "apply_movement", original_apply_movement)

    reloaded_exit = stack.exits.get_exit(exit_.id)
    assert reloaded_exit.statut == StatutOperation.BROUILLON

    reloaded_article_1 = stack.articles.get_article(article_1.id)
    reloaded_article_2 = stack.articles.get_article(article_2.id)
    assert reloaded_article_1.stock_actuel == Decimal("50")
    assert reloaded_article_2.stock_actuel == Decimal("50")

    assert stack.exits.get_exit_movements(exit_.id) == []


# -- motif inactif ----------------------------------------------------------------


def test_create_exit_rejects_inactive_motif(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    stack.exit_reasons.deactivate_exit_reason(motif.id)

    with pytest.raises(ValidationError):
        stack.exits.create_exit(motif.id, date(2026, 1, 1), [])


def test_update_exit_rejects_switching_to_inactive_motif(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif_active = _make_motif(stack, "Perte")
    motif_inactive = _make_motif(stack, "Casse")
    stack.exit_reasons.deactivate_exit_reason(motif_inactive.id)
    article = _make_article(stack, stock_initial=Decimal("50"))

    exit_ = stack.exits.create_exit(motif_active.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))])

    with pytest.raises(ValidationError):
        stack.exits.update_exit(
            exit_.id, motif_inactive.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))]
        )


def test_exit_keeps_referencing_reason_deactivated_after_creation(login_as) -> None:
    """Un motif désactivé APRÈS la création d'une sortie reste visible dans
    l'historique (aucune suppression physique, aucune invalidation
    rétroactive)."""
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))])
    stack.exits.validate_exit(exit_.id)
    stack.exit_reasons.deactivate_exit_reason(motif.id)

    reloaded = stack.exits.get_exit(exit_.id)
    assert reloaded.motif_libelle == motif.libelle


# -- article inactif ----------------------------------------------------------------


def test_create_exit_rejects_inactive_article(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))
    stack.articles.deactivate_article(article.id)

    with pytest.raises(ValidationError):
        stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))])


def test_validate_exit_rejects_article_deactivated_after_draft_creation(login_as) -> None:
    """L'article était actif à la création du brouillon mais désactivé
    depuis : la validation doit le revérifier et refuser."""
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))])
    stack.articles.deactivate_article(article.id)

    with pytest.raises(ValidationError):
        stack.exits.validate_exit(exit_.id)

    reloaded_exit = stack.exits.get_exit(exit_.id)
    assert reloaded_exit.statut == StatutOperation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")


# -- annulation -----------------------------------------------------------------


def test_cancel_exit_restores_stock_and_keeps_history(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("100"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("20"))])
    stack.exits.validate_exit(exit_.id)
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("80")

    cancelled = stack.exits.cancel_exit(exit_.id)
    assert cancelled.statut == StatutOperation.ANNULEE

    updated = stack.articles.get_article(article.id)
    assert updated.stock_actuel == Decimal("100")

    movements = stack.exits.get_exit_movements(exit_.id)
    assert len(movements) == 2
    assert movements[0].type == TypeMouvement.SORTIE
    assert movements[0].quantite == Decimal("-20")
    assert movements[1].type == TypeMouvement.ANNULATION
    assert movements[1].quantite == Decimal("20")

    # L'opération originale est conservée (jamais supprimée) et reste consultable.
    reloaded = stack.exits.get_exit(exit_.id)
    assert reloaded.numero == exit_.numero
    assert len(reloaded.lignes) == 1


def test_cancel_exit_only_allowed_from_validee(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])

    with pytest.raises(ConflictError):
        stack.exits.cancel_exit(exit_.id)


# -- permissions ----------------------------------------------------------------


def test_gestionnaire_de_stock_can_create_and_validate_but_not_cancel(login_as) -> None:
    """Les motifs de sortie restent administrés exclusivement par
    l'Administrateur (décision métier de la phase précédente) : le
    Gestionnaire de stock ne fait que les *utiliser* dans ses sorties."""
    admin_stack, _ = login_as("Administrateur")
    motif = _make_motif(admin_stack)

    stack, _ = login_as("Gestionnaire de stock")
    article = _make_article(stack, stock_initial=Decimal("50"))

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])
    stack.exits.validate_exit(exit_.id)

    with pytest.raises(PermissionDeniedError):
        stack.exits.cancel_exit(exit_.id)


def test_vendeur_cannot_view_or_create_exits(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.exits.list_exits()

    with pytest.raises(PermissionDeniedError):
        stack.exits.create_exit(1, date(2026, 1, 1), [])


def test_consultation_cannot_view_or_create_exits_but_can_view_movements(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    motif = _make_motif(admin_stack)
    article = _make_article(admin_stack, stock_initial=Decimal("50"))
    exit_ = admin_stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])
    admin_stack.exits.validate_exit(exit_.id)

    stack, _ = login_as("Consultation")

    with pytest.raises(PermissionDeniedError):
        stack.exits.list_exits()

    with pytest.raises(PermissionDeniedError):
        stack.exits.create_exit(1, date(2026, 1, 1), [])

    movements = stack.exits.get_exit_movements(exit_.id)
    assert len(movements) == 1


# -- validations diverses --------------------------------------------------------


def test_create_exit_rejects_non_positive_quantity(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))

    with pytest.raises(ValidationError):
        stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("0"))])


def test_create_exit_unknown_motif_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.exits.create_exit(999999, date(2026, 1, 1), [])


def test_create_exit_auto_generates_sequential_numero(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)

    first = stack.exits.create_exit(motif.id, date(2026, 1, 1), [])
    second = stack.exits.create_exit(motif.id, date(2026, 1, 1), [])

    assert first.numero == "SOR-000001"
    assert second.numero == "SOR-000002"
