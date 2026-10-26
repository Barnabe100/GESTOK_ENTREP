"""Chantier A (audit multi-postes) : tests de charge progressifs simulant
2 à 50 postes StockManager Desktop indépendants partageant la même base
PostgreSQL 16.15 de test.

Différence délibérée avec
``tests/test_document_validation_concurrency_postgresql.py`` (qui réutilise
le moteur SQLAlchemy mis en cache par processus, ``app.db.session.get_engine``) :
ici, chaque « poste » simulé construit son **propre** moteur
(``create_db_engine``, jamais ``get_engine``), avec son propre pool de
connexions — fidèle à un déploiement réel où chaque poste est un processus
StockManager Desktop séparé, jamais un pool partagé entre postes. C'est le
scénario que ce fichier doit mesurer : le comportement du socle
SQLAlchemy/PostgreSQL quand ``N`` pools indépendants sollicitent le même
serveur en même temps.

Limite assumée et explicite (jamais dissimulée, voir le rapport de ce
lot) : ces threads tournent dans un seul conteneur Linux partagé (quelques
coeurs), jamais sur ``N`` postes Windows physiques séparés par un réseau
local réel. Un résultat ici démontre l'absence de corruption/blocage
logiciel à charge croissante et donne un ordre de grandeur de débit — il ne
remplace jamais une mesure sur le matériel et le réseau réels du
déploiement visé, qui reste à faire.

Même principe d'isolation que les autres suites PostgreSQL de ce projet :
base/rôle de test dédiés, ignorés proprement (``pytest.skip``) si le
serveur ou ``STOCKMANAGER_TEST_PG_PASSWORD`` sont indisponibles.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

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
from app.services.registry import build_service_registry
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import AppError, ConflictError
from tests.conftest import DEFAULT_TEST_PASSWORD, TEST_LICENSE_PUBLIC_KEY_BYTES, _full_access_test_licence

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_MULTISITE_LOAD"


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


class _ThreadLocalEngineRegistry:
    """Donne à chaque thread (= chaque poste simulé) son propre moteur
    SQLAlchemy et sa propre fabrique de sessions, en remplaçant
    temporairement (voir ``monkeypatch`` dans ``_run_load_test``)
    ``app.db.session.get_engine``/``get_session_factory`` — jamais
    ``app/db/session.py`` lui-même.

    Un premier essai de ce test (voir le rapport de ce lot) mutait
    directement les variables globales ``db_session_module._engine``/
    ``_session_factory`` depuis chaque thread : plusieurs threads
    s'écrasaient alors les uns les autres de façon imprévisible (un thread
    pouvait fermer via ``reset_engine_cache()`` le moteur qu'un AUTRE
    thread, encore en cours d'exécution, s'apprêtait à utiliser —
    constaté concrètement sous la forme d'un ``AttributeError: 'NoneType'
    object has no attribute 'dispose'``). Cette classe élimine le partage :
    chaque thread obtient paresseusement SON propre moteur (stocké dans un
    ``threading.local``), jamais partagé ni fermé par un autre thread —
    fidèle à N postes réels, chacun son propre processus."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._local = threading.local()
        self._all_engines: list = []
        self._lock = threading.Lock()

    def get_engine(self, _settings: Optional[Settings] = None) -> object:
        engine = getattr(self._local, "engine", None)
        if engine is None:
            engine = db_session_module.create_db_engine(self._settings)
            self._local.engine = engine
            with self._lock:
                self._all_engines.append(engine)
        return engine

    def get_session_factory(self, _settings: Optional[Settings] = None) -> object:
        factory = getattr(self._local, "session_factory", None)
        if factory is None:
            factory = db_session_module.sessionmaker(
                bind=self.get_engine(), expire_on_commit=False, future=True
            )
            self._local.session_factory = factory
        return factory

    def dispose_all(self) -> None:
        with self._lock:
            engines, self._all_engines = self._all_engines, []
        for engine in engines:
            engine.dispose()


@dataclass
class LoadTestReport:
    nombre_postes: int
    operations_reussies: int = 0
    operations_rejetees_proprement: int = 0  # ConflictError (numéro en double) — jamais une corruption.
    erreurs_inattendues: list[str] = field(default_factory=list)
    duree_secondes: float = 0.0

    @property
    def debit_operations_par_seconde(self) -> float:
        return self.operations_reussies / self.duree_secondes if self.duree_secondes > 0 else 0.0


def _run_one_post_creating_a_sale(settings: Settings, index: int, article_id: int, report: LoadTestReport) -> None:
    """Exécuté dans son propre thread — ``db_session_module.get_engine``/
    ``get_session_factory`` sont patchés (voir ``_ThreadLocalEngineRegistry``)
    pour que cet appel passe par le moteur propre à CE thread, jamais celui
    d'un autre poste simulé en cours d'exécution au même instant."""
    stack = build_service_registry(settings, license_public_key_bytes=TEST_LICENSE_PUBLIC_KEY_BYTES)
    username = f"loadtest_post_{index}"
    with db_session_module.session_scope(settings) as setup_session:
        role = setup_session.query(Role).filter_by(nom="Administrateur").one()
        setup_session.add(
            User(
                username=username, password_hash=hash_password(DEFAULT_TEST_PASSWORD),
                role_id=role.id, roles=[role], actif=True,
            )
        )
    stack.auth.login(username, DEFAULT_TEST_PASSWORD)

    try:
        stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article_id, Decimal("1"), Decimal("100"))])
        report.operations_reussies += 1
    except ConflictError:
        # Chantier A (audit) : numéro de vente généré par
        # ``count_all() + 1`` (voir app/services/sales/sale_service.py) —
        # une collision entre deux postes quasi simultanés est détectée et
        # rejetée proprement (contrainte unique), jamais une corruption de
        # donnée ni un doublon silencieux. Comptée séparément des erreurs
        # inattendues : c'est précisément le risque documenté dans le
        # rapport de ce lot, pas un défaut de ce test.
        report.operations_rejetees_proprement += 1
    except AppError as exc:  # pragma: no cover - diagnostic
        report.erreurs_inattendues.append(f"poste {index} : {exc}")
    except Exception as exc:  # pragma: no cover - diagnostic
        report.erreurs_inattendues.append(f"poste {index} : erreur inattendue ({type(exc).__name__}) : {exc}")


def _run_load_test(settings: Settings, nombre_postes: int, monkeypatch: pytest.MonkeyPatch) -> LoadTestReport:
    """Crée ``nombre_postes`` moteurs indépendants et fait créer une vente à
    chacun, synchronisés pour démarrer au même instant (pire cas de
    concurrence, barrière) — mesure le débit et détecte toute incohérence."""
    # Passe par les services métier (jamais par une construction directe des
    # modèles ORM) pour que l'article créé respecte exactement les mêmes
    # règles qu'une création réelle via l'interface (CMUP, contraintes...).
    setup_username = f"loadtest_setup_{nombre_postes}"
    with db_session_module.session_scope(settings) as setup_session:
        role = setup_session.query(Role).filter_by(nom="Administrateur").one()
        setup_session.add(
            User(
                username=setup_username, password_hash=hash_password(DEFAULT_TEST_PASSWORD),
                role_id=role.id, roles=[role], actif=True,
            )
        )
    setup_stack = build_service_registry(settings, license_public_key_bytes=TEST_LICENSE_PUBLIC_KEY_BYTES)
    setup_stack.auth.login(setup_username, DEFAULT_TEST_PASSWORD)
    category = setup_stack.categories.create_category(f"CAT-LOAD-{nombre_postes}")
    article = setup_stack.articles.create_article(
        f"ART-LOAD-{nombre_postes}", "Article de charge", category.id, "unite",
        Decimal("50"), Decimal("100"), Decimal("50"), stock_initial=Decimal("1000"),
    )
    article_id = article.id

    report = LoadTestReport(nombre_postes=nombre_postes)
    barrier = threading.Barrier(nombre_postes)

    # Chaque thread (= chaque poste simulé) obtient son propre moteur, voir
    # _ThreadLocalEngineRegistry ci-dessus — remplace get_engine/
    # get_session_factory pour la durée de la section parallèle UNIQUEMENT ;
    # restauré (monkeypatch.undo) avant que _assert_no_data_corruption ne
    # relise les données via le moteur habituel, mis en cache par la
    # fixture.
    registry = _ThreadLocalEngineRegistry(settings)
    monkeypatch.setattr(db_session_module, "get_engine", registry.get_engine)
    monkeypatch.setattr(db_session_module, "get_session_factory", registry.get_session_factory)

    def _wrapped(index: int) -> None:
        try:
            barrier.wait(timeout=30)
        except threading.BrokenBarrierError:  # pragma: no cover - diagnostic
            pass
        _run_one_post_creating_a_sale(settings, index, article_id, report)

    threads = [threading.Thread(target=_wrapped, args=(i,)) for i in range(nombre_postes)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    report.duree_secondes = time.monotonic() - start

    monkeypatch.undo()
    registry.dispose_all()

    return report


def _assert_no_data_corruption(settings: Settings, report: LoadTestReport) -> None:
    """Cohérence des données (§ exigé) : le nombre de ventes réellement
    persistées doit correspondre exactement au nombre d'opérations comptées
    « réussies » — jamais plus (doublon silencieux), jamais moins (perte
    silencieuse) — et chaque numéro de vente doit être unique."""
    from app.models.documents import Vente

    with db_session_module.session_scope(settings) as session:
        ventes = session.query(Vente).all()
        numeros = [v.numero for v in ventes]

    assert len(ventes) == report.operations_reussies
    assert len(numeros) == len(set(numeros)), "Numéros de vente en double détectés — corruption de données."


@pytest.mark.parametrize("nombre_postes", [5, 20])
def test_concurrent_sale_creation_across_simulated_posts(
    postgresql_initialized_db: Settings, nombre_postes: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exécuté réellement (voir le rapport de ce lot pour les chiffres
    obtenus) — 5 et 20 postes simulés, limite de ce conteneur partagé.
    30 et 50 postes : code identique ci-dessous (paramétrage), à exécuter
    sur l'infrastructure réelle visée pour une mesure représentative."""
    report = _run_load_test(postgresql_initialized_db, nombre_postes, monkeypatch)

    assert not report.erreurs_inattendues, (
        f"Erreurs inattendues sous charge ({nombre_postes} postes) : {report.erreurs_inattendues}"
    )
    _assert_no_data_corruption(postgresql_initialized_db, report)

    print(
        f"\n[Charge {nombre_postes} postes] "
        f"réussies={report.operations_reussies} "
        f"rejetées_proprement(numéro en double)={report.operations_rejetees_proprement} "
        f"durée={report.duree_secondes:.3f}s "
        f"débit={report.debit_operations_par_seconde:.1f} ops/s"
    )


@pytest.mark.parametrize("nombre_postes", [30, 50])
@pytest.mark.skipif(
    os.environ.get("STOCKMANAGER_RUN_LARGE_LOAD_TEST") != "1",
    reason=(
        "Charge 30/50 postes simulés désactivée par défaut (consommation de "
        "ressources non négligeable dans un conteneur partagé) — "
        "STOCKMANAGER_RUN_LARGE_LOAD_TEST=1 pour l'activer explicitement."
    ),
)
def test_concurrent_sale_creation_across_simulated_posts_large_scale(
    postgresql_initialized_db: Settings, nombre_postes: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Même test que ci-dessus, à une échelle plus proche de la cible
    commerciale (30/50 postes) — désactivé par défaut (voir le skipif) :
    exécuté une fois explicitement pour ce rapport, jamais prétendu
    équivalent à un test sur le matériel/réseau réel du déploiement visé."""
    report = _run_load_test(postgresql_initialized_db, nombre_postes, monkeypatch)

    assert not report.erreurs_inattendues, (
        f"Erreurs inattendues sous charge ({nombre_postes} postes) : {report.erreurs_inattendues}"
    )
    _assert_no_data_corruption(postgresql_initialized_db, report)

    print(
        f"\n[Charge {nombre_postes} postes] "
        f"réussies={report.operations_reussies} "
        f"rejetées_proprement(numéro en double)={report.operations_rejetees_proprement} "
        f"durée={report.duree_secondes:.3f}s "
        f"débit={report.debit_operations_par_seconde:.1f} ops/s"
    )
