"""Tests d'intégration de la synchronisation automatique (Chantier D) dans
``MainWindow``, contre un serveur PostgreSQL 16.15 réel — deux « postes »
simulés par deux piles de services (``ServiceRegistry``) distinctes
partageant la même base, à l'identique de
``tests/test_document_validation_concurrency_postgresql.py``.

Les minuteurs réels (``QTimer``) ne sont jamais attendus ici (un test ne
doit jamais dépendre d'un délai d'horloge réel) : les méthodes qu'ils
déclenchent (``_poll_change_notifications``/``_reconcile_current_page``)
sont appelées directement, exactement comme le ferait un déclenchement de
minuteur.
"""
from __future__ import annotations

import os
import time

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
from app.views.main_window import MainWindow
from app.views.pages.categories_page import CategoriesPage
from tests.conftest import DEFAULT_TEST_PASSWORD, TEST_LICENSE_PUBLIC_KEY_BYTES, _full_access_test_licence

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_MAIN_WINDOW_SYNC"


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


@pytest.fixture()
def pg_login_as(postgresql_initialized_db: Settings):
    settings = postgresql_initialized_db
    counter = {"n": 0}

    def _login_as(role_name: str = "Administrateur") -> tuple[ServiceRegistry, Settings]:
        counter["n"] += 1
        username = f"pgtest_mainwindow_{counter['n']}"
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


def test_change_listener_is_active_under_postgresql(qtbot, pg_login_as) -> None:
    stack, _ = pg_login_as()
    window = MainWindow(stack)
    qtbot.addWidget(window)

    assert window._change_listener is not None
    window.close()


def test_closing_the_window_stops_both_synchronization_timers(qtbot, pg_login_as) -> None:
    """Correctif (suite de non-régression) : ``close()`` masque la fenêtre
    mais ne détruit pas immédiatement un ``QTimer`` qui lui est parenté —
    un minuteur resté actif après une fermeture a été observé se déclencher
    bien plus tard, dans une suite de tests ultérieure sans rapport,
    échouant sur un mot de passe de test déjà hors de portée. ``close()``
    doit donc arrêter explicitement les deux minuteurs de synchronisation,
    jamais compter sur la seule destruction différée de l'objet Qt."""
    stack, _ = pg_login_as()
    window = MainWindow(stack)
    qtbot.addWidget(window)

    assert window._change_listener_timer.isActive()
    assert window._change_reconciliation_timer.isActive()

    window.close()

    assert not window._change_listener_timer.isActive()
    assert not window._change_reconciliation_timer.isActive()


def test_poll_change_notifications_refreshes_categories_page_after_remote_change(qtbot, pg_login_as) -> None:
    """Scénario central du mandat (§6, test obligatoire n°2) : un poste A
    crée une catégorie ; sans aucune action locale sur le poste B (ouvert
    sur l'écran Catégories), la nouvelle catégorie doit apparaître dès le
    prochain sondage — jamais besoin d'un clic « Actualiser »."""
    stack_b, settings = pg_login_as()
    window_b = MainWindow(stack_b)
    qtbot.addWidget(window_b)
    categories_index = window_b.visible_modules.index("Catégories")
    window_b.navigation_list.setCurrentRow(categories_index)
    categories_page_b = window_b.page_stack.widget(categories_index)
    assert isinstance(categories_page_b, CategoriesPage)
    initial_row_count = categories_page_b.table.rowCount()

    # Poste A : crée une catégorie dans une pile de services INDÉPENDANTE
    # (jamais ``stack_b``), simulant un poste physiquement distinct.
    stack_a, _ = pg_login_as()
    stack_a.categories.create_category("Catégorie créée sur un autre poste")

    time.sleep(0.2)  # laisse le temps au NOTIFY d'atteindre la connexion LISTEN du poste B.
    window_b._poll_change_notifications()

    assert categories_page_b.table.rowCount() == initial_row_count + 1
    names = {categories_page_b.table.item(row, 0).text() for row in range(categories_page_b.table.rowCount())}
    assert "Catégorie créée sur un autre poste" in names
    window_b.close()


def test_poll_change_notifications_never_refreshes_an_unrelated_page_s_selection(qtbot, pg_login_as) -> None:
    """Préserve la sélection/saisie en cours (§6) : un sondage qui ne
    rafraîchit QUE l'écran actif ne doit jamais perturber un formulaire
    ouvert ailleurs — ici vérifié indirectement (aucune exception, aucun
    changement d'écran) en restant sur le Dashboard pendant la création
    distante."""
    stack_b, _ = pg_login_as()
    window_b = MainWindow(stack_b)
    qtbot.addWidget(window_b)
    assert window_b.page_title_label.text() == "Dashboard"

    stack_a, _ = pg_login_as()
    stack_a.categories.create_category("Catégorie pendant Dashboard")

    time.sleep(0.2)
    window_b._poll_change_notifications()

    assert window_b.page_title_label.text() == "Dashboard"
    window_b.close()


def test_reconcile_current_page_refreshes_even_without_polling(qtbot, pg_login_as) -> None:
    """Filet de sécurité (réconciliation périodique) : rafraîchit l'écran
    actif même sans appeler ``_poll_change_notifications`` au préalable —
    couvre une notification manquée."""
    stack_b, _ = pg_login_as()
    window_b = MainWindow(stack_b)
    qtbot.addWidget(window_b)
    categories_index = window_b.visible_modules.index("Catégories")
    window_b.navigation_list.setCurrentRow(categories_index)
    categories_page_b = window_b.page_stack.widget(categories_index)
    initial_row_count = categories_page_b.table.rowCount()

    stack_a, _ = pg_login_as()
    stack_a.categories.create_category("Catégorie via réconciliation")

    window_b._reconcile_current_page()

    assert categories_page_b.table.rowCount() == initial_row_count + 1
    window_b.close()
