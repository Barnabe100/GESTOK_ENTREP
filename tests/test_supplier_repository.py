from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import Supplier
from app.models.enums import StatutActifInactif
from app.repositories.supplier_repository import SupplierRepository


def test_search_matches_name(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add_all([Supplier(nom="Martin SARL"), Supplier(nom="Dupont SA")])
        session.flush()

        repo = SupplierRepository(session)
        assert [s.nom for s in repo.search("martin")] == ["Martin SARL"]


def test_search_matches_city_or_contact(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add_all(
            [
                Supplier(nom="A", ville="Lyon"),
                Supplier(nom="B", contact="Paul Lyon"),
                Supplier(nom="C", ville="Paris"),
            ]
        )
        session.flush()

        repo = SupplierRepository(session)
        names = {s.nom for s in repo.search("lyon")}
        assert names == {"A", "B"}


def test_search_can_exclude_inactive_suppliers(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add_all(
            [
                Supplier(nom="Actif", statut=StatutActifInactif.ACTIF),
                Supplier(nom="Inactif", statut=StatutActifInactif.INACTIF),
            ]
        )
        session.flush()

        repo = SupplierRepository(session)
        names = {s.nom for s in repo.search(include_inactive=False)}
        assert names == {"Actif"}


def test_search_without_term_returns_all_ordered_by_name(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add_all([Supplier(nom="Zorro"), Supplier(nom="Alpha")])
        session.flush()

        repo = SupplierRepository(session)
        assert [s.nom for s in repo.search()] == ["Alpha", "Zorro"]
