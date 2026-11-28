"""Vérifie app.backup_external_agent_cli.

``run_cycle`` (logique pure du cycle sauvegarde locale -> copie externe) et
``run_agent_locked`` (verrou anti-concurrence + délégation à ``run_cycle``)
sont testées directement avec des services déjà construits par
``login_as``, jamais via ``run_agent()`` complet : ``run_agent()`` appelle
``setup_logging()``, qui reconfigure le logger racine de façon persistante
pour tout le processus pytest (effet de bord global documenté dans
``app/utils/logging_config.py``) — l'appeler dans la suite de tests
casserait ``caplog`` pour tous les tests suivants de la même exécution,
exactement la raison pour laquelle tests/test_backup_cli.py (sauvegarde
locale seule, V1) n'appelle jamais ``app.backup_cli.main()`` non plus et
teste directement ``BackupService.run_scheduled_backup_if_due``. Le verrou
lui-même (acquisition/relâchement/récupération d'un verrou périmé) est déjà
testé indépendamment dans tests/test_process_lock.py ; les tests ci-dessous
ne vérifient que son intégration (exécution simultanée empêchée, verrou
toujours relâché) via ``run_agent_locked``, jamais ``setup_logging``."""
import logging
import subprocess
import sys
import time

from app.backup_external_agent_cli import (
    AGENT_FLAG,
    resolve_agent_invocation,
    run_agent_locked,
    run_cycle,
)
from app.utils.process_lock import ProcessLock


def _logger() -> logging.Logger:
    return logging.getLogger("test.backup_external_agent")


def test_resolve_agent_invocation_uses_python_module_in_development() -> None:
    executable, arguments = resolve_agent_invocation()

    assert executable == sys.executable
    assert arguments == ["-m", "app.backup_external_agent_cli"]


def test_resolve_agent_invocation_uses_agent_flag_when_frozen(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/StockManager/StockManager.exe", raising=False)

    executable, arguments = resolve_agent_invocation()

    assert executable == "C:/StockManager/StockManager.exe"
    assert arguments == [AGENT_FLAG]


def test_run_cycle_performs_local_backup_when_due(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )

    exit_code = run_cycle(stack.backups, stack.external_backups, _logger())

    assert exit_code == 0
    assert list((tmp_path / "local_backups").glob("stockmanager_backup_*.db")) != []


def test_run_cycle_does_nothing_when_auto_backup_disabled(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )

    exit_code = run_cycle(stack.backups, stack.external_backups, _logger())

    assert exit_code == 0
    # Le dossier lui-même est créé par update_config (toujours tenté
    # immédiatement) — seule l'absence de fichier prouve qu'aucune
    # sauvegarde n'a eu lieu.
    assert list((tmp_path / "local_backups").glob("stockmanager_backup_*.db")) == []


def test_run_cycle_also_copies_externally_when_configured(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )
    stack.external_backups.configure_media(drive, "Support de test")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]

    exit_code = run_cycle(stack.backups, stack.external_backups, _logger())

    assert exit_code == 0
    external_backups = list((drive / "StockManager_Sauvegardes").glob("stockmanager_backup_*.db"))
    assert len(external_backups) == 1


def test_run_cycle_reports_failure_exit_code_when_external_copy_fails(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )
    stack.external_backups.configure_media(drive, "Support de test")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: []  # support débranché -> copie refusée

    exit_code = run_cycle(stack.backups, stack.external_backups, _logger())

    assert exit_code == 1  # sauvegarde locale réussie, mais copie externe échouée


def test_run_cycle_is_idempotent_within_the_same_day(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )

    first = run_cycle(stack.backups, stack.external_backups, _logger())
    second = run_cycle(stack.backups, stack.external_backups, _logger())

    assert first == 0
    assert second == 0
    assert len(list((tmp_path / "local_backups").glob("stockmanager_backup_*.db"))) == 1


def test_run_agent_locked_runs_cycle_when_lock_free(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )
    lock = ProcessLock(tmp_path / "backup_agent.lock")

    exit_code = run_agent_locked(lock, stack.backups, stack.external_backups, _logger())

    assert exit_code == 0
    assert list((tmp_path / "local_backups").glob("stockmanager_backup_*.db")) != []


def test_run_agent_locked_skips_cleanly_when_already_held(login_as, tmp_path) -> None:
    """Le verrou étant désormais réentrant au sein d'un même processus
    (mission corrective, §3.7 — voir ``app.utils.process_lock``), seul un
    AUTRE processus réellement actif détenant le verrou doit faire
    abandonner proprement l'agent — jamais une seconde instance
    ``ProcessLock`` du même processus, qui réussirait désormais à
    l'acquérir (voir ``tests/test_process_lock.py`` pour la distinction)."""
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )
    lock_path = tmp_path / "backup_agent.lock"
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    time.sleep(0.2)
    try:
        lock_path.write_text(str(other.pid), encoding="utf-8")
        contender = ProcessLock(lock_path)

        exit_code = run_agent_locked(contender, stack.backups, stack.external_backups, _logger())

        assert exit_code == 0
        # Jamais exécuté : la sauvegarde locale, pourtant due, n'a pas eu lieu.
        assert list((tmp_path / "local_backups").glob("stockmanager_backup_*.db")) == []
    finally:
        other.terminate()
        other.wait(timeout=5)


def test_run_agent_locked_releases_lock_after_success(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )
    lock_path = tmp_path / "backup_agent.lock"

    run_agent_locked(ProcessLock(lock_path), stack.backups, stack.external_backups, _logger())

    # Le verrou a bien été relâché : une seconde exécution peut l'acquérir.
    second_lock = ProcessLock(lock_path)
    assert second_lock.acquire() is True
    second_lock.release()


def test_run_agent_locked_releases_lock_even_when_cycle_fails(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support de test")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: []  # support débranché -> copie refusée
    lock_path = tmp_path / "backup_agent.lock"

    exit_code = run_agent_locked(ProcessLock(lock_path), stack.backups, stack.external_backups, _logger())

    assert exit_code == 1
    second_lock = ProcessLock(lock_path)
    assert second_lock.acquire() is True
    second_lock.release()


# -- mission « Fiabilisation des sauvegardes automatiques », §3 : instrumentation --


def test_run_agent_locked_logs_lock_acquisition_steps(login_as, tmp_path, caplog) -> None:
    """Chaque étape nommée par le mandat (tentative d'acquisition, verrou
    acquis) doit apparaître dans le journal, succès compris — jusqu'ici
    seul l'échec d'acquisition était journalisé."""
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )
    lock = ProcessLock(tmp_path / "backup_agent.lock")

    with caplog.at_level(logging.INFO, logger="test.backup_external_agent"):
        run_agent_locked(lock, stack.backups, stack.external_backups, _logger())

    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "tentative d'acquisition du verrou" in logged_text
    assert "verrou acquis" in logged_text


def test_run_agent_locked_logs_and_reports_an_unexpected_exception_during_the_cycle(
    login_as, tmp_path, caplog, monkeypatch
) -> None:
    """§3/§4 du mandat : une exception non prévue pendant le cycle ne doit
    jamais être perdue (un exécutable sans console, voir
    ``stockmanager.spec``, n'a aucune sortie d'erreur visible) ni
    confondue avec un cycle qui n'avait légitimement rien à faire — code
    de sortie non nul, trace complète journalisée, verrou tout de même
    relâché."""
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )
    monkeypatch.setattr(
        stack.backups, "run_scheduled_backup_if_due",
        lambda: (_ for _ in ()).throw(RuntimeError("échec simulé, jamais réel")),
    )
    lock_path = tmp_path / "backup_agent.lock"

    with caplog.at_level(logging.ERROR, logger="test.backup_external_agent"):
        exit_code = run_agent_locked(ProcessLock(lock_path), stack.backups, stack.external_backups, _logger())

    assert exit_code == 1
    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "exception non interceptée" in logged_text
    assert any(
        "RuntimeError" in (record.exc_text or "") or "RuntimeError" in logged_text
        for record in caplog.records
    )
    # Le verrou reste relâché malgré l'exception — même garantie que pour
    # un échec « ordinaire » (voir test_run_agent_locked_releases_lock_even_when_cycle_fails).
    second_lock = ProcessLock(lock_path)
    assert second_lock.acquire() is True
    second_lock.release()
