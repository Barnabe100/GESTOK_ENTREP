"""Tests de app.services.backups.recovery — module volontairement sans
dépendance à SQLAlchemy/permissions (voir sa docstring) : ces tests
n'utilisent jamais la fixture ``login_as``/``stack`` de l'application,
uniquement des fichiers et des ``Settings`` construits directement, pour
rester fidèles au scénario visé (base active inexploitable, aucune session
possible)."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.services.backups import backup_engine, recovery


def _make_db(path: Path, *, value: str = "a") -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, valeur TEXT)")
    conn.execute("INSERT INTO demo (valeur) VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test", db_path=tmp_path / "stockmanager.db", log_dir=tmp_path / "logs",
        log_level="INFO", default_currency="XOF",
    )


# -- résolution du dossier de sauvegardes ----------------------------------------


def test_resolve_recovery_destination_falls_back_to_default_when_db_unreadable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    # Base active absente/illisible : session_scope échoue forcément à lire
    # la configuration — le repli doit rester silencieux, jamais lever.
    destination = recovery.resolve_recovery_destination(settings)

    assert destination == settings.data_dir / "backups"


# -- listage des sauvegardes de sécurité -----------------------------------------


def test_list_recoverable_backups_empty_for_missing_directory(tmp_path: Path) -> None:
    assert recovery.list_recoverable_backups(tmp_path / "does_not_exist") == []


def test_list_recoverable_backups_reports_validity(initialized_db: Settings, tmp_path: Path) -> None:
    destination = tmp_path / "backups"
    good = backup_engine.create_backup_file(
        initialized_db.db_path, destination, prefix=backup_engine.PRERESTORE_PREFIX
    )

    corrupted = destination / "stockmanager_prerestore_20260101_000000.db"
    corrupted.write_bytes(b"pas une base sqlite valide")

    results = recovery.list_recoverable_backups(destination)

    by_path = {r.path: r for r in results}
    assert by_path[good].valid is True
    assert by_path[corrupted].valid is False
    assert by_path[corrupted].errors


def test_list_recoverable_backups_never_includes_regular_backups(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_db(source)
    destination = tmp_path / "backups"
    backup_engine.create_backup_file(source, destination)  # préfixe normal, pas prerestore

    assert recovery.list_recoverable_backups(destination) == []


# -- restauration de secours ------------------------------------------------------


def test_restore_from_recovery_moves_aside_existing_database_and_restores_content(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _make_db(source, value="sauvegarde de securite")
    destination = tmp_path / "backups"
    security_backup = backup_engine.create_backup_file(source, destination, prefix=backup_engine.PRERESTORE_PREFIX)

    db_path = tmp_path / "stockmanager.db"
    _make_db(db_path, value="base cassee")  # simule la base active (ici juste différente, pas réellement corrompue)

    result = recovery.restore_from_recovery(security_backup, db_path)

    assert result.success is True
    assert result.moved_aside_path is not None
    assert result.moved_aside_path.exists()
    assert ".corrompue-" in result.moved_aside_path.name

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT valeur FROM demo").fetchall()
    conn.close()
    assert rows == [("sauvegarde de securite",)]

    conn = sqlite3.connect(str(result.moved_aside_path))
    rows = conn.execute("SELECT valeur FROM demo").fetchall()
    conn.close()
    assert rows == [("base cassee",)]  # l'ancienne base est bien préservée, pas perdue


def test_restore_from_recovery_works_when_no_database_exists_yet(tmp_path: Path) -> None:
    """Scénario d'un poste neuf : aucun fichier stockmanager.db n'existe
    encore (pas de base à mettre de côté)."""
    source = tmp_path / "source.db"
    _make_db(source)
    destination = tmp_path / "backups"
    security_backup = backup_engine.create_backup_file(source, destination, prefix=backup_engine.PRERESTORE_PREFIX)

    db_path = tmp_path / "stockmanager.db"
    assert not db_path.exists()

    result = recovery.restore_from_recovery(security_backup, db_path)

    assert result.success is True
    assert result.moved_aside_path is None
    assert db_path.exists()


def test_restore_from_recovery_rejects_postgresql_dump_files(tmp_path: Path) -> None:
    db_path = tmp_path / "stockmanager.db"
    _make_db(db_path)
    fake_dump = tmp_path / "stockmanager_prerestore_pg_20260101_020000.dump"
    fake_dump.write_bytes(b"contenu pg_dump factice")

    result = recovery.restore_from_recovery(fake_dump, db_path)

    assert result.success is False
    assert "PostgreSQL" in result.message
    # La base active n'a pas été touchée.
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT valeur FROM demo").fetchall()
    conn.close()
    assert rows == [("a",)]


def test_restore_from_recovery_failure_keeps_moved_aside_database_and_mentions_it(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.db"
    _make_db(source)
    destination = tmp_path / "backups"
    security_backup = backup_engine.create_backup_file(source, destination, prefix=backup_engine.PRERESTORE_PREFIX)

    db_path = tmp_path / "stockmanager.db"
    _make_db(db_path, value="base cassee")

    monkeypatch.setattr(
        "app.services.backups.backup_engine.restore_database_from_backup",
        lambda *a, **k: (_ for _ in ()).throw(OSError("panne simulée")),
    )

    result = recovery.restore_from_recovery(security_backup, db_path)

    assert result.success is False
    assert result.moved_aside_path is not None
    assert result.moved_aside_path.exists()
    # db_path lui-même n'a jamais été touché (garantie de restore_database_from_backup,
    # §3.2) : la copie de prudence est redondante ici, mais la base active
    # reste intacte et exploitable malgré l'échec.
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT valeur FROM demo").fetchall()
    conn.close()
    assert rows == [("base cassee",)]
