"""Tests de :class:`app.repositories.counter_repository.CounterRepository`
(audit multi-poste, numérotation atomique) — voir
``app/models/counters.py`` pour le contexte complet.

Équivalent PostgreSQL (accès concurrent réel entre connexions) :
``tests/test_counter_repository_postgresql.py``.
"""
from __future__ import annotations

import threading

import pytest

from app.config.settings import Settings
from app.db.session import session_scope
from app.repositories.counter_repository import CounterRepository


def test_next_value_increments_from_zero(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        assert CounterRepository(session).next_value("VNT") == 1
    with session_scope(initialized_db) as session:
        assert CounterRepository(session).next_value("VNT") == 2


def test_next_value_is_independent_per_type_document(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        repo = CounterRepository(session)
        assert repo.next_value("VNT") == 1
        assert repo.next_value("ENT") == 1
        assert repo.next_value("VNT") == 2


def test_next_value_raises_lookup_error_for_unknown_type(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        with pytest.raises(LookupError):
            CounterRepository(session).next_value("INCONNU")


def test_next_value_rolled_back_transaction_does_not_burn_the_number(initialized_db: Settings) -> None:
    """Exigence « vérifie le comportement en cas de rollback » : la
    numérotation est incrémentée dans la MÊME transaction que la création
    du document (voir les 5 services appelants) — si cette transaction
    échoue et annule tout (rollback), le compteur doit revenir à sa valeur
    d'avant la tentative, jamais rester bloqué sur un numéro jamais
    réellement attribué à aucun document."""
    try:
        with session_scope(initialized_db) as session:
            assert CounterRepository(session).next_value("VNT") == 1
            raise RuntimeError("échec simulé après incrémentation, avant la fin de la transaction")
    except RuntimeError:
        pass

    with session_scope(initialized_db) as session:
        # Le rollback précédent n'a jamais été validé : le prochain appel
        # réussi doit obtenir 1, jamais 2 (aucun numéro n'a été « brûlé »).
        assert CounterRepository(session).next_value("VNT") == 1


def test_next_value_concurrent_calls_never_collide_and_cover_every_value(initialized_db: Settings) -> None:
    """Scénario central de l'audit multi-poste : plusieurs postes créent un
    document du même type au même instant. Avec l'ancien mécanisme
    (``COUNT(*)+1``), plusieurs threads auraient pu lire la même valeur
    avant qu'aucun n'écrive — ici, chaque appel doit obtenir une valeur
    strictement différente, et l'ensemble des valeurs obtenues doit
    couvrir exactement ``{1, ..., N}`` sans trou ni doublon (SQLite
    sérialise les écritures concurrentes via son verrou base de données,
    avec le délai d'attente par défaut de 5 s du module ``sqlite3`` — voir
    ``app/services/stock/stock_service.py`` pour ce principe déjà établi)."""
    n = 10
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def _call(index: int) -> None:
        try:
            barrier.wait(timeout=10)
        except threading.BrokenBarrierError:  # pragma: no cover - diagnostic
            pass
        with session_scope(initialized_db) as session:
            results[index] = CounterRepository(session).next_value("VNT")

    threads = [threading.Thread(target=_call, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert None not in results, f"un appel n'a pas terminé : {results}"
    assert sorted(results) == list(range(1, n + 1))
