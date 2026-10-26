"""Connexion base de données, moteur SQLAlchemy et gestion transactionnelle.

Point d'entrée unique pour obtenir une session : ``session_scope()``. Les
services métier s'appuient dessus pour garantir que toute opération de stock
est atomique (commit intégral ou rollback complet) — ceci est strictement
indépendant du moteur de base de données actif (voir Lot A, ci-dessous) :
aucun service métier n'a besoin de savoir si la session qu'il manipule est
adossée à SQLite ou à PostgreSQL.

Lot A (socle multi-moteur) : ``create_db_engine`` construit le moteur en
fonction de ``Settings.db_backend`` — les options propres à SQLite
(``check_same_thread``, l'écouteur ``PRAGMA foreign_keys=ON``) ne sont
appliquées que pour ce moteur ; PostgreSQL reçoit à la place un délai de
connexion explicite, sans qu'aucune option SQLite ne lui soit jamais
transmise. L'intégrité référentielle est de toute façon garantie nativement
par PostgreSQL (contrainte FK toujours active), sans configuration
supplémentaire de notre part.
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

    if settings.db_backend == "postgresql":
        if settings.postgresql is None:
            raise ValueError(
                "db_backend='postgresql' mais aucune configuration de connexion "
                "(Settings.postgresql) n'a été fournie."
            )
        # Jamais d'option SQLite ici (ni check_same_thread, ni l'écouteur
        # PRAGMA foreign_keys=ON ci-dessous, réservé à la branche SQLite) —
        # seul un délai de connexion explicite est transmis au pilote
        # psycopg3, pour échouer proprement plutôt que d'attendre
        # indéfiniment un serveur réseau inaccessible (§3.B du mandat).
        #
        # Chantier A (audit multi-postes) : ``pool_pre_ping`` et
        # ``pool_recycle`` ajoutés — StockManager Desktop est une application
        # longue durée connectée à un serveur distant par le réseau local
        # (voir docs/postgresql-reseau-multipostes.md) : une connexion du
        # pool restée inactive peut être fermée silencieusement par un
        # pare-feu/routeur intermédiaire, ou par le serveur lui-même, sans
        # qu'aucune requête n'en informe l'application avant d'essayer de la
        # réutiliser. Sans ``pool_pre_ping``, la prochaine opération sur
        # cette connexion échouerait alors avec une erreur technique brute
        # (``OperationalError``/connexion réinitialisée) au lieu d'une
        # reconnexion transparente — ``pool_pre_ping`` exécute un test de
        # validité léger avant de réutiliser une connexion du pool et la
        # remplace silencieusement si elle est morte (coût : un aller-retour
        # réseau supplémentaire, négligeable face à la fiabilité gagnée).
        # ``pool_recycle`` (30 minutes) referme proactivement toute connexion
        # plus ancienne, avant qu'un intermédiaire réseau n'ait l'occasion de
        # le faire à sa place — n'a jamais modifié le comportement applicatif
        # observable, uniquement la résilience réseau. Taille du pool
        # (``pool_size``/``max_overflow``) volontairement laissée aux valeurs
        # par défaut de SQLAlchemy ici : leur dimensionnement définitif pour
        # un déploiement à grande échelle (nombreux postes) doit s'appuyer
        # sur les tests de charge progressifs (voir le rapport de ce lot),
        # pas sur une estimation arbitraire.
        engine = create_engine(
            settings.sqlalchemy_database_uri,
            connect_args={"connect_timeout": settings.postgresql.connect_timeout_seconds},
            pool_pre_ping=True,
            pool_recycle=1800,
            future=True,
        )
        # Jamais l'URL/le mot de passe dans ce message : seuls les éléments
        # non sensibles de la configuration (voir PostgreSQLConnectionConfig,
        # qui ne porte jamais le mot de passe lui-même).
        logger.info(
            "Moteur SQLAlchemy créé pour PostgreSQL (%s:%s/%s)",
            settings.postgresql.host, settings.postgresql.port, settings.postgresql.database,
        )
        return engine

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
        # Chantier D (synchronisation automatique) : n'a aucun effet sous
        # SQLite (un seul poste) — voir app/db/change_notifications.py.
        from app.db.change_notifications import register_change_notifications

        register_change_notifications(_session_factory, settings or get_settings())
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
