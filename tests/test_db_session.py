from sqlalchemy import text

from app.config.settings import Settings
from app.db.session import get_engine, session_scope
from app.models.rbac import Role


def test_engine_connects_to_sqlite_file(test_settings: Settings) -> None:
    engine = get_engine(test_settings)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar()
    assert result == 1
    assert test_settings.db_path.exists()


def test_foreign_keys_pragma_is_enabled_on_every_connection(test_settings: Settings) -> None:
    engine = get_engine(test_settings)
    with engine.connect() as connection:
        value = connection.execute(text("PRAGMA foreign_keys")).scalar()
    assert value == 1


def test_session_scope_commits_on_success(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add(Role(nom="TestRole", description="rôle de test"))

    with session_scope(initialized_db) as session:
        role = session.query(Role).filter_by(nom="TestRole").one_or_none()
    assert role is not None


def test_session_scope_rolls_back_on_exception(initialized_db: Settings) -> None:
    class _Boom(Exception):
        pass

    try:
        with session_scope(initialized_db) as session:
            session.add(Role(nom="RoleQuiDoitDisparaitre", description=""))
            session.flush()
            raise _Boom("échec volontaire")
    except _Boom:
        pass

    with session_scope(initialized_db) as session:
        role = session.query(Role).filter_by(nom="RoleQuiDoitDisparaitre").one_or_none()
    assert role is None
