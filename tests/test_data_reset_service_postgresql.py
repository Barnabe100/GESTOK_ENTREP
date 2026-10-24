"""Incident « PRAGMA sous PostgreSQL » : la réinitialisation des données
métier (``DataResetService.reset_business_data``) exécutait
``PRAGMA integrity_check`` sans condition de moteur — syntaxe propre à
SQLite, rejetée par PostgreSQL (``psycopg.errors.SyntaxError``), ce qui
annulait systématiquement l'opération (rollback automatique de
``session_scope`` : aucune perte de donnée, mais la réinitialisation
échouait toujours sous PostgreSQL). Voir
``app/services/system/data_reset_service.py`` pour le correctif.

Même principe d'isolation que les autres suites PostgreSQL de ce projet
(``tests/test_document_validation_concurrency_postgresql.py``,
``tests/test_postgresql_backup_engine.py``) : base/rôle de test dédiés
(jamais la base applicative, jamais une base client), ignorés proprement
(``pytest.skip``) si le serveur ou ``STOCKMANAGER_TEST_PG_PASSWORD`` sont
indisponibles — jamais présenté comme un échec de l'application. Fixtures
dupliquées localement plutôt qu'ajoutées à ``tests/conftest.py`` (utilisé
par des centaines d'autres tests), à l'identique de la convention déjà en
place dans les fichiers cités ci-dessus.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.registry import ServiceRegistry, build_service_registry
from app.utils.exceptions import ValidationError
from tests.conftest import DEFAULT_TEST_PASSWORD, TEST_LICENSE_PUBLIC_KEY_BYTES, _full_access_test_licence
from tests.test_data_reset_service import _seed_full_business_data

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
# Jamais de valeur de repli en dur : cette variable est obligatoire pour les
# tests PostgreSQL (voir le rapport des lots précédents de ce projet).
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_DATA_RESET"


@pytest.fixture()
def postgresql_initialized_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    """Base PostgreSQL de test dédiée, migrée et pré-remplie — voir le
    même fixture dans tests/test_document_validation_concurrency_postgresql.py."""
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


@pytest.fixture()
def pg_login_as(postgresql_initialized_db: Settings):
    """Équivalent PostgreSQL de tests/conftest.py::login_as."""
    settings = postgresql_initialized_db
    counter = {"n": 0}

    def _login_as(role_name: str = "Administrateur") -> tuple[ServiceRegistry, Settings]:
        counter["n"] += 1
        username = f"pgtest_datareset_{role_name.lower()}_{counter['n']}"
        with db_session_module.session_scope(settings) as session:
            role = session.query(Role).filter_by(nom=role_name).one()
            session.add(
                User(
                    username=username, password_hash=hash_password(DEFAULT_TEST_PASSWORD),
                    role_id=role.id, roles=[role], actif=True,
                )
            )
        stack = build_service_registry(settings, license_public_key_bytes=TEST_LICENSE_PUBLIC_KEY_BYTES)
        stack.auth.login(username, DEFAULT_TEST_PASSWORD)
        return stack, settings

    return _login_as


def _business_table_counts(settings: Settings) -> dict[str, int]:
    from app.models.catalog import Article, ArticleModeGestionChangement, Category, ExitReason, Supplier
    from app.models.client import Client
    from app.models.documents import Entree, EntreeLigne, Sortie, SortieLigne, Vente, VenteLigne
    from app.models.inventory import Inventaire, InventaireLigne
    from app.models.movement import MouvementStock
    from app.models.payment import Paiement
    from app.models.rental import Location, LocationLigne, LocationPaiement, LocationRetour

    models = {
        "articles": Article, "categories": Category, "fournisseurs": Supplier, "motifs_sortie": ExitReason,
        "clients": Client, "entrees": Entree, "entree_lignes": EntreeLigne, "sorties": Sortie,
        "sortie_lignes": SortieLigne, "ventes": Vente, "vente_lignes": VenteLigne,
        "inventaires": Inventaire, "inventaire_lignes": InventaireLigne,
        "mouvements_stock": MouvementStock, "paiements": Paiement,
        "locations": Location, "location_lignes": LocationLigne,
        "location_retours": LocationRetour, "location_paiements": LocationPaiement,
        "article_mode_gestion_changements": ArticleModeGestionChangement,
    }
    with db_session_module.session_scope(settings) as session:
        return {label: session.query(model).count() for label, model in models.items()}


def test_reset_succeeds_on_postgresql(pg_login_as) -> None:
    """Reproduit exactement le symptôme signalé : la réinitialisation doit
    réussir sous PostgreSQL, pas seulement sous SQLite."""
    stack, settings = pg_login_as()
    _seed_full_business_data(stack)
    assert sum(_business_table_counts(settings).values()) > 0

    result = stack.data_reset.reset_business_data()

    assert result.success is True
    assert sum(_business_table_counts(settings).values()) == 0


def test_reset_never_executes_pragma_on_postgresql(pg_login_as, monkeypatch) -> None:
    """Preuve directe (§D.3) : PRAGMA integrity_check n'est jamais construit
    ni exécuté sous PostgreSQL — pas seulement « la réinitialisation ne
    plante plus »."""
    import app.services.system.data_reset_service as data_reset_module

    stack, _ = pg_login_as()
    _seed_full_business_data(stack)

    original_text = data_reset_module.text
    executed_sql: list[str] = []

    def _spy_text(sql_string):
        executed_sql.append(sql_string)
        return original_text(sql_string)

    monkeypatch.setattr(data_reset_module, "text", _spy_text)

    result = stack.data_reset.reset_business_data()

    assert result.success is True
    assert not any("PRAGMA" in sql for sql in executed_sql)


def test_reset_rollback_on_foreign_key_violation_postgresql(pg_login_as, monkeypatch) -> None:
    """Équivalent PostgreSQL de
    tests/test_data_reset_service.py::test_reset_remains_atomic_if_locations_tables_missing_from_delete_order
    — réinjecte un ordre de suppression fautif (une table enfant supprimée
    après son parent) pour prouver qu'une violation de clé étrangère réelle,
    sous PostgreSQL (qui l'applique nativement, sans équivalent de
    ``PRAGMA foreign_keys``), déclenche un rollback complet : aucune
    suppression partielle, aucune donnée perdue."""
    from app.models.catalog import Article, Category
    from app.models.client import Client
    from app.models.documents import Vente, VenteLigne

    faulty_delete_order = [
        ("ventes", Vente),  # supprimée AVANT vente_lignes, qui la référence -> violation FK.
        ("vente_lignes", VenteLigne),
        ("articles", Article),
        ("clients", Client),
        ("categories", Category),
    ]
    monkeypatch.setattr("app.services.system.data_reset_service._DELETE_ORDER", faulty_delete_order)

    stack, settings = pg_login_as()
    _seed_full_business_data(stack)
    counts_before = _business_table_counts(settings)
    assert sum(counts_before.values()) > 0

    with pytest.raises(ValidationError):
        stack.data_reset.reset_business_data()

    counts_after = _business_table_counts(settings)
    assert counts_after == counts_before  # rien n'a été supprimé (rollback complet)


def test_reset_preserves_users_roles_permissions_on_postgresql(pg_login_as) -> None:
    from app.models.rbac import Permission, Role as RoleModel
    from app.models.user import User as UserModel

    stack, settings = pg_login_as()
    _seed_full_business_data(stack)

    stack.data_reset.reset_business_data()

    with db_session_module.session_scope(settings) as session:
        assert session.query(UserModel).count() > 0
        assert session.query(RoleModel).count() > 0
        assert session.query(Permission).count() > 0


def test_administrateur_can_still_authenticate_after_reset_on_postgresql(pg_login_as) -> None:
    stack, _ = pg_login_as()
    _seed_full_business_data(stack)

    stack.data_reset.reset_business_data()

    stack.auth.logout()
    stack.auth.login("pgtest_datareset_administrateur_1", DEFAULT_TEST_PASSWORD)
    assert stack.auth.current_user is not None
