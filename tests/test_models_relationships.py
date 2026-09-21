from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import Article, Category, Supplier
from app.models.documents import Entree, EntreeLigne
from app.models.enums import StatutOperation, TypeMouvement
from app.models.movement import MouvementStock
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password


def _create_base_data(session: Session):
    role = session.query(Role).filter_by(nom="Gestionnaire de stock").one()
    user = User(username="jdupont", password_hash=hash_password("Motdepasse!23"), role_id=role.id, roles=[role])
    category = Category(nom="Boissons")
    supplier = Supplier(nom="Fournisseur Test")
    session.add_all([user, category, supplier])
    session.flush()

    article = Article(
        reference="ART-0001",
        designation="Article de test",
        category_id=category.id,
        unite="unité",
        fournisseur_principal_id=supplier.id,
        prix_achat_defaut=Decimal("100.00"),
        prix_vente=Decimal("150.00"),
    )
    session.add(article)
    session.flush()
    return user, category, supplier, article


def test_article_relationships_navigate_correctly(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        _, category, supplier, article = _create_base_data(session)

        assert article.category.nom == "Boissons"
        assert article.fournisseur_principal.nom == "Fournisseur Test"
        assert article in category.articles
        assert article in supplier.articles


def test_entree_validation_creates_traceable_movement(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user, _category, supplier, article = _create_base_data(session)

        entree = Entree(
            numero="ENT-0001",
            date=date.today(),
            fournisseur_id=supplier.id,
            user_id=user.id,
            statut=StatutOperation.BROUILLON,
        )
        session.add(entree)
        session.flush()

        ligne = EntreeLigne(
            entree_id=entree.id,
            article_id=article.id,
            quantite=Decimal("10.000"),
            prix_unitaire=Decimal("100.00"),
            montant=Decimal("1000.00"),
        )
        session.add(ligne)
        session.flush()

        mouvement = MouvementStock(
            article_id=article.id,
            type=TypeMouvement.ENTREE,
            quantite=Decimal("10.000"),
            stock_avant=Decimal("0.000"),
            stock_apres=Decimal("10.000"),
            cout_unitaire=Decimal("100.00"),
            entree_ligne_id=ligne.id,
            user_id=user.id,
        )
        session.add(mouvement)
        session.flush()

        assert entree.lignes[0] is ligne
        assert mouvement.article is article
        assert mouvement.entree_ligne_id == ligne.id


def test_user_roles_relationship(initialized_db: Settings) -> None:
    """``User.roles``/``Role.users`` : relation many-to-many (lot
    multi-rôles) — un utilisateur peut porter un ou plusieurs rôles."""
    with session_scope(initialized_db) as session:
        role = session.query(Role).filter_by(nom="Vendeur").one()
        user = User(
            username="vendeur1", password_hash=hash_password("AzertY123!"), role_id=role.id, roles=[role]
        )
        session.add(user)
        session.flush()

        assert [r.nom for r in user.roles] == ["Vendeur"]
        assert user in role.users


def test_user_can_have_multiple_roles(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        vendeur = session.query(Role).filter_by(nom="Vendeur").one()
        gestionnaire = session.query(Role).filter_by(nom="Gestionnaire de stock").one()
        user = User(
            username="polyvalent",
            password_hash=hash_password("AzertY123!"),
            role_id=vendeur.id,
            roles=[vendeur, gestionnaire],
        )
        session.add(user)
        session.flush()

        assert {r.nom for r in user.roles} == {"Vendeur", "Gestionnaire de stock"}
        assert user in vendeur.users
        assert user in gestionnaire.users


def test_foreign_key_violation_is_rejected(initialized_db: Settings) -> None:
    """Un article référençant une catégorie inexistante doit être rejeté (PRAGMA foreign_keys=ON)."""
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            orphan_article = Article(
                reference="ART-ORPHAN",
                designation="Article orphelin",
                category_id=999999,
                unite="unité",
                prix_achat_defaut=Decimal("1.00"),
                prix_vente=Decimal("2.00"),
            )
            session.add(orphan_article)


def test_negative_stock_check_constraint_is_rejected(initialized_db: Settings) -> None:
    """Contrainte CHECK en base : un stock négatif est impossible, même par écriture directe."""
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            category = Category(nom="Catégorie CK")
            session.add(category)
            session.flush()
            invalid_article = Article(
                reference="ART-NEG",
                designation="Stock négatif interdit",
                category_id=category.id,
                unite="unité",
                prix_achat_defaut=Decimal("1.00"),
                prix_vente=Decimal("2.00"),
                stock_actuel=Decimal("-1.000"),
            )
            session.add(invalid_article)
