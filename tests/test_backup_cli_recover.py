"""Vérifie la sous-commande ``recover`` de app/backup_cli.py (mission
corrective, §3.3). Jamais d'appel à ``main()``/``_run_scheduled_backup()``
sans sous-commande ici (celui-ci appelle ``setup_logging``, voir
tests/test_backup_cli.py et sa docstring) — seule ``_run_recover``, qui n'y
touche jamais, est exercée directement."""
import sqlite3

import pytest

from app.backup_cli import main
from app.config.settings import Settings
from app.services.backups import backup_engine


def _make_prerestore_backup(settings: Settings, destination) -> None:
    backup_engine.create_backup_file(settings.db_path, destination, prefix=backup_engine.PRERESTORE_PREFIX)


def test_recover_list_reports_no_backups_when_none_exist(initialized_db: Settings, capsys) -> None:
    exit_code = main(["recover", "--list"])

    assert exit_code == 0
    assert "Aucune sauvegarde de sécurité" in capsys.readouterr().out


def test_recover_list_shows_existing_security_backup(initialized_db: Settings, tmp_path, capsys) -> None:
    destination = tmp_path / "backups"
    _make_prerestore_backup(initialized_db, destination)

    exit_code = main(["recover", "--list"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "stockmanager_prerestore_" in output
    assert "valide" in output


def test_recover_restore_succeeds_and_replaces_active_database(
    initialized_db: Settings, tmp_path, capsys
) -> None:
    conn = sqlite3.connect(str(initialized_db.db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS marqueur_test (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    destination = tmp_path / "backups"
    _make_prerestore_backup(initialized_db, destination)
    backup_path = next(destination.glob("stockmanager_prerestore_*.db"))

    exit_code = main(["recover", "--restore", str(backup_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Restauration réussie" in output
    assert initialized_db.db_path.exists()


def test_recover_restore_reports_error_for_missing_file(initialized_db: Settings, tmp_path, capsys) -> None:
    exit_code = main(["recover", "--restore", str(tmp_path / "absent.db")])

    assert exit_code == 1
    assert "n'est pas un fichier accessible" in capsys.readouterr().err


def test_recover_restore_reports_failure_for_invalid_backup(initialized_db: Settings, tmp_path, capsys) -> None:
    fake = tmp_path / "stockmanager_prerestore_20260101_000000.db"
    fake.write_bytes(b"pas une base sqlite valide")

    exit_code = main(["recover", "--restore", str(fake)])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Échec" in output


def test_recover_restore_rejects_postgresql_dump(initialized_db: Settings, tmp_path, capsys) -> None:
    fake_dump = tmp_path / "stockmanager_prerestore_pg_20260101_000000.dump"
    fake_dump.write_bytes(b"contenu factice")

    exit_code = main(["recover", "--restore", str(fake_dump)])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "PostgreSQL" in output


def test_main_without_subcommand_still_dispatches_to_scheduled_backup(monkeypatch) -> None:
    """Comportement par défaut (sauvegarde planifiée) inchangé — toute
    installation existante ayant déjà enregistré cette commande auprès du
    Planificateur de tâches Windows continue de fonctionner à l'identique.
    N'appelle jamais la vraie fonction (``setup_logging``, voir la
    docstring de module) : vérifie seulement qu'elle est bien appelée."""
    calls = []
    monkeypatch.setattr("app.backup_cli._run_scheduled_backup", lambda: calls.append(True) or 0)

    exit_code = main([])

    assert calls == [True]
    assert exit_code == 0
