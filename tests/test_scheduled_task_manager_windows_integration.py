"""Tests d'intégration RÉELS de app.services.backups.scheduled_task_manager
— invoquent véritablement ``schtasks.exe`` et créent/suppriment une tâche
planifiée Windows réelle. Jamais exécutés automatiquement hors Windows
(``skipif`` ci-dessous) : un succès de la suite sous Linux ne doit jamais
être présenté comme une validation du comportement Windows réel (§8 du
mandat de cette mission — voir aussi le rapport de livraison, section
« limites et tests non exécutables »).

Pour exécuter réellement ces tests (sur un poste Windows, hors session
Administrateur — la création d'une tâche pour l'utilisateur courant ne
nécessite aucune élévation) :

    python -m pytest tests/test_scheduled_task_manager_windows_integration.py -v
"""
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Nécessite réellement Windows (schtasks.exe).")

if sys.platform == "win32":
    from app.services.backups import scheduled_task_manager as stm

_TEST_TASK_NAME = "StockManager - Test automatise (a supprimer si visible)"


@pytest.fixture(autouse=True)
def _cleanup_test_task():
    yield
    try:
        stm.delete_task(_TEST_TASK_NAME)
    except Exception:
        pass


def test_task_exists_false_for_unknown_task() -> None:
    assert stm.task_exists(_TEST_TASK_NAME) is False


def test_create_then_task_exists_true() -> None:
    stm.create_or_repair_task(_TEST_TASK_NAME, sys.executable, ["--version"], "23:59")

    assert stm.task_exists(_TEST_TASK_NAME) is True


def test_create_is_idempotent_and_repairs() -> None:
    stm.create_or_repair_task(_TEST_TASK_NAME, sys.executable, ["--version"], "23:59")
    stm.create_or_repair_task(_TEST_TASK_NAME, sys.executable, ["--version"], "22:30")

    status = stm.query_task_status(_TEST_TASK_NAME)
    assert status.exists is True


def test_query_task_status_reports_ready_state() -> None:
    stm.create_or_repair_task(_TEST_TASK_NAME, sys.executable, ["--version"], "23:59")

    status = stm.query_task_status(_TEST_TASK_NAME)

    assert status.exists is True
    assert status.status is not None


def test_delete_removes_task() -> None:
    stm.create_or_repair_task(_TEST_TASK_NAME, sys.executable, ["--version"], "23:59")

    stm.delete_task(_TEST_TASK_NAME)

    assert stm.task_exists(_TEST_TASK_NAME) is False


def test_delete_is_idempotent_when_already_absent() -> None:
    stm.delete_task(_TEST_TASK_NAME)  # ne doit jamais lever, même si absente


def test_create_onlogon_task_is_accepted_by_real_schtasks() -> None:
    """Mission corrective, §3.5 : vérifie réellement que ``schtasks.exe``
    accepte ``/sc onlogon`` sans ``/st`` — jamais vérifié ailleurs que sur
    Windows réel (la construction de la ligne de commande elle-même est
    déjà testée sans Windows, voir tests/test_scheduled_task_manager.py)."""
    stm.create_or_repair_task(
        _TEST_TASK_NAME, sys.executable, ["--version"], "20:00", schedule=stm.SCHEDULE_ONLOGON,
    )

    assert stm.task_exists(_TEST_TASK_NAME) is True
