"""Connexion SQLite, moteur SQLAlchemy et gestion transactionnelle.

Point d'entrée unique pour obtenir une session : ``session_scope()``. Les
services métier des phases suivantes s'appuieront dessus pour garantir que
toute opération de stock est atomique (commit intégral ou rollback complet).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.utils.logging_config import get_logger

logger = get_logger("db.session")

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """Active la contrainte d'intégrité référentielle sur chaque connexion SQLite.

    SQLite désactive PRAGMA foreign_keys par défaut : sans cet appel, les FK
    déclarées dans les modèles ne seraient jamais vérifiées.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(settings: Optional[Settings] = None) -> Engine:
    from sqlalchemy import create_engine

    settings = settings or get_settings()
    settings.ensure_directories()
    engine = create_engine(
        settings.sqlalchemy_database_uri,
        connect_args={"check_same_thread": False},
        future=True,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    logger.info("Moteur SQLAlchemy créé pour %s", settings.db_path)
    return engine


def get_engine(settings: Optional[Settings] = None) -> Engine:
    global _engine
    if _engine is None:
        _engine = create_db_engine(settings)
    return _engine


def get_session_factory(settings: Optional[Settings] = None) -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(settings), expire_on_commit=False, future=True
        )
    return _session_factory


@contextmanager
def session_scope(settings: Optional[Settings] = None) -> Iterator[Session]:
    """Fournit une session transactionnelle : commit à la sortie normale,
    rollback automatique en cas d'exception. Usage :

        with session_scope() as session:
            session.add(objet)
    """
    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_cache() -> None:
    """Réinitialise le moteur et la fabrique de sessions mis en cache.

    Utilisé par les tests pour isoler chaque scénario sur une base distincte.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
