from datetime import date
from decimal import Decimal

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import ExitReason
from app.models.documents import Sortie
from app.models.enums import StatutOperation
from app.models.rbac import Role
from app.models.user import User
from app.repositories.sortie_repository import SortieRepository
from app.security.password_hashing import hash_password


def _make_motif(session, libelle="Perte") -> ExitReason:
    motif = ExitReason(libelle=libelle)
    session.add(motif)
    session.flush()
    return motif


def _make_user(session, username="op1") -> User:
    role = session.query(Role).filter_by(nom="Administrateur").one()
    user = User(username=username, password_hash=hash_password("Password!23"), role_id=role.id)
    session.add(user)
    session.flush()
    return user


def _make_sortie(session, motif, user, numero, **overrides) -> Sortie:
    defaults = dict(
        numero=numero,
        date=date(2026, 1, 1),
        motif_id=motif.id,
        user_id=user.id,
        statut=StatutOperation.BROUILLON,
    )
    defaults.update(overrides)
    sortie = Sortie(**defaults)
    session.add(sortie)
    session.flush()
    return sortie


def test_find_by_numero(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        motif = _make_motif(session)
        user = _make_user(session)
        _make_sortie(session, motif, user, "SOR-000001")

        repo = SortieRepository(session)
        assert repo.find_by_numero("SOR-000001") is not None
        assert repo.find_by_numero("SOR-999999") is None


def test_search_matches_numero_reference_beneficiaire_or_motif(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        motif_a = _make_motif(session, "Perte")
        motif_b = _make_motif(session, "Casse")
        user = _make_user(session)
        _make_sortie(session, motif_a, user, "SOR-000001", reference="REF-100", beneficiaire="Service A")
        _make_sortie(session, motif_b, user, "SOR-000002", reference="REF-200", beneficiaire="Service B")

        repo = SortieRepository(session)
        assert {s.numero for s in repo.search("SOR-000001")} == {"SOR-000001"}
        assert {s.numero for s in repo.search("REF-200")} == {"SOR-000002"}
        assert {s.numero for s in repo.search("Service A")} == {"SOR-000001"}
        assert {s.numero for s in repo.search("Casse")} == {"SOR-000002"}


def test_search_filters_by_motif_id(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        motif_a = _make_motif(session, "Perte")
        motif_b = _make_motif(session, "Casse")
        user = _make_user(session)
        _make_sortie(session, motif_a, user, "SOR-000001")
        _make_sortie(session, motif_b, user, "SOR-000002")

        repo = SortieRepository(session)
        assert {s.numero for s in repo.search(motif_id=motif_a.id)} == {"SOR-000001"}


def test_search_filters_by_statut(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        motif = _make_motif(session)
        user = _make_user(session)
        _make_sortie(session, motif, user, "SOR-000001", statut=StatutOperation.BROUILLON)
        _make_sortie(session, motif, user, "SOR-000002", statut=StatutOperation.VALIDEE)

        repo = SortieRepository(session)
        assert {s.numero for s in repo.search(statut=StatutOperation.VALIDEE)} == {"SOR-000002"}


def test_count_all_reflects_number_of_exits(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        motif = _make_motif(session)
        user = _make_user(session)
        repo = SortieRepository(session)
        assert repo.count_all() == 0

        _make_sortie(session, motif, user, "SOR-000001")
        assert repo.count_all() == 1

        _make_sortie(session, motif, user, "SOR-000002")
        assert repo.count_all() == 2
