"""Règle métier commune « date future interdite » (Entrées/Sorties/Ventes/
Inventaires) : ``date_operation`` ne doit jamais être postérieure à la date
du jour, y compris pour une opération en BROUILLON (voir ``app.utils.dates``
et le diagnostic qui a motivé ce lot — une entrée avait pu être créée avec
une date postérieure à aujourd'hui).

Applique systématiquement le triptyque hier/aujourd'hui/demain (+ une date
plus éloignée) exigé pour chaque type d'opération, et vérifie que la
validation est bien portée par le SERVICE (appelée ici directement, sans
passer par aucun widget Qt) — jamais uniquement par l'interface."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.entries.entry_service import EntreeLigneInput
from app.services.exits.exit_service import SortieLigneInput
from app.services.inventory.inventory_service import InventaireLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.dates import DATE_FUTURE_MESSAGE, validate_not_future_date
from app.utils.exceptions import ValidationError

YESTERDAY = date.today() - timedelta(days=1)
TODAY = date.today()
TOMORROW = date.today() + timedelta(days=1)
FAR_FUTURE = date.today() + timedelta(days=365)


def _make_article(stack, reference="ART-DATE", stock_initial=Decimal("50")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


# -- utilitaire partagé (app.utils.dates) ---------------------------------------------


@pytest.mark.parametrize("value", [YESTERDAY, TODAY])
def test_validate_not_future_date_accepts_past_and_today(value) -> None:
    assert validate_not_future_date(value) == value


@pytest.mark.parametrize("value", [TOMORROW, FAR_FUTURE])
def test_validate_not_future_date_rejects_future(value) -> None:
    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        validate_not_future_date(value)


# -- Entrées ----------------------------------------------------------------------------


def test_entry_create_accepts_yesterday(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur")
    article = _make_article(stack)

    entry = stack.entries.create_entry(
        supplier.id, YESTERDAY, [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
    )
    assert entry.date == YESTERDAY


def test_entry_create_accepts_today(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur")
    article = _make_article(stack)

    entry = stack.entries.create_entry(
        supplier.id, TODAY, [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
    )
    assert entry.date == TODAY
    stack.entries.validate_entry(entry.id)  # une entrée valide datée d'aujourd'hui reste validable


def test_entry_create_rejects_tomorrow(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur")
    article = _make_article(stack)

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.entries.create_entry(
            supplier.id, TOMORROW, [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
        )


def test_entry_create_rejects_far_future(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur")
    article = _make_article(stack)

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.entries.create_entry(
            supplier.id, FAR_FUTURE, [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
        )


def test_entry_draft_with_future_date_is_never_created(login_as) -> None:
    """Une entrée BROUILLON avec une date future doit être refusée dès la
    création — le statut brouillon ne contourne jamais la règle."""
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur")
    article = _make_article(stack)

    with pytest.raises(ValidationError):
        stack.entries.create_entry(
            supplier.id, TOMORROW, [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
        )
    assert stack.entries.list_entries() == []


def test_entry_update_rejects_tomorrow(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur")
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, TODAY, [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
    )

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.entries.update_entry(
            entry.id, supplier.id, TOMORROW, [EntreeLigneInput(article.id, Decimal("6"), Decimal("100"))]
        )
    # non-régression : l'entrée existante n'a pas été modifiée par la tentative refusée.
    unchanged = stack.entries.get_entry(entry.id)
    assert unchanged.date == TODAY


# -- Sorties ----------------------------------------------------------------------------


def test_exit_create_accepts_yesterday(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = _make_article(stack)

    exit_ = stack.exits.create_exit(motif.id, YESTERDAY, [SortieLigneInput(article.id, Decimal("2"))])
    assert exit_.date == YESTERDAY


def test_exit_create_accepts_today(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = _make_article(stack)

    exit_ = stack.exits.create_exit(motif.id, TODAY, [SortieLigneInput(article.id, Decimal("2"))])
    assert exit_.date == TODAY
    stack.exits.validate_exit(exit_.id)


def test_exit_create_rejects_tomorrow(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = _make_article(stack)

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.exits.create_exit(motif.id, TOMORROW, [SortieLigneInput(article.id, Decimal("2"))])


def test_exit_create_rejects_far_future(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = _make_article(stack)

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.exits.create_exit(motif.id, FAR_FUTURE, [SortieLigneInput(article.id, Decimal("2"))])


def test_exit_draft_with_future_date_is_never_created(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = _make_article(stack)

    with pytest.raises(ValidationError):
        stack.exits.create_exit(motif.id, TOMORROW, [SortieLigneInput(article.id, Decimal("2"))])
    assert stack.exits.list_exits() == []


def test_exit_update_rejects_tomorrow(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = _make_article(stack)
    exit_ = stack.exits.create_exit(motif.id, TODAY, [SortieLigneInput(article.id, Decimal("2"))])

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.exits.update_exit(exit_.id, motif.id, TOMORROW, [SortieLigneInput(article.id, Decimal("3"))])
    unchanged = stack.exits.get_exit(exit_.id)
    assert unchanged.date == TODAY


# -- Ventes -----------------------------------------------------------------------------


def test_sale_create_accepts_yesterday(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    sale = stack.sales.create_sale(YESTERDAY, [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])
    assert sale.date == YESTERDAY


def test_sale_create_accepts_today(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    sale = stack.sales.create_sale(TODAY, [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])
    assert sale.date == TODAY
    stack.sales.validate_sale(sale.id)


def test_sale_create_rejects_tomorrow(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.sales.create_sale(TOMORROW, [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])


def test_sale_create_rejects_far_future(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.sales.create_sale(FAR_FUTURE, [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])


def test_sale_draft_with_future_date_is_never_created(login_as) -> None:
    """Une vente BROUILLON avec une date future doit être refusée dès la
    création, exactement comme une vente déjà validée."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    with pytest.raises(ValidationError):
        stack.sales.create_sale(TOMORROW, [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])
    assert stack.sales.list_sales() == []


def test_sale_update_rejects_tomorrow(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(TODAY, [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.sales.update_sale(sale.id, TOMORROW, [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])
    unchanged = stack.sales.get_sale(sale.id)
    assert unchanged.date == TODAY


# -- Inventaires --------------------------------------------------------------------------


def test_inventory_create_accepts_yesterday(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    inventory = stack.inventory.create_inventory(YESTERDAY, [InventaireLigneInput(article.id, Decimal("50"))])
    assert inventory.date == YESTERDAY


def test_inventory_create_accepts_today(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    inventory = stack.inventory.create_inventory(TODAY, [InventaireLigneInput(article.id, Decimal("50"))])
    assert inventory.date == TODAY
    stack.inventory.validate_inventory(inventory.id)


def test_inventory_create_rejects_tomorrow(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.inventory.create_inventory(TOMORROW, [InventaireLigneInput(article.id, Decimal("50"))])


def test_inventory_create_rejects_far_future(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.inventory.create_inventory(FAR_FUTURE, [InventaireLigneInput(article.id, Decimal("50"))])


def test_inventory_draft_with_future_date_is_never_created(login_as) -> None:
    """Cas exact du diagnostic à l'origine de ce lot : préparation
    (brouillon) d'un inventaire avec une date future doit être refusée dès
    la création, pas seulement à la validation/définitive."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    with pytest.raises(ValidationError):
        stack.inventory.create_inventory(TOMORROW, [InventaireLigneInput(article.id, Decimal("50"))])
    assert stack.inventory.list_inventories() == []


def test_inventory_update_rejects_tomorrow(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    inventory = stack.inventory.create_inventory(TODAY, [InventaireLigneInput(article.id, Decimal("50"))])

    with pytest.raises(ValidationError, match=DATE_FUTURE_MESSAGE):
        stack.inventory.update_inventory(inventory.id, TOMORROW, [InventaireLigneInput(article.id, Decimal("51"))])
    unchanged = stack.inventory.get_inventory(inventory.id)
    assert unchanged.date == TODAY


# -- non-régression : opérations historiques et du jour toujours possibles ------------------


def test_historical_and_today_operations_remain_fully_functional(login_as) -> None:
    """Bout en bout (création -> validation) pour les 4 types d'opérations,
    à une date historique et à la date du jour : aucune régression sur le
    comportement déjà validé par le reste de la suite."""
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = _make_article(stack, stock_initial=Decimal("0"))

    for operation_date in (date(2020, 1, 1), TODAY):
        entry = stack.entries.create_entry(
            supplier.id, operation_date, [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
        )
        stack.entries.validate_entry(entry.id)

        exit_ = stack.exits.create_exit(motif.id, operation_date, [SortieLigneInput(article.id, Decimal("1"))])
        stack.exits.validate_exit(exit_.id)

        sale = stack.sales.create_sale(operation_date, [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])
        stack.sales.validate_sale(sale.id)

        inventory = stack.inventory.create_inventory(
            operation_date, [InventaireLigneInput(article.id, Decimal("8"))]
        )
        stack.inventory.validate_inventory(inventory.id)
