from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import Article, ArticleModeGestionChangement, Category
from app.models.client import Client
from app.models.enums import ModeGestionArticle, StatutLocation, TypeMouvement
from app.models.movement import MouvementStock
from app.models.rbac import Role
from app.models.rental import Location, LocationLigne, LocationPaiement, LocationRetour
from app.models.user import User
from app.security.password_hashing import hash_password


def _create_base_data(session: Session):
    role = session.query(Role).filter_by(nom="Gestionnaire de stock").one()
    user = User(username="jdupont", password_hash=hash_password("Motdepasse!23"), role_id=role.id, roles=[role])
    category = Category(nom="Matériel de location")
    client = Client(nom="Client Location")
    session.add_all([user, category, client])
    session.flush()

    article = Article(
        reference="ART-LOC-0001",
        designation="Article de location",
        category_id=category.id,
        unite="unité",
        prix_achat_defaut=Decimal("1000.00"),
        prix_vente=Decimal("0.00"),
        mode_gestion=ModeGestionArticle.LOCATION,
        tarif_location_jour=Decimal("500.00"),
        stock_actuel=Decimal("10.000"),
    )
    session.add(article)
    session.flush()
    return user, category, client, article


def _create_location(session: Session, client_id: int, user_id: int) -> Location:
    location = Location(
        numero="LOC-TEST-0001", date=date(2026, 1, 1), client_id=client_id, user_id=user_id,
        statut=StatutLocation.BROUILLON, caution_montant=Decimal("0"), caution_rendue=Decimal("0"),
    )
    session.add(location)
    session.flush()
    return location


# -- relations --------------------------------------------------------------------


def test_location_relationships_navigate_correctly(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user, _category, client, article = _create_base_data(session)
        location = _create_location(session, client.id, user.id)

        ligne = LocationLigne(
            location_id=location.id, article_id=article.id,
            qte_prevue=Decimal("2.000"), qte_reservee=Decimal("2.000"), tarif_jour=Decimal("500.00"),
        )
        session.add(ligne)
        session.flush()

        assert location.lignes[0] is ligne
        assert ligne.location is location
        assert ligne.article is article
        assert location.client is client
        assert location.user is user


def test_location_retour_and_mouvement_relationships(initialized_db: Settings) -> None:
    """Reproduit un départ puis un retour, à l'identique de LocationService,
    pour vérifier la navigation complète des relations (y compris
    mouvements_stock.location_ligne_id, cinquième FK d'origine)."""
    with session_scope(initialized_db) as session:
        user, _category, client, article = _create_base_data(session)
        location = _create_location(session, client.id, user.id)
        ligne = LocationLigne(
            location_id=location.id, article_id=article.id,
            qte_prevue=Decimal("2.000"), qte_en_location=Decimal("2.000"), tarif_jour=Decimal("500.00"),
        )
        session.add(ligne)
        session.flush()

        sortie_mouvement = MouvementStock(
            article_id=article.id, type=TypeMouvement.LOCATION_SORTIE,
            quantite=Decimal("-2.000"), stock_avant=Decimal("10.000"), stock_apres=Decimal("8.000"),
            location_ligne_id=ligne.id, user_id=user.id,
        )
        session.add(sortie_mouvement)

        retour = LocationRetour(
            location_ligne_id=ligne.id, date_retour=date(2026, 1, 2),
            quantite_bon_etat=Decimal("2.000"), quantite_immobilisee=Decimal("0.000"),
            montant_facture=Decimal("1000.00"), user_id=user.id,
        )
        session.add(retour)

        retour_mouvement = MouvementStock(
            article_id=article.id, type=TypeMouvement.LOCATION_RETOUR,
            quantite=Decimal("2.000"), stock_avant=Decimal("8.000"), stock_apres=Decimal("10.000"),
            location_ligne_id=ligne.id, user_id=user.id,
        )
        session.add(retour_mouvement)
        session.flush()

        assert ligne.retours[0] is retour
        assert retour.location_ligne is ligne
        assert sortie_mouvement.location_ligne is ligne
        assert retour_mouvement.location_ligne is ligne


def test_location_paiement_relationship(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user, _category, client, _article = _create_base_data(session)
        location = _create_location(session, client.id, user.id)

        paiement = LocationPaiement(location_id=location.id, montant=Decimal("500.00"), user_id=user.id)
        session.add(paiement)
        session.flush()

        assert location.paiements[0] is paiement
        assert paiement.location is location


def test_article_mode_gestion_changement_relationship(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user, _category, _client, article = _create_base_data(session)

        changement = ArticleModeGestionChangement(
            article_id=article.id, ancien_mode=ModeGestionArticle.VENTE,
            nouveau_mode=ModeGestionArticle.LOCATION, user_id=user.id,
        )
        session.add(changement)
        session.flush()

        assert changement.article is article
        assert changement.user is user


# -- clés étrangères ---------------------------------------------------------------


def test_location_ligne_rejects_unknown_article(initialized_db: Settings) -> None:
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            user, _category, client, _article = _create_base_data(session)
            location = _create_location(session, client.id, user.id)
            session.add(
                LocationLigne(
                    location_id=location.id, article_id=999999,
                    qte_prevue=Decimal("1.000"), tarif_jour=Decimal("500.00"),
                )
            )


def test_location_rejects_unknown_client(initialized_db: Settings) -> None:
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            role = session.query(Role).filter_by(nom="Administrateur").one()
            user = User(username="admin_fk", password_hash=hash_password("Motdepasse!23"), role_id=role.id, roles=[role])
            session.add(user)
            session.flush()
            session.add(
                Location(
                    numero="LOC-ORPHAN", date=date(2026, 1, 1), client_id=999999, user_id=user.id,
                    statut=StatutLocation.BROUILLON, caution_montant=Decimal("0"), caution_rendue=Decimal("0"),
                )
            )


def test_location_retour_rejects_unknown_location_ligne(initialized_db: Settings) -> None:
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            role = session.query(Role).filter_by(nom="Administrateur").one()
            user = User(username="admin_fk2", password_hash=hash_password("Motdepasse!23"), role_id=role.id, roles=[role])
            session.add(user)
            session.flush()
            session.add(
                LocationRetour(
                    location_ligne_id=999999, date_retour=date(2026, 1, 1),
                    quantite_bon_etat=Decimal("1.000"), montant_facture=Decimal("0"), user_id=user.id,
                )
            )


def test_mouvement_stock_rejects_unknown_location_ligne(initialized_db: Settings) -> None:
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            user, _category, _client, article = _create_base_data(session)
            session.add(
                MouvementStock(
                    article_id=article.id, type=TypeMouvement.LOCATION_SORTIE,
                    quantite=Decimal("-1.000"), stock_avant=Decimal("10.000"), stock_apres=Decimal("9.000"),
                    location_ligne_id=999999, user_id=user.id,
                )
            )


# -- contraintes CHECK --------------------------------------------------------------


def test_location_ligne_rejects_non_positive_qte_prevue(initialized_db: Settings) -> None:
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            user, _category, client, article = _create_base_data(session)
            location = _create_location(session, client.id, user.id)
            session.add(
                LocationLigne(
                    location_id=location.id, article_id=article.id,
                    qte_prevue=Decimal("0.000"), tarif_jour=Decimal("500.00"),
                )
            )


def test_location_caution_rendue_cannot_exceed_montant(initialized_db: Settings) -> None:
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            user, _category, client, _article = _create_base_data(session)
            session.add(
                Location(
                    numero="LOC-CAUTION-KO", date=date(2026, 1, 1), client_id=client.id, user_id=user.id,
                    statut=StatutLocation.BROUILLON,
                    caution_montant=Decimal("1000.00"), caution_rendue=Decimal("1000.01"),
                )
            )


def test_location_retour_rejects_zero_total_quantity(initialized_db: Settings) -> None:
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            user, _category, client, article = _create_base_data(session)
            location = _create_location(session, client.id, user.id)
            ligne = LocationLigne(
                location_id=location.id, article_id=article.id,
                qte_prevue=Decimal("1.000"), qte_en_location=Decimal("1.000"), tarif_jour=Decimal("500.00"),
            )
            session.add(ligne)
            session.flush()
            session.add(
                LocationRetour(
                    location_ligne_id=ligne.id, date_retour=date(2026, 1, 2),
                    quantite_bon_etat=Decimal("0"), quantite_immobilisee=Decimal("0"),
                    montant_facture=Decimal("0"), user_id=user.id,
                )
            )


def test_location_paiement_rejects_non_positive_montant(initialized_db: Settings) -> None:
    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            user, _category, client, _article = _create_base_data(session)
            location = _create_location(session, client.id, user.id)
            session.add(LocationPaiement(location_id=location.id, montant=Decimal("0"), user_id=user.id))
