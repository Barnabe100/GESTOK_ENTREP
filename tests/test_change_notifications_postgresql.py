"""Tests de ``app.db.change_notifications`` (Chantier D, synchronisation
automatique) contre un serveur PostgreSQL 16.15 réel : une connexion
``LISTEN`` dédiée (simulant un AUTRE poste) doit recevoir un ``NOTIFY``
après le commit d'une opération créant une entité suivie, jamais après un
rollback.

Base/rôle de test dédiés, isolation et squelette de fixture : même
convention que ``tests/test_document_validation_concurrency_postgresql.py``.
"""
from __future__ import annotations

import os

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.change_notifications import CHANGES_CHANNEL
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from tests.conftest import _full_access_test_licence

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_CHANGE_NOTIF"


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


def _psycopg_dsn(settings: Settings) -> str:
    pg = settings.postgresql
    password = os.environ[pg.password_env_var]
    return f"postgresql://{pg.username}:{password}@{pg.host}:{pg.port}/{pg.database}"


def test_commit_creating_a_category_emits_a_notify(postgresql_initialized_db: Settings) -> None:
    settings = postgresql_initialized_db
    listener = psycopg.connect(_psycopg_dsn(settings), autocommit=True)
    listener.execute(f"LISTEN {CHANGES_CHANNEL}")

    from app.models.catalog import Category

    with db_session_module.session_scope(settings) as session:
        session.add(Category(nom="Catégorie synchro"))

    notifications = list(listener.notifies(timeout=5, stop_after=1))
    listener.close()

    assert len(notifications) == 1
    assert notifications[0].payload == "categories"


def test_rollback_never_emits_a_notify(postgresql_initialized_db: Settings) -> None:
    settings = postgresql_initialized_db
    listener = psycopg.connect(_psycopg_dsn(settings), autocommit=True)
    listener.execute(f"LISTEN {CHANGES_CHANNEL}")

    from app.models.catalog import Category

    try:
        with db_session_module.session_scope(settings) as session:
            session.add(Category(nom="Catégorie jamais validée"))
            raise RuntimeError("échec simulé avant la fin de la transaction")
    except RuntimeError:
        pass

    notifications = list(listener.notifies(timeout=1))
    listener.close()

    assert notifications == []


def test_multiple_entity_types_in_one_transaction_are_all_reported(postgresql_initialized_db: Settings) -> None:
    """Une entrée de stock validée modifie à la fois ``Article`` (stock) et
    crée un ``MouvementStock`` — les deux écrans concernés doivent être
    notifiés en une seule émission."""
    settings = postgresql_initialized_db
    listener = psycopg.connect(_psycopg_dsn(settings), autocommit=True)
    listener.execute(f"LISTEN {CHANGES_CHANNEL}")

    from datetime import date
    from decimal import Decimal

    from app.models.rbac import Role
    from app.models.user import User
    from app.security.password_hashing import hash_password
    from app.services.entries.entry_service import EntreeLigneInput
    from app.services.registry import build_service_registry
    from tests.conftest import DEFAULT_TEST_PASSWORD, TEST_LICENSE_PUBLIC_KEY_BYTES

    with db_session_module.session_scope(settings) as session:
        role = session.query(Role).filter_by(nom="Administrateur").one()
        session.add(User(username="notif_user", password_hash=hash_password(DEFAULT_TEST_PASSWORD), role_id=role.id, roles=[role], actif=True))
    stack = build_service_registry(settings, license_public_key_bytes=TEST_LICENSE_PUBLIC_KEY_BYTES)
    stack.auth.login("notif_user", DEFAULT_TEST_PASSWORD)
    category = stack.categories.create_category("CAT-NOTIF")
    supplier = stack.suppliers.create_supplier("Fournisseur notif")
    article = stack.articles.create_article(
        "ART-NOTIF", "Article notif", category.id, "unite", Decimal("50"), Decimal("80"), Decimal("0"),
        stock_initial=Decimal("0"),
    )
    # Purge les notifications émises par la préparation ci-dessus (catégorie,
    # fournisseur, article) avant d'observer celle de l'entrée elle-même.
    list(listener.notifies(timeout=2))

    entry = stack.entries.create_entry(
        supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("10"), Decimal("50"))]
    )
    list(listener.notifies(timeout=2))  # création du brouillon (entrees)

    stack.entries.validate_entry(entry.id)
    notifications = list(listener.notifies(timeout=5, stop_after=1))
    listener.close()

    assert len(notifications) == 1
    types_notifies = set(notifications[0].payload.split(","))
    # "entrees" : le statut BROUILLON -> VALIDEE lui-même (voir
    # apply_atomic_status_transition) ; "articles" : le stock mis à jour
    # (StockService.apply_movement) ; "mouvements_stock" : le nouveau
    # MouvementStock créé — les trois écrans doivent se rafraîchir.
    assert types_notifies == {"articles", "mouvements_stock", "entrees"}
