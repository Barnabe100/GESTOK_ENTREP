from datetime import date
from decimal import Decimal

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.documents import Vente
from app.models.enums import StatutOperation
from app.models.rbac import Role
from app.models.user import User
from app.repositories.vente_repository import VenteRepository
from app.security.password_hashing import hash_password


def _make_user(session, username="op1") -> User:
    role = session.query(Role).filter_by(nom="Administrateur").one()
    user = User(username=username, password_hash=hash_password("Password!23"), role_id=role.id)
    session.add(user)
    session.flush()
    return user


def _make_vente(session, user, numero, **overrides) -> Vente:
    defaults = dict(
        numero=numero,
        date=date(2026, 1, 1),
        user_id=user.id,
        statut=StatutOperation.BROUILLON,
        total=Decimal("0"),
    )
    defaults.update(overrides)
    vente = Vente(**defaults)
    session.add(vente)
    session.flush()
    return vente


def test_find_by_numero(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        _make_vente(session, user, "VNT-000001")

        repo = VenteRepository(session)
        assert repo.find_by_numero("VNT-000001") is not None
        assert repo.find_by_numero("VNT-999999") is None


def test_search_matches_numero(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        _make_vente(session, user, "VNT-000001")
        _make_vente(session, user, "VNT-000002")

        repo = VenteRepository(session)
        assert {v.numero for v in repo.search("VNT-000001")} == {"VNT-000001"}


def test_search_filters_by_statut(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        _make_vente(session, user, "VNT-000001", statut=StatutOperation.BROUILLON)
        _make_vente(session, user, "VNT-000002", statut=StatutOperation.VALIDEE)

        repo = VenteRepository(session)
        assert {v.numero for v in repo.search(statut=StatutOperation.VALIDEE)} == {"VNT-000002"}


def test_count_all_reflects_number_of_sales(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        repo = VenteRepository(session)
        assert repo.count_all() == 0

        _make_vente(session, user, "VNT-000001")
        assert repo.count_all() == 1

        _make_vente(session, user, "VNT-000002")
        assert repo.count_all() == 2


def test_delete_removes_draft_sale(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        user = _make_user(session)
        vente = _make_vente(session, user, "VNT-000001")

        repo = VenteRepository(session)
        repo.delete(vente)

        assert repo.find_by_numero("VNT-000001") is None
