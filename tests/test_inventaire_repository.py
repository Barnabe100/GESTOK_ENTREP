from datetime import date, datetime

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.enums import StatutInventaire
from app.models.inventory import Inventaire
from app.models.rbac import Role
from app.models.user import User
from app.repositories.inventaire_repository import InventaireRepository
from app.security.password_hashing import hash_password


def _make_user(session, username="op1") -> User:
    role = session.query(Role).filter_by(nom="Administrateur").one()
    user = User(username=username, password_hash=hash_password("Password!23"), role_id=role.id)
    session.add(user)
    session.flush()
    return user


def _make_inventaire(session, user, numero, **overrides) -> Inventaire:
    defaults = dict(
        numero=numero,
        date=date(2026, 1, 1),
        user_id=user.id,
        statut=StatutInventaire.BROUILLON,
    )
    defaults.update(overrides)
    inventaire = Inventaire(**defaults)
    session.add(inventaire)
    session.flush()
    return inventaire


def test_find_by_numero(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        _make_inventaire(session, user, "INV-000001")

        repo = InventaireRepository(session)
        assert repo.find_by_numero("INV-000001") is not None
        assert repo.find_by_numero("INV-999999") is None


def test_search_matches_numero(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        _make_inventaire(session, user, "INV-000001")
        _make_inventaire(session, user, "INV-000002")

        repo = InventaireRepository(session)
        assert {i.numero for i in repo.search("INV-000001")} == {"INV-000001"}


def test_search_filters_by_statut(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        _make_inventaire(session, user, "INV-000001", statut=StatutInventaire.BROUILLON)
        _make_inventaire(session, user, "INV-000002", statut=StatutInventaire.VALIDE)

        repo = InventaireRepository(session)
        assert {i.numero for i in repo.search(statut=StatutInventaire.VALIDE)} == {"INV-000002"}


def test_count_all_reflects_number_of_inventories(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        repo = InventaireRepository(session)
        assert repo.count_all() == 0

        _make_inventaire(session, user, "INV-000001")
        assert repo.count_all() == 1

        _make_inventaire(session, user, "INV-000002")
        assert repo.count_all() == 2


def test_search_orders_by_creation_date_not_business_date(initialized_db: Settings) -> None:
    """Chantier B : voir le test équivalent dans tests/test_vente_repository.py."""
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        older_creation = _make_inventaire(session, user, "INV-ANCIEN", date=date(2026, 6, 1))
        older_creation.date_creation = datetime(2026, 1, 1, 8, 0, 0)
        session.flush()

        newer_creation = _make_inventaire(session, user, "INV-RECENT", date=date(2026, 1, 1))
        newer_creation.date_creation = datetime(2026, 6, 1, 8, 0, 0)
        session.flush()

        repo = InventaireRepository(session)
        results = repo.search()

        assert [i.numero for i in results] == ["INV-RECENT", "INV-ANCIEN"]
