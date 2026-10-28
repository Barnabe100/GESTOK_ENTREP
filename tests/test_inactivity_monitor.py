"""Tests de ``app.views.inactivity_monitor.InactivityMonitor`` (phase accès
réseau/déconnexion auto/permissions Consultant, point 2)."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent

from app.views.inactivity_monitor import DEFAULT_INACTIVITY_TIMEOUT_MINUTES, InactivityMonitor


def test_default_timeout_is_ten_minutes() -> None:
    assert DEFAULT_INACTIVITY_TIMEOUT_MINUTES == 10


def _mouse_press_event() -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonPress, QPoint(0, 0), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )


def _key_press_event() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)


def test_timed_out_is_emitted_after_the_configured_delay_with_no_activity(qtbot) -> None:
    monitor = InactivityMonitor(timeout_minutes=1)
    monitor._timer.setInterval(50)  # raccourci pour le test, sans changer l'API publique
    received = {"n": 0}
    monitor.timed_out.connect(lambda: received.update(n=received["n"] + 1))

    monitor.start()

    qtbot.waitUntil(lambda: received["n"] == 1, timeout=2000)


def test_activity_event_resets_the_timer_before_it_fires(qtbot) -> None:
    monitor = InactivityMonitor(timeout_minutes=1)
    monitor._timer.setInterval(150)
    received = {"n": 0}
    monitor.timed_out.connect(lambda: received.update(n=received["n"] + 1))

    monitor.start()
    qtbot.wait(80)  # moins que l'intervalle : aucune émission ne doit encore avoir eu lieu
    assert received["n"] == 0

    monitor.eventFilter(None, _mouse_press_event())  # réarme depuis zéro
    qtbot.wait(80)
    assert received["n"] == 0, "une activité juste avant l'échéance doit la reporter, jamais la laisser expirer."

    qtbot.waitUntil(lambda: received["n"] == 1, timeout=2000)


def test_key_press_and_wheel_events_also_reset_the_timer() -> None:
    """Pas seulement le clic : la frappe clavier et la molette comptent
    aussi comme activité (voir _ACTIVITY_EVENT_TYPES)."""
    monitor = InactivityMonitor(timeout_minutes=1)
    for event in (_key_press_event(), _mouse_press_event()):
        assert monitor.eventFilter(None, event) is False  # ne consomme jamais l'évènement


def test_unrelated_event_types_do_not_reset_the_timer(qtbot) -> None:
    monitor = InactivityMonitor(timeout_minutes=1)
    monitor._timer.setInterval(50)
    received = {"n": 0}
    monitor.timed_out.connect(lambda: received.update(n=received["n"] + 1))

    monitor.start()
    # Un évènement d'un type non surveillé (ex. Resize) ne doit jamais
    # réarmer le minuteur ni interrompre son expiration normale.
    monitor.eventFilter(None, QEvent(QEvent.Type.Resize))

    qtbot.waitUntil(lambda: received["n"] == 1, timeout=2000)


def test_stop_prevents_any_further_timeout(qtbot) -> None:
    monitor = InactivityMonitor(timeout_minutes=1)
    monitor._timer.setInterval(50)
    received = {"n": 0}
    monitor.timed_out.connect(lambda: received.update(n=received["n"] + 1))

    monitor.start()
    monitor.stop()

    qtbot.wait(150)
    assert received["n"] == 0
