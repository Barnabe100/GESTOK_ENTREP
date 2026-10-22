"""Lot C (audit de concurrence PostgreSQL) : mêmes scénarios que
``tests/test_document_validation_concurrency.py``, exécutés contre un
serveur PostgreSQL 16.15 réel plutôt que SQLite — voir ce fichier et le
rapport de ce lot pour le contexte complet du défaut corrigé
(``app.utils.atomic_transition.apply_atomic_status_transition``).

Base/rôle de test dédiés (jamais la base applicative, jamais une base
client) : si le serveur ou la variable ``STOCKMANAGER_TEST_PG_PASSWORD``
sont indisponibles, les tests sont ignorés proprement (``pytest.skip``),
jamais présentés comme un échec de l'application — voir aussi
``tests/test_db_session.py``/``tests/test_migrations_postgresql.py`` pour
le même principe. Aucun mot de passe codé en dur ni valeur de repli :
cette variable est obligatoire, conformément au mandat de ce lot.

Isolation (limite déjà documentée aux lots A/B, reconduite ici à
l'identique) : le schéma ``public`` de la base de test dédiée est
réinitialisé avant chaque test — sûr uniquement parce que la suite de ce
projet s'exécute séquentiellement (``pytest-xdist`` n'est pas installé,
vérifié) ; une exécution parallèle imposerait un schéma distinct par
worker, non implémenté ici."""
from __future__ import annotations

import os
import threading
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from app.models.enums import ModeGestionArticle
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.entries.entry_service import EntreeLigneInput
from app.services.exits.exit_service import SortieLigneInput
from app.services.inventory.inventory_service import InventaireLigneInput
from app.services.registry import ServiceRegistry, build_service_registry
from app.services.rentals.location_service import LocationLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import AppError
from tests.conftest import DEFAULT_TEST_PASSWORD, TEST_LICENSE_PUBLIC_KEY_BYTES, _full_access_test_licence

CONCURRENCY_REPETITIONS = 8

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
# Jamais de valeur de repli en dur (voir le rapport de la publication des
# lots A/B) : cette variable est obligatoire pour les tests PostgreSQL.
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_LOT_C"


@pytest.fixture()
def postgresql_initialized_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    """Base PostgreSQL de test dédiée, migrée et pré-remplie (rôles,
    permissions, licence de test à accès complet) — équivalent PostgreSQL
    de ``tests/conftest.py::initialized_db``, volontairement autonome
    (aucune modification de ``conftest.py``, utilisé par des centaines
    d'autres tests)."""
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
    """Équivalent PostgreSQL de ``tests/conftest.py::login_as`` — crée un
    utilisateur Administrateur et retourne (stack, settings)."""
    settings = postgresql_initialized_db
    counter = {"n": 0}

    def _login_as(role_name: str = "Administrateur") -> tuple[ServiceRegistry, Settings]:
        counter["n"] += 1
        username = f"pgtest_{role_name.lower()}_{counter['n']}"
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


def _concurrent_run(*targets) -> list:
    barrier = threading.Barrier(len(targets))
    results: list = [None] * len(targets)

    def _wrap(index: int, fn) -> None:
        try:
            barrier.wait(timeout=10)
        except threading.BrokenBarrierError:
            pass
        try:
            fn()
        except Exception as exc:  # pragma: no cover - diagnostic
            results[index] = exc

    threads = [threading.Thread(target=_wrap, args=(i, fn)) for i, fn in enumerate(targets)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    return results


def _make_sellable_article(stack, reference: str, stock_initial: Decimal):
    category = stack.categories.create_category(f"CAT-{reference}")
    return stack.articles.create_article(
        reference, f"Article {reference}", category.id, "unite",
        Decimal("50"), Decimal("80"), Decimal("0"), stock_initial=stock_initial,
    )


def _make_rental_article(stack, reference: str, stock_initial: Decimal):
    article = _make_sellable_article(stack, reference, stock_initial)
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    return article


# -- Sorties --------------------------------------------------------------------------


def test_concurrent_double_validation_of_same_exit_is_rejected_on_postgresql(pg_login_as) -> None:
    stack, _ = pg_login_as()
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_sellable_article(stack, f"ART-PG-DVC-EXIT-{i}", Decimal("100"))
        reason = stack.exit_reasons.create_exit_reason(f"Motif PG DVC {i}")
        exit_doc = stack.exits.create_exit(reason.id, date.today(), [SortieLigneInput(article.id, Decimal("10"))])

        errors = _concurrent_run(
            lambda eid=exit_doc.id: stack.exits.validate_exit(eid),
            lambda eid=exit_doc.id: stack.exits.validate_exit(eid),
        )
        succeeded = [e for e in errors if e is None]
        failed = [e for e in errors if e is not None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"
        assert len(failed) == 1 and isinstance(failed[0], AppError), f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        sortie_movements = [m for m in movements if m.type.value == "SORTIE"]
        assert len(sortie_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("90.000"), f"itération {i}"


# -- Entrées --------------------------------------------------------------------------


def test_concurrent_double_validation_of_same_entry_is_rejected_on_postgresql(pg_login_as) -> None:
    stack, _ = pg_login_as()
    for i in range(CONCURRENCY_REPETITIONS):
        category = stack.categories.create_category(f"CAT-PG-DVC-ENTRY-{i}")
        supplier = stack.suppliers.create_supplier(f"Fournisseur PG DVC {i}")
        article = stack.articles.create_article(
            f"ART-PG-DVC-ENTRY-{i}", f"Article {i}", category.id, "unite",
            Decimal("50"), Decimal("80"), Decimal("0"), stock_initial=Decimal("0"),
        )
        entry = stack.entries.create_entry(
            supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("10"), Decimal("50"))]
        )

        errors = _concurrent_run(
            lambda eid=entry.id: stack.entries.validate_entry(eid),
            lambda eid=entry.id: stack.entries.validate_entry(eid),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        entree_movements = [m for m in movements if m.type.value == "ENTREE"]
        assert len(entree_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("10.000"), f"itération {i}"


# -- Ventes ---------------------------------------------------------------------------


def test_concurrent_double_validation_of_same_sale_is_rejected_on_postgresql(pg_login_as) -> None:
    stack, _ = pg_login_as()
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_sellable_article(stack, f"ART-PG-DVC-SALE-{i}", Decimal("100"))
        sale = stack.sales.create_sale(date.today(), [VenteLigneInput(article.id, Decimal("10"), Decimal("80"))])

        errors = _concurrent_run(
            lambda sid=sale.id: stack.sales.validate_sale(sid),
            lambda sid=sale.id: stack.sales.validate_sale(sid),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        vente_movements = [m for m in movements if m.type.value == "VENTE"]
        assert len(vente_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("90.000"), f"itération {i}"


# -- Inventaires ------------------------------------------------------------------------


def test_concurrent_double_validation_of_same_inventory_is_rejected_on_postgresql(pg_login_as) -> None:
    stack, _ = pg_login_as()
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_sellable_article(stack, f"ART-PG-DVC-INV-{i}", Decimal("100"))
        inventory = stack.inventory.create_inventory(
            date.today(), [InventaireLigneInput(article.id, Decimal("120"))]
        )

        errors = _concurrent_run(
            lambda iid=inventory.id: stack.inventory.validate_inventory(iid),
            lambda iid=inventory.id: stack.inventory.validate_inventory(iid),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        # Exclut l'AJUSTEMENT initial généré par create_article(stock_initial=...)
        # (sans rapport avec cet inventaire) : seul le mouvement rattaché à
        # ce numéro d'inventaire est significatif ici.
        movements = stack.movements.list_movements(article_id=article.id)
        ajustement_movements = [
            m for m in movements if m.type.value == "AJUSTEMENT" and m.reference_operation == inventory.numero
        ]
        assert len(ajustement_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("120.000"), f"itération {i}"


# -- Locations : départ -----------------------------------------------------------------


def test_concurrent_double_departure_of_same_location_is_rejected_on_postgresql(pg_login_as) -> None:
    stack, _ = pg_login_as()
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_rental_article(stack, f"ART-PG-DVC-DEP-{i}", Decimal("20"))
        client = stack.clients.create_client(f"Client PG DVC {i}")
        location = stack.rentals.create_location(
            date.today(), client.id, [LocationLigneInput(article.id, Decimal("5"), tarif_jour=Decimal("100"))]
        )
        confirmed = stack.rentals.confirm_location(location.id)

        errors = _concurrent_run(
            lambda lid=confirmed.id: stack.rentals.depart_location(lid, date.today()),
            lambda lid=confirmed.id: stack.rentals.depart_location(lid, date.today()),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        depart_movements = [m for m in movements if m.type.value == "LOCATION_SORTIE"]
        assert len(depart_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("15.000"), f"itération {i}"


# -- Locations : retour (même ligne, double retour concurrent) -------------------------


def test_concurrent_double_return_of_same_location_line_never_goes_negative_on_postgresql(pg_login_as) -> None:
    """Voir ``tests/test_document_validation_concurrency.py`` (même nom de
    test, sans ``_on_postgresql``) pour le contexte complet de ce défaut
    distinct (``qte_en_location`` pouvant passer en négatif)."""
    stack, _ = pg_login_as()
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_rental_article(stack, f"ART-PG-DVC-RET-{i}", Decimal("20"))
        client = stack.clients.create_client(f"Client PG DVC RET {i}")
        location = stack.rentals.create_location(
            date.today(), client.id, [LocationLigneInput(article.id, Decimal("10"), tarif_jour=Decimal("100"))]
        )
        confirmed = stack.rentals.confirm_location(location.id)
        departed = stack.rentals.depart_location(confirmed.id, date.today())
        ligne_id = departed.lignes[0].id

        errors = _concurrent_run(
            lambda lid=departed.id: stack.rentals.return_location_line(
                lid, ligne_id, date.today(), quantite_bon_etat=Decimal("10")
            ),
            lambda lid=departed.id: stack.rentals.return_location_line(
                lid, ligne_id, date.today(), quantite_bon_etat=Decimal("10")
            ),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        retour_movements = [m for m in movements if m.type.value == "LOCATION_RETOUR"]
        assert len(retour_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("20.000"), f"itération {i}"

        final_location = stack.rentals.get_location(departed.id)
        final_ligne = next(l for l in final_location.lignes if l.id == ligne_id)
        assert final_ligne.qte_en_location == Decimal("0.000"), f"itération {i}"
        assert final_ligne.qte_en_location >= 0, f"itération {i}"
