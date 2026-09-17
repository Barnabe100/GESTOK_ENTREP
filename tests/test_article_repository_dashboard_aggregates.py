"""Méthodes d'agrégation ciblées ajoutées à ``ArticleRepository`` pour le
Dashboard (§8 : COUNT/SUM en SQL plutôt que charger des lignes complètes)."""
from decimal import Decimal

from app.db.session import session_scope
from app.repositories.article_repository import ArticleRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.supplier_repository import SupplierRepository


def _make_stack_with_articles(login_as):
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    other_category = stack.categories.create_category("Hygiène")
    stack.suppliers.create_supplier("Fournisseur A")
    article_low = stack.articles.create_article(
        "ART-LOW", "Faible", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("2")
    )
    article_out = stack.articles.create_article(
        "ART-OUT", "Rupture", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("0")
    )
    article_ok = stack.articles.create_article(
        "ART-OK", "OK", other_category.id, "u", Decimal("20"), Decimal("25"), Decimal("5"), stock_initial=Decimal("3")
    )
    stack.articles.deactivate_article(article_ok.id)
    return stack, category, other_category, article_low, article_out, article_ok


def test_count_active_excludes_inactive_articles(login_as) -> None:
    stack, *_ = _make_stack_with_articles(login_as)
    with session_scope(None) as session:
        count = ArticleRepository(session).count_active()
    assert count == 2  # ART-LOW et ART-OUT actifs, ART-OK désactivé


def test_count_low_stock_includes_ruptures(login_as) -> None:
    stack, *_ = _make_stack_with_articles(login_as)
    with session_scope(None) as session:
        count = ArticleRepository(session).count_low_stock()
    assert count == 2  # ART-LOW (2<=5) et ART-OUT (0<=5), ART-OK inactif exclu


def test_count_out_of_stock(login_as) -> None:
    stack, *_ = _make_stack_with_articles(login_as)
    with session_scope(None) as session:
        count = ArticleRepository(session).count_out_of_stock()
    assert count == 1  # ART-OUT


def test_sum_stock_value_matches_manual_decimal_computation(login_as) -> None:
    stack, *_ = _make_stack_with_articles(login_as)
    with session_scope(None) as session:
        total = ArticleRepository(session).sum_stock_value(include_inactive=False)
    # ART-LOW : 2 x CMUP initial (10) = 20 ; ART-OUT : 0 x 10 = 0 ; ART-OK inactif exclu.
    assert total == Decimal("20.00")
    assert isinstance(total, Decimal)


def test_sum_stock_quantity(login_as) -> None:
    stack, *_ = _make_stack_with_articles(login_as)
    with session_scope(None) as session:
        total = ArticleRepository(session).sum_stock_quantity(include_inactive=False)
    assert total == Decimal("2")  # ART-LOW(2) + ART-OUT(0), ART-OK inactif exclu


def test_sum_stock_value_by_category_groups_and_sorts_descending(login_as) -> None:
    stack, category, other_category, *_ = _make_stack_with_articles(login_as)

    with session_scope(None) as session:
        rows = ArticleRepository(session).sum_stock_value_by_category(include_inactive=True)

    by_name = dict(rows)
    assert by_name["Boissons"] == Decimal("20.00")  # ART-LOW(2x10) + ART-OUT(0x10)
    assert by_name["Hygiène"] == Decimal("60.00")  # ART-OK(3x20), inclus car include_inactive=True
    assert rows[0][1] >= rows[1][1]  # tri décroissant


def test_category_count_active(login_as) -> None:
    stack, *_ = _make_stack_with_articles(login_as)
    stack.categories.create_category("Inactive")  # créée active par défaut
    with session_scope(None) as session:
        count = CategoryRepository(session).count_active()
    assert count == 3  # Boissons, Hygiène, Inactive (toutes actives à la création)


def test_supplier_count_active(login_as) -> None:
    stack, *_ = _make_stack_with_articles(login_as)
    with session_scope(None) as session:
        count = SupplierRepository(session).count_active()
    assert count == 1
