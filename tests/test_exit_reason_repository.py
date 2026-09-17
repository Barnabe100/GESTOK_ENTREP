from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import ExitReason
from app.models.enums import StatutActifInactif
from app.repositories.exit_reason_repository import ExitReasonRepository, normalize_label


def test_normalize_label_ignores_case_and_surrounding_whitespace() -> None:
    assert normalize_label("Perte") == normalize_label(" perte ")
    assert normalize_label("Perte") == normalize_label("PERTE")


def test_normalize_label_collapses_internal_whitespace() -> None:
    assert normalize_label("Perte   totale") == normalize_label("perte totale")


def test_find_by_normalized_label_matches_case_and_space_variants(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add(ExitReason(libelle="Perte"))
        session.flush()

        repo = ExitReasonRepository(session)
        assert repo.find_by_normalized_label("perte") is not None
        assert repo.find_by_normalized_label("  PERTE  ") is not None
        assert repo.find_by_normalized_label("Casse") is None


def test_find_by_normalized_label_excludes_given_id(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        reason = ExitReason(libelle="Perte")
        session.add(reason)
        session.flush()

        repo = ExitReasonRepository(session)
        assert repo.find_by_normalized_label("Perte", exclude_id=reason.id) is None
        assert repo.find_by_normalized_label("Perte", exclude_id=reason.id + 1) is not None


def test_search_can_exclude_inactive_reasons(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add_all([
            ExitReason(libelle="Actif", statut=StatutActifInactif.ACTIF),
            ExitReason(libelle="Inactif", statut=StatutActifInactif.INACTIF),
        ])
        session.flush()

        repo = ExitReasonRepository(session)
        labels = {r.libelle for r in repo.search(include_inactive=False)}
        assert labels == {"Actif"}
