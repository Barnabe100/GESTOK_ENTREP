from decimal import Decimal

import pytest

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import Article, Category
from app.models.enums import TypeMouvement
from app.models.movement import MouvementStock
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.stock.stock_service import StockService
from app.utils.exceptions import ValidationError


def _make_article(session, stock_actuel=Decimal("0"), cout_moyen_pondere=Decimal("0")) -> Article:
    category = Category(nom="Boissons")
    session.add(category)
    session.flush()
    article = Article(
        reference="ART-STOCK",
        designation="Article de test",
        category_id=category.id,
        unite="unité",
        prix_achat_defaut=Decimal("0"),
        prix_vente=Decimal("0"),
        cout_moyen_pondere=cout_moyen_pondere,
        stock_actuel=stock_actuel,
        stock_min=Decimal("0"),
    )
    session.add(article)
    session.flush()
    return article


def _make_user(session, username="op1") -> User:
    role = session.query(Role).filter_by(nom="Administrateur").one()
    user = User(username=username, password_hash=hash_password("Password!23"), role_id=role.id)
    session.add(user)
    session.flush()
    return user


# -- calcul du CMUP (fonction pure) ----------------------------------------------


def test_compute_new_cmup_matches_worked_example() -> None:
    """Exemple du cahier des charges : stock 100 @ 1000, entrée 50 @ 1200 -> 1066.67."""
    result = StockService.compute_new_cmup(Decimal("100"), Decimal("1000"), Decimal("50"), Decimal("1200"))
    assert result == Decimal("1066.67")


def test_compute_new_cmup_on_zero_initial_stock_equals_purchase_price() -> None:
    result = StockService.compute_new_cmup(Decimal("0"), Decimal("0"), Decimal("10"), Decimal("500"))
    assert result == Decimal("500.00")


def test_compute_new_cmup_on_zero_stock_ignores_stale_cmup() -> None:
    """Le CMUP précédent (résiduel d'un stock épuisé) ne doit pas polluer le calcul
    quand stock_avant = 0 : le terme stock_avant × CMUP_avant s'annule naturellement."""
    result = StockService.compute_new_cmup(Decimal("0"), Decimal("999999"), Decimal("10"), Decimal("50"))
    assert result == Decimal("50.00")


def test_compute_new_cmup_rounds_half_up() -> None:
    result = StockService.compute_new_cmup(Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1.005"))
    # (1*1 + 1*1.005) / 2 = 1.0025 -> arrondi ROUND_HALF_UP -> 1.00
    assert result == Decimal("1.00")


def test_compute_new_cmup_multiple_successive_entries() -> None:
    """Vérifie l'évolution correcte du CMUP sur plusieurs entrées successives."""
    cmup = StockService.compute_new_cmup(Decimal("0"), Decimal("0"), Decimal("10"), Decimal("100"))
    assert cmup == Decimal("100.00")
    stock = Decimal("10")

    cmup = StockService.compute_new_cmup(stock, cmup, Decimal("10"), Decimal("200"))
    assert cmup == Decimal("150.00")
    stock += Decimal("10")

    cmup = StockService.compute_new_cmup(stock, cmup, Decimal("20"), Decimal("150"))
    # (20*150 + 20*150) / 40 = 150.00
    assert cmup == Decimal("150.00")


# -- apply_movement ---------------------------------------------------------------


def test_apply_movement_entree_increases_stock_and_recomputes_cmup(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        article = _make_article(session, stock_actuel=Decimal("100"), cout_moyen_pondere=Decimal("1000"))
        user = _make_user(session)
        service = StockService()

        movement = service.apply_movement(
            session, article, TypeMouvement.ENTREE, Decimal("50"),
            cout_unitaire=Decimal("1200"), user_id=user.id,
        )

        assert article.stock_actuel == Decimal("150")
        assert article.cout_moyen_pondere == Decimal("1066.67")
        assert movement.stock_avant == Decimal("100")
        assert movement.stock_apres == Decimal("150")
        assert movement.type == TypeMouvement.ENTREE
        assert movement.quantite == Decimal("50")
        assert movement.cout_unitaire == Decimal("1200")


def test_apply_movement_sortie_decreases_stock_without_touching_cmup(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        article = _make_article(session, stock_actuel=Decimal("100"), cout_moyen_pondere=Decimal("1000"))
        user = _make_user(session)
        service = StockService()

        movement = service.apply_movement(
            session, article, TypeMouvement.SORTIE, Decimal("-30"),
            cout_unitaire=Decimal("1000"), user_id=user.id,
        )

        assert article.stock_actuel == Decimal("70")
        assert article.cout_moyen_pondere == Decimal("1000")  # inchangé
        assert movement.stock_avant == Decimal("100")
        assert movement.stock_apres == Decimal("70")


def test_apply_movement_rejects_negative_resulting_stock(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        article = _make_article(session, stock_actuel=Decimal("10"))
        user = _make_user(session)
        service = StockService()

        with pytest.raises(ValidationError):
            service.apply_movement(session, article, TypeMouvement.SORTIE, Decimal("-11"), user_id=user.id)

        # Rien n'a été modifié : ni le stock, ni un mouvement créé.
        assert article.stock_actuel == Decimal("10")
        movements = session.query(MouvementStock).filter_by(article_id=article.id).all()
        assert movements == []


def test_apply_movement_exact_depletion_to_zero_is_allowed(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        article = _make_article(session, stock_actuel=Decimal("10"))
        user = _make_user(session)
        service = StockService()

        movement = service.apply_movement(session, article, TypeMouvement.SORTIE, Decimal("-10"), user_id=user.id)

        assert article.stock_actuel == Decimal("0")
        assert movement.stock_apres == Decimal("0")


def test_apply_movement_entree_rejects_non_positive_quantity(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        article = _make_article(session, stock_actuel=Decimal("10"))
        user = _make_user(session)
        service = StockService()

        with pytest.raises(ValidationError):
            service.apply_movement(
                session, article, TypeMouvement.ENTREE, Decimal("0"),
                cout_unitaire=Decimal("10"), user_id=user.id,
            )


def test_apply_movement_records_user_and_comment(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        article = _make_article(session)
        service = StockService()

        movement = service.apply_movement(
            session, article, TypeMouvement.ENTREE, Decimal("10"),
            cout_unitaire=Decimal("5"), user_id=user.id, commentaire="Test",
        )

        assert movement.user_id == user.id
        assert movement.commentaire == "Test"


def test_apply_movement_links_mouvement_origine_for_annulation(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        article = _make_article(session, cout_moyen_pondere=Decimal("100"))
        user = _make_user(session)
        service = StockService()

        original = service.apply_movement(
            session, article, TypeMouvement.ENTREE, Decimal("10"),
            cout_unitaire=Decimal("100"), user_id=user.id,
        )
        reversal = service.apply_movement(
            session, article, TypeMouvement.ANNULATION, Decimal("-10"),
            cout_unitaire=Decimal("100"), user_id=user.id, mouvement_origine_id=original.id,
        )

        assert reversal.mouvement_origine_id == original.id
        assert article.cout_moyen_pondere == Decimal("100")  # ANNULATION ne recalcule jamais le CMUP


def test_apply_movement_annulation_never_recomputes_cmup_even_reversing_an_entree(
    initialized_db: Settings,
) -> None:
    with session_scope(initialized_db) as session:
        article = _make_article(session, stock_actuel=Decimal("0"), cout_moyen_pondere=Decimal("0"))
        user = _make_user(session)
        service = StockService()

        service.apply_movement(
            session, article, TypeMouvement.ENTREE, Decimal("10"),
            cout_unitaire=Decimal("100"), user_id=user.id,
        )
        assert article.cout_moyen_pondere == Decimal("100.00")

        service.apply_movement(
            session, article, TypeMouvement.ENTREE, Decimal("10"),
            cout_unitaire=Decimal("300"), user_id=user.id,
        )
        assert article.cout_moyen_pondere == Decimal("200.00")  # (10*100+10*300)/20

        # Annuler la 2e entrée ne doit pas reconstruire rétroactivement le CMUP.
        service.apply_movement(
            session, article, TypeMouvement.ANNULATION, Decimal("-10"),
            cout_unitaire=Decimal("300"), user_id=user.id,
        )
        assert article.cout_moyen_pondere == Decimal("200.00")
        assert article.stock_actuel == Decimal("10")
