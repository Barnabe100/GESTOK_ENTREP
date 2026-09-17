from app.config.settings import Settings
from app.db.session import session_scope
from app.models.rbac import Role
from app.repositories.base import SQLAlchemyRepository


def test_generic_repository_add_and_get_by_id(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        repo = SQLAlchemyRepository(session, Role)
        created = repo.add(Role(nom="RoleRepoTest", description="test repo"))
        created_id = created.id
        assert created_id is not None

    with session_scope(initialized_db) as session:
        repo = SQLAlchemyRepository(session, Role)
        fetched = repo.get_by_id(created_id)
        assert fetched is not None
        assert fetched.nom == "RoleRepoTest"


def test_generic_repository_get_by_id_returns_none_when_missing(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        repo = SQLAlchemyRepository(session, Role)
        assert repo.get_by_id(999999) is None


def test_generic_repository_list_all_returns_seeded_roles(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        repo = SQLAlchemyRepository(session, Role)
        all_roles = repo.list_all()
    assert len(all_roles) == 4
