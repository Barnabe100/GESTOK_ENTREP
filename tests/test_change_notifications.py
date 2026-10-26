"""Tests de ``app.db.change_notifications`` sous SQLite — n'a jamais aucun
effet (voir la docstring de module : un seul poste existe sous SQLite, le
rafraîchissement sur navigation déjà existant reste suffisant). Équivalent
PostgreSQL (notifications réellement émises/reçues) :
``tests/test_change_notifications_postgresql.py``.
"""
from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.db import change_notifications


def test_register_change_notifications_is_a_noop_under_sqlite(initialized_db: Settings) -> None:
    assert initialized_db.db_backend == "sqlite"
    factory = sessionmaker()

    change_notifications.register_change_notifications(factory, initialized_db)

    assert not event.contains(factory, "after_flush", change_notifications._collect_from_flush)
    assert not event.contains(factory, "do_orm_execute", change_notifications._collect_from_core_dml)
    assert not event.contains(factory, "after_rollback", change_notifications._clear_pending)
