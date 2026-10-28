"""Tests de ``app.views.background_task.BackgroundTask`` (phase amélioration
UX, points 3 et 4 — correctif suite à la revue finale : l'exécution dans un
vrai ``QThread`` est précisément ce qui permet à la boucle d'évènements Qt
du thread appelant de continuer à tourner — et donc à un spinner animé par
``QTimer`` de réellement s'animer — pendant l'opération, contrairement à un
simple ``QApplication.processEvents()`` appelé une fois avant un appel
bloquant."""
from __future__ import annotations

import gc
import threading

import pytest

from app.views.background_task import _ACTIVE_TASKS, BackgroundTask


def test_successful_function_result_is_delivered_on_success_callback(qtbot) -> None:
    received = {}

    task = BackgroundTask(lambda: 42)
    task.start(on_success=lambda result: received.update(value=result), on_failure=lambda exc: pytest.fail(str(exc)))

    qtbot.waitUntil(lambda: "value" in received, timeout=2000)
    assert received["value"] == 42


def test_exception_raised_in_the_function_is_delivered_on_failure_callback(qtbot) -> None:
    received = {}

    def _boom() -> None:
        raise RuntimeError("échec simulé")

    task = BackgroundTask(_boom)
    task.start(
        on_success=lambda result: pytest.fail("ne doit pas être appelé en cas d'échec"),
        on_failure=lambda exc: received.update(error=exc),
    )

    qtbot.waitUntil(lambda: "error" in received, timeout=2000)
    assert isinstance(received["error"], RuntimeError)
    assert str(received["error"]) == "échec simulé"


def test_success_callback_is_never_called_together_with_failure_callback(qtbot) -> None:
    calls = []

    task = BackgroundTask(lambda: "ok")
    task.start(on_success=lambda result: calls.append(("success", result)), on_failure=lambda exc: calls.append(("failure", exc)))

    qtbot.waitUntil(lambda: len(calls) == 1, timeout=2000)
    assert calls == [("success", "ok")]


def test_main_thread_event_loop_keeps_running_during_the_background_call(qtbot) -> None:
    """Preuve concrète de la raison d'être de cette classe (voir la
    docstring de module) : tant que ``func`` s'exécute dans le thread
    d'arrière-plan, un ``QTimer`` du thread appelant continue de se
    déclencher — ce qui ne serait jamais le cas pendant un appel bloquant
    classique (``QApplication.processEvents()`` appelé une seule fois
    avant l'appel, comme avant ce correctif)."""
    from PySide6.QtCore import QTimer

    release = threading.Event()
    tick_count = {"n": 0}

    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: tick_count.update(n=tick_count["n"] + 1))
    timer.start()

    def _blocking_work():
        release.wait(timeout=5)
        return "done"

    received = {}
    task = BackgroundTask(_blocking_work)
    task.start(on_success=lambda result: received.update(value=result), on_failure=lambda exc: pytest.fail(str(exc)))

    # Attend que le minuteur du thread appelant ait eu l'occasion de
    # déclencher plusieurs fois PENDANT que le thread d'arrière-plan est
    # encore bloqué sur ``release.wait`` — la preuve que la boucle
    # d'évènements de ce thread n'est jamais interrompue par l'appel.
    qtbot.waitUntil(lambda: tick_count["n"] >= 3, timeout=2000)
    assert "value" not in received, "le travail d'arrière-plan ne devrait pas déjà être terminé."

    release.set()
    qtbot.waitUntil(lambda: "value" in received, timeout=2000)
    timer.stop()

    assert received["value"] == "done"


# -- correctif revue finale — défaut critique de cycle de vie ----------------
#
# Protection de second niveau, indépendante de la discipline de l'appelant
# (la protection principale est dans MainWindow/BackupsPage, voir
# tests/test_main_window.py) : une tâche démarrée reste référencée par le
# registre du module tant qu'elle n'a pas réellement terminé, même si
# l'objet qui l'a créée disparaissait entre-temps.


def test_running_task_is_kept_alive_by_the_module_registry_even_without_a_caller_reference(qtbot) -> None:
    release = threading.Event()
    received = {}

    task = BackgroundTask(lambda: (release.wait(timeout=5), "done")[1])
    task.start(on_success=lambda result: received.update(value=result), on_failure=lambda exc: pytest.fail(str(exc)))

    assert task in _ACTIVE_TASKS

    # L'appelant abandonne sa seule référence Python à la tâche — sans le
    # registre du module, rien d'autre ne la maintiendrait en vie.
    del task
    gc.collect()

    assert len(_ACTIVE_TASKS) == 1, "la tâche encore active a disparu du registre alors qu'elle tourne toujours."
    surviving_task = next(iter(_ACTIVE_TASKS))
    assert surviving_task.is_running() is True

    release.set()
    qtbot.waitUntil(lambda: "value" in received, timeout=2000)
    assert received["value"] == "done"
    assert len(_ACTIVE_TASKS) == 0, "la tâche terminée aurait dû être retirée du registre."


def test_invoking_a_callback_whose_target_is_already_destroyed_never_raises(qtbot) -> None:
    """Filet de sécurité de :meth:`BackgroundTask._invoke` : si le rappel
    fourni lève ``RuntimeError`` (ex. widget Qt déjà détruit), l'exception
    est absorbée et journalisée, jamais laissée se propager."""

    class _DeadTarget:
        def __call__(self, _value) -> None:
            raise RuntimeError("Internal C++ object already deleted.")

    task = BackgroundTask(lambda: "ok")
    task.start(on_success=_DeadTarget(), on_failure=lambda exc: pytest.fail(str(exc)))

    # Ne doit jamais lever, même si le callback échoue en interne.
    qtbot.waitUntil(lambda: task not in _ACTIVE_TASKS, timeout=2000)
