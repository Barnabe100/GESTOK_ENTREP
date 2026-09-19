"""Intégration Client <-> Vente : association optionnelle, sans aucun impact
sur le stock, le CMUP, les mouvements ou la logique de validation/annulation
(§6-8 du lot Clients + Ventes aux clients).
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.enums import TypeMouvement
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import NotFoundError, ValidationError


def _make_category(stack, nom):
    return stack.categories.create_category(nom)


def _make_article(stack, reference="ART-0001", stock_initial=Decimal("50"), cmup=Decimal("100")):
    category_id = _make_category(stack, f"Cat-{reference}").id
    return stack.articles.create_article(
        reference, "Article de test", category_id, "unité",
        cmup, Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


# -- vente avec / sans client ------------------------------------------------------------


def test_create_sale_with_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Jean Dupont")

    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )

    assert sale.client_id == client.id
    assert sale.client_nom == "Jean Dupont"


def test_create_sale_without_client_is_valid(login_as) -> None:
    """Vente comptant : client_id=None, parfaitement valide (§6)."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])

    assert sale.client_id is None
    assert sale.client_nom is None


def test_create_sale_defaults_to_no_client_when_omitted(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))]
    )

    assert sale.client_id is None


def test_get_sale_returns_client_after_reload(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Jean Dupont")
    created = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )

    reloaded = stack.sales.get_sale(created.id)

    assert reloaded.client_id == client.id
    assert reloaded.client_nom == "Jean Dupont"


def test_create_sale_rejects_unknown_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)

    with pytest.raises(NotFoundError):
        stack.sales.create_sale(
            date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=999999
        )


def test_create_sale_rejects_inactive_client(login_as) -> None:
    """§8 : un client désactivé ne doit plus être proposé pour une nouvelle
    vente — revérifié côté service, pas seulement côté interface."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client inactif")
    stack.clients.deactivate_client(client.id)

    with pytest.raises(ValidationError):
        stack.sales.create_sale(
            date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
        )


def test_update_sale_changes_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client_a = stack.clients.create_client("Client A")
    client_b = stack.clients.create_client("Client B")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client_a.id
    )

    updated = stack.sales.update_sale(
        sale.id, date(2026, 1, 2), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client_b.id
    )

    assert updated.client_id == client_b.id
    assert updated.client_nom == "Client B"


def test_update_sale_can_clear_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )

    updated = stack.sales.update_sale(
        sale.id, date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=None
    )

    assert updated.client_id is None
    assert updated.client_nom is None


def test_update_sale_rejects_inactive_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client")
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])
    stack.clients.deactivate_client(client.id)

    with pytest.raises(ValidationError):
        stack.sales.update_sale(
            sale.id, date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))],
            client_id=client.id,
        )


# -- filtre par client --------------------------------------------------------------------


def test_list_sales_filtered_by_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client_a = stack.clients.create_client("Client A")
    client_b = stack.clients.create_client("Client B")
    stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))], client_id=client_a.id
    )
    stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))], client_id=client_b.id
    )
    stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])

    results_a = stack.sales.list_sales(client_id=client_a.id)

    assert len(results_a) == 1
    assert results_a[0].client_id == client_a.id


# -- non-régression : stock / CMUP / mouvements identiques avec ou sans client -------------


def test_stock_after_validation_identical_with_or_without_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article_with_client = _make_article(stack, reference="ART-A", stock_initial=Decimal("50"), cmup=Decimal("100"))
    article_without_client = _make_article(stack, reference="ART-B", stock_initial=Decimal("50"), cmup=Decimal("100"))
    client = stack.clients.create_client("Client")

    sale_with_client = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article_with_client.id, Decimal("10"), Decimal("150"))], client_id=client.id
    )
    sale_without_client = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article_without_client.id, Decimal("10"), Decimal("150"))]
    )

    stack.sales.validate_sale(sale_with_client.id)
    stack.sales.validate_sale(sale_without_client.id)

    stock_with = stack.articles.get_article(article_with_client.id).stock_actuel
    stock_without = stack.articles.get_article(article_without_client.id).stock_actuel
    assert stock_with == stock_without == Decimal("40")

    cmup_with = stack.articles.get_article(article_with_client.id).cout_moyen_pondere
    cmup_without = stack.articles.get_article(article_without_client.id).cout_moyen_pondere
    assert cmup_with == cmup_without  # une VENTE ne recalcule jamais le CMUP (règle StockService n°4)


def test_movements_identical_with_or_without_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article_with_client = _make_article(stack, reference="ART-A")
    article_without_client = _make_article(stack, reference="ART-B")
    client = stack.clients.create_client("Client")

    sale_with_client = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article_with_client.id, Decimal("5"), Decimal("150"))], client_id=client.id
    )
    sale_without_client = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article_without_client.id, Decimal("5"), Decimal("150"))]
    )
    stack.sales.validate_sale(sale_with_client.id)
    stack.sales.validate_sale(sale_without_client.id)

    movements_with = stack.movements.list_movements(article_id=article_with_client.id, type_mouvement=TypeMouvement.VENTE)
    movements_without = stack.movements.list_movements(article_id=article_without_client.id, type_mouvement=TypeMouvement.VENTE)

    assert len(movements_with) == len(movements_without) == 1
    assert movements_with[0].quantite == movements_without[0].quantite == Decimal("-5")


def test_cancel_sale_with_client_restores_stock_normally(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    client = stack.clients.create_client("Client")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))], client_id=client.id
    )
    stack.sales.validate_sale(sale.id)

    cancelled = stack.sales.cancel_sale(sale.id)

    assert cancelled.client_id == client.id  # le client reste associé après annulation
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")


def test_deactivating_client_does_not_affect_existing_sale(login_as) -> None:
    """§8 : la vente historique reste intacte (client toujours affiché)
    après désactivation du client."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )
    stack.sales.validate_sale(sale.id)

    stack.clients.deactivate_client(client.id)

    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.client_id == client.id
    assert reloaded.client_nom == "Client"


# -- permissions bout en bout --------------------------------------------------------------


def test_vendeur_can_create_sale_with_client_they_created(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)

    stack, _ = login_as("Vendeur")
    client = stack.clients.create_client("Client du vendeur")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))], client_id=client.id
    )

    assert sale.client_id == client.id
