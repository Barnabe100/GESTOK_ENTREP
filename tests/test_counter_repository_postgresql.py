"""Équivalent PostgreSQL de ``tests/test_counter_repository.py`` — même
scénario de concurrence, contre un serveur PostgreSQL 16.15 réel plutôt
que SQLite (verrou de ligne PostgreSQL au lieu du verrou base SQLite).

Base/rôle de test dédiés, isolation et squelette de fixture : même
convention que ``tests/test_document_validation_concurrency_postgresql.py``
(voir ce fichier pour le détail déjà établi des principes repris ici)."""
from __future__ import annotations

import os
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from app.repositories.counter_repository import CounterRepository
from tests.conftest import _full_access_test_licence

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_COUNTER_REPO"


@pytest.fixture()
def postgresql_initialized_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    if _PG_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )
    monkeypatch.setenv(_PG_PASSWORD_ENV_VAR, _PG_PASSWORD)
    settings = Settings(
        environment="test", db_path=tmp_path / "unused-for-postgresql.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER,
            password_env_var=_PG_PASSWORD_ENV_VAR, connect_timeout_seconds=5,
        ),
    )
    db_session_module.reset_engine_cache()
    try:
        probe_engine = db_session_module.create_db_engine(settings)
        with probe_engine.connect() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            connection.commit()
        probe_engine.dispose()
    except OperationalError as exc:
        db_session_module.reset_engine_cache()
        pytest.skip(f"Serveur PostgreSQL de test non atteignable ({_PG_HOST}:{_PG_PORT}) : {exc}")

    init_database(settings)
    with db_session_module.session_scope(settings) as session:
        seed_reference_data(session)
        session.add(_full_access_test_licence())

    yield settings

    engine = db_session_module.get_engine(settings)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()
    db_session_module.reset_engine_cache()


def test_next_value_increments_from_zero_on_postgresql(postgresql_initialized_db: Settings) -> None:
    with db_session_module.session_scope(postgresql_initialized_db) as session:
        assert CounterRepository(session).next_value("VNT") == 1
    with db_session_module.session_scope(postgresql_initialized_db) as session:
        assert CounterRepository(session).next_value("VNT") == 2


def test_next_value_rolled_back_transaction_does_not_burn_the_number_on_postgresql(
    postgresql_initialized_db: Settings,
) -> None:
    try:
        with db_session_module.session_scope(postgresql_initialized_db) as session:
            assert CounterRepository(session).next_value("VNT") == 1
            raise RuntimeError("échec simulé après incrémentation, avant la fin de la transaction")
    except RuntimeError:
        pass

    with db_session_module.session_scope(postgresql_initialized_db) as session:
        assert CounterRepository(session).next_value("VNT") == 1


def test_next_value_concurrent_calls_never_collide_on_real_postgresql(
    postgresql_initialized_db: Settings,
) -> None:
    """Même scénario que la version SQLite, mais avec un moteur SQLAlchemy
    INDÉPENDANT par thread (voir ``tests/test_multisite_load_postgresql.py``
    pour l'explication complète de cette nécessité) : fidèle à N postes
    réels, chacun avec son propre pool de connexions, plutôt qu'un seul
    moteur partagé par le processus de test — ici, le verrou de ligne
    PostgreSQL sur la ligne du compteur sérialise les écritures
    concurrentes entre connexions réellement distinctes."""
    n = 10
    barrier = threading.Barrier(n)
    results: list = [None] * n
    engines: list = []
    engines_lock = threading.Lock()

    def _call(index: int) -> None:
        engine = db_session_module.create_db_engine(postgresql_initialized_db)
        with engines_lock:
            engines.append(engine)
        session_factory = db_session_module.sessionmaker(bind=engine, expire_on_commit=False, future=True)
        try:
            barrier.wait(timeout=10)
        except threading.BrokenBarrierError:  # pragma: no cover - diagnostic
            pass
        session = session_factory()
        try:
            results[index] = CounterRepository(session).next_value("VNT")
            session.commit()
        finally:
            session.close()

    threads = [threading.Thread(target=_call, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    for engine in engines:
        engine.dispose()

    assert None not in results, f"un appel n'a pas terminé : {results}"
    assert sorted(results) == list(range(1, n + 1))
