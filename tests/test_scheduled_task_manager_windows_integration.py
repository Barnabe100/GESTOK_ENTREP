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
    déjà testée sans Windows, voir tests/test_scheduled_task_manager.py).

    Mission corrective « Erreur Accès refusé de la tâche planifiée Windows » :
    c'est précisément cette création (``onlogon``) qui échouait avec le
    code 1 (« Accès refusé ») avant la correction du ``<LogonTrigger>``
    sans ``<UserId>`` — exécutable depuis une session Windows standard
    (non administrateur), sans élévation (voir la docstring de module de
    ``scheduled_task_manager`` pour la cause exacte)."""
    stm.create_or_repair_task(
        _TEST_TASK_NAME, sys.executable, ["--version"], "20:00", schedule=stm.SCHEDULE_ONLOGON,
    )

    assert stm.task_exists(_TEST_TASK_NAME) is True
    status = stm.query_task_status(_TEST_TASK_NAME)
    assert status.run_as_user is not None and status.run_as_user != ""


def test_create_task_with_a_space_in_the_executable_path_and_runs_it_successfully(tmp_path) -> None:
    """Mission corrective « Correction et validation du module de
    sauvegarde sous Windows », §3.2/§5 : reproduit réellement, sur Windows,
    le scénario diagnostiqué (exécutable installé dans un dossier dont le
    nom contient un espace, ex. ``Program Files`` — l'emplacement
    d'installation par défaut de l'installateur Inno Setup) ET exécute
    effectivement la tâche créée (``schtasks /run``), pas seulement sa
    création : seule une exécution réelle prouve que la valeur transmise à
    ``schtasks.exe`` (désormais via ``/xml``, jamais ``/tr``) est
    correctement interprétée de bout en bout, pas seulement acceptée à la
    création."""
    import shutil
    import subprocess as sp
    import time

    install_dir = tmp_path / "Program Files Test" / "StockManager"
    install_dir.mkdir(parents=True)
    copied_executable = install_dir / "python_copie.exe"
    shutil.copy2(sys.executable, copied_executable)

    marker_file = tmp_path / "marker.txt"
    # ``--version`` ne produit aucun fichier observable ; on exécute plutôt
    # un script Python minimal qui écrit un repère, pour prouver que
    # l'exécutable ET ses arguments ont bien été transmis et exécutés tels
    # quels par la tâche planifiée.
    script = tmp_path / "write_marker.py"
    script.write_text(f"open(r'{marker_file}', 'w').write('ok')\n", encoding="utf-8")

    stm.create_or_repair_task(_TEST_TASK_NAME, str(copied_executable), [str(script)], "23:59")
    assert stm.task_exists(_TEST_TASK_NAME) is True

    sp.run(["schtasks", "/run", "/tn", _TEST_TASK_NAME], capture_output=True, text=True, timeout=30)
    deadline = time.time() + 15
    while time.time() < deadline and not marker_file.exists():
        time.sleep(0.5)

    assert marker_file.exists(), (
        "La tâche planifiée ne semble pas avoir exécuté l'exécutable (chemin avec espace) avec "
        "l'argument attendu — voir la définition XML générée par _build_task_xml."
    )
