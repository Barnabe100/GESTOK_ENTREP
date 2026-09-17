from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import Category
from app.models.enums import StatutActifInactif
from app.repositories.category_repository import CategoryRepository


def test_find_by_name_exact_match_only(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add(Category(nom="Boissons"))
        session.flush()

        repo = CategoryRepository(session)
        assert repo.find_by_name("Boissons") is not None
        assert repo.find_by_name("boissons") is None  # sensible à la casse, comme la contrainte DB
        assert repo.find_by_name("Autre") is None


def test_find_by_name_excludes_given_id(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        category = Category(nom="Boissons")
        session.add(category)
        session.flush()

        repo = CategoryRepository(session)
        assert repo.find_by_name("Boissons", exclude_id=category.id) is None
        assert repo.find_by_name("Boissons", exclude_id=category.id + 1) is not None


def test_search_filters_by_partial_name_case_insensitive(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add_all([Category(nom="Boissons"), Category(nom="Épicerie")])
        session.flush()

        repo = CategoryRepository(session)
        results = repo.search("BOIS")
        assert [c.nom for c in results] == ["Boissons"]


def test_search_can_exclude_inactive_categories(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add_all([
            Category(nom="Active", statut=StatutActifInactif.ACTIF),
            Category(nom="Inactive", statut=StatutActifInactif.INACTIF),
        ])
        session.flush()

        repo = CategoryRepository(session)
        names = {c.nom for c in repo.search(include_inactive=False)}
        assert names == {"Active"}
