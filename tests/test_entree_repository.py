from datetime import date
from decimal import Decimal

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import Article, Category, Supplier
from app.models.documents import Entree
from app.models.enums import StatutOperation
from app.models.rbac import Role
from app.models.user import User
from app.repositories.entree_repository import EntreeRepository
from app.security.password_hashing import hash_password


def _make_supplier(session, nom="Fournisseur A") -> Supplier:
    supplier = Supplier(nom=nom)
    session.add(supplier)
    session.flush()
    return supplier


def _make_user(session, username="op1") -> User:
    role = session.query(Role).filter_by(nom="Administrateur").one()
    user = User(username=username, password_hash=hash_password("Password!23"), role_id=role.id)
    session.add(user)
    session.flush()
    return user


def _make_entree(session, supplier, user, numero, **overrides) -> Entree:
    defaults = dict(
        numero=numero,
        date=date(2026, 1, 1),
        fournisseur_id=supplier.id,
        user_id=user.id,
        statut=StatutOperation.BROUILLON,
    )
    defaults.update(overrides)
    entree = Entree(**defaults)
    session.add(entree)
    session.flush()
    return entree


def test_find_by_numero(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        supplier = _make_supplier(session)
        user = _make_user(session)
        _make_entree(session, supplier, user, "ENT-000001")

        repo = EntreeRepository(session)
        assert repo.find_by_numero("ENT-000001") is not None
        assert repo.find_by_numero("ENT-999999") is None


def test_search_matches_numero_reference_or_supplier_name(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        supplier_a = _make_supplier(session, "Alpha Boissons")
        supplier_b = _make_supplier(session, "Beta Épicerie")
        user = _make_user(session)
        _make_entree(session, supplier_a, user, "ENT-000001", reference_document="BL-100")
        _make_entree(session, supplier_b, user, "ENT-000002", reference_document="BL-200")

        repo = EntreeRepository(session)
        assert {e.numero for e in repo.search("ENT-000001")} == {"ENT-000001"}
        assert {e.numero for e in repo.search("BL-200")} == {"ENT-000002"}
        assert {e.numero for e in repo.search("Alpha")} == {"ENT-000001"}


def test_search_filters_by_fournisseur_id(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        supplier_a = _make_supplier(session, "Alpha")
        supplier_b = _make_supplier(session, "Beta")
        user = _make_user(session)
        _make_entree(session, supplier_a, user, "ENT-000001")
        _make_entree(session, supplier_b, user, "ENT-000002")

        repo = EntreeRepository(session)
        assert {e.numero for e in repo.search(fournisseur_id=supplier_a.id)} == {"ENT-000001"}


def test_search_filters_by_statut(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        supplier = _make_supplier(session)
        user = _make_user(session)
        _make_entree(session, supplier, user, "ENT-000001", statut=StatutOperation.BROUILLON)
        _make_entree(session, supplier, user, "ENT-000002", statut=StatutOperation.VALIDEE)

        repo = EntreeRepository(session)
        assert {e.numero for e in repo.search(statut=StatutOperation.VALIDEE)} == {"ENT-000002"}


def test_count_all_reflects_number_of_entries(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        supplier = _make_supplier(session)
        user = _make_user(session)
        repo = EntreeRepository(session)
        assert repo.count_all() == 0

        _make_entree(session, supplier, user, "ENT-000001")
        assert repo.count_all() == 1

        _make_entree(session, supplier, user, "ENT-000002")
        assert repo.count_all() == 2
