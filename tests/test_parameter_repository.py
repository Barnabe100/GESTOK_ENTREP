from app.config.settings import Settings
from app.db.session import session_scope
from app.repositories.parameter_repository import ParameterRepository


def test_get_value_returns_none_when_absent(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        repo = ParameterRepository(session)
        assert repo.get_value("inconnu.cle") is None


def test_set_value_then_get_value(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        repo = ParameterRepository(session)
        repo.set_value("backup.destination", "/tmp/backups")

    with session_scope(initialized_db) as session:
        repo = ParameterRepository(session)
        assert repo.get_value("backup.destination") == "/tmp/backups"


def test_set_value_overwrites_existing(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        repo = ParameterRepository(session)
        repo.set_value("backup.retention", "5")
        repo.set_value("backup.retention", "10")

    with session_scope(initialized_db) as session:
        repo = ParameterRepository(session)
        assert repo.get_value("backup.retention") == "10"


def test_set_value_persists_across_sessions(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        ParameterRepository(session).set_value("backup.auto_enabled", "true")

    with session_scope(initialized_db) as session:
        assert ParameterRepository(session).get_value("backup.auto_enabled") == "true"
