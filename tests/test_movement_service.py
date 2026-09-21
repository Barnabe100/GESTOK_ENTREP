from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.enums import TypeMouvement
from app.services.entries.entry_service import EntreeLigneInput
from app.services.exits.exit_service import SortieLigneInput
from app.services.inventory.inventory_service import InventaireLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import PermissionDeniedError


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


# -- permissions ---------------------------------------------------------------------


def test_gestionnaire_stock_can_list_movements(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")
    article = _make_article(stack, stock_initial=Decimal("10"))

    movements = stack.movements.list_movements(article_id=article.id)

    assert len(movements) == 1


def test_consultation_can_list_movements(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("10"))

    consultation_stack, _ = login_as("Consultation")
    movements = consultation_stack.movements.list_movements(article_id=article.id)

    assert len(movements) == 1


def test_vendeur_without_stock_movement_view_is_denied(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.movements.list_movements()


# -- contenu / référence de l'opération ------------------------------------------------


def test_entry_movement_reference_operation_is_entry_numero(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack, stock_initial=Decimal("0"))
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    movements = stack.movements.list_movements(article_id=article.id, type_mouvement=TypeMouvement.ENTREE)

    assert len(movements) == 1
    assert movements[0].reference_operation == entry.numero
    assert movements[0].username.startswith("test_administrateur")


def test_sale_and_cancellation_reference_operation_is_sale_numero(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("10"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)
    stack.sales.cancel_sale(sale.id, "Motif de test valide")

    movements = stack.movements.list_movements(article_id=article.id)
    vente = next(m for m in movements if m.type == TypeMouvement.VENTE)
    annulation = next(m for m in movements if m.type == TypeMouvement.ANNULATION)

    assert vente.reference_operation == sale.numero
    assert annulation.reference_operation == sale.numero


def test_movements_cover_all_four_types_plus_cancellation(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    motif = stack.exit_reasons.create_exit_reason("Perte")
    article = _make_article(stack, stock_initial=Decimal("0"))

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("100"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])
    stack.exits.validate_exit(exit_.id)

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("10"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)
    stack.sales.cancel_sale(sale.id, "Motif de test valide")

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("100"))])
    stack.inventory.validate_inventory(inv.id)

    movements = stack.movements.list_movements(article_id=article.id)
    types = {m.type for m in movements}

    assert TypeMouvement.ENTREE in types
    assert TypeMouvement.SORTIE in types
    assert TypeMouvement.VENTE in types
    assert TypeMouvement.ANNULATION in types
    assert TypeMouvement.AJUSTEMENT in types


# -- filtres --------------------------------------------------------------------------


def test_filtered_by_period(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    assert len(stack.movements.list_movements(article_id=article.id, date_from=today, date_to=today)) == 1
    assert len(stack.movements.list_movements(article_id=article.id, date_from=tomorrow, date_to=tomorrow)) == 0
    assert len(stack.movements.list_movements(article_id=article.id, date_from=yesterday, date_to=yesterday)) == 0


def test_filtered_by_type(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack, stock_initial=Decimal("0"))
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    entree_movements = stack.movements.list_movements(article_id=article.id, type_mouvement=TypeMouvement.ENTREE)
    sortie_movements = stack.movements.list_movements(article_id=article.id, type_mouvement=TypeMouvement.SORTIE)

    assert len(entree_movements) == 1
    assert len(sortie_movements) == 0


def test_search_term_matches_article_reference(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-ALPHA", stock_initial=Decimal("10"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-BETA", stock_initial=Decimal("20"), category_id=category.id)

    movements = stack.movements.list_movements(term="ALPHA")

    assert {m.article_id for m in movements} == {article_1.id}


def test_search_term_matches_username(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))

    movements = stack.movements.list_movements(term=current_user.username)

    assert any(m.article_id == article.id for m in movements)

    no_match = stack.movements.list_movements(term="utilisateur-inexistant-xyz")
    assert no_match == []
