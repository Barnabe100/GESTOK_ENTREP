import os
import subprocess
import sys
import time

import pytest

from app.utils.process_lock import ProcessLock, ProcessLockHeldError, _process_is_running


@pytest.fixture
def other_process():
    """Un processus réel et distinct (jamais une simulation par PID
    arbitraire, qui pourrait coïncider avec un processus différent déjà
    terminé) — utilisé pour les tests ci-dessous vérifiant le refus face à
    un AUTRE processus réellement actif, par opposition à la réentrance
    intra-processus (mission corrective, §3.7 — voir
    ``app.utils.process_lock``, docstring de module, et les tests dédiés
    plus bas dans ce fichier)."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    time.sleep(0.2)  # laisse le temps au processus de démarrer réellement.
    try:
        yield proc
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_acquire_succeeds_when_no_lock_file_exists(tmp_path) -> None:
    lock = ProcessLock(tmp_path / "agent.lock")

    assert lock.acquire() is True
    assert (tmp_path / "agent.lock").is_file()


def test_acquire_writes_current_pid(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"
    lock = ProcessLock(lock_path)

    lock.acquire()

    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_second_acquire_fails_while_another_process_is_alive(tmp_path, other_process) -> None:
    lock_path = tmp_path / "agent.lock"
    lock_path.write_text(str(other_process.pid), encoding="utf-8")

    second = ProcessLock(lock_path)

    assert second.acquire() is False


def test_release_allows_reacquiring(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"
    first = ProcessLock(lock_path)
    first.acquire()
    first.release()

    second = ProcessLock(lock_path)

    assert second.acquire() is True


def test_release_without_acquire_is_a_no_op(tmp_path) -> None:
    lock = ProcessLock(tmp_path / "agent.lock")

    lock.release()  # ne doit jamais lever

    assert not (tmp_path / "agent.lock").exists()


def test_stale_lock_from_dead_process_is_reclaimed(tmp_path) -> None:
    """Un PID garanti inexistant (très grande valeur improbable) simule un
    processus disparu sans nettoyage — le verrou doit être repris, jamais
    bloquer indéfiniment."""
    lock_path = tmp_path / "agent.lock"
    lock_path.write_text("999999999", encoding="utf-8")

    lock = ProcessLock(lock_path)

    assert lock.acquire() is True
    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_lock_file_with_corrupted_content_is_reclaimed(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"
    lock_path.write_text("ceci n'est pas un PID", encoding="utf-8")

    lock = ProcessLock(lock_path)

    assert lock.acquire() is True


def test_context_manager_acquires_and_releases(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"

    with ProcessLock(lock_path) as lock:
        assert lock_path.is_file()

    assert not lock_path.exists()


def test_context_manager_raises_when_lock_already_held_by_another_process(tmp_path, other_process) -> None:
    lock_path = tmp_path / "agent.lock"
    lock_path.write_text(str(other_process.pid), encoding="utf-8")

    with pytest.raises(ProcessLockHeldError):
        with ProcessLock(lock_path):
            pass


def test_context_manager_releases_even_on_exception(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"

    with pytest.raises(ValueError):
        with ProcessLock(lock_path):
            raise ValueError("erreur quelconque pendant l'opération verrouillée")

    assert not lock_path.exists()


def test_process_is_running_true_for_current_process() -> None:
    assert _process_is_running(os.getpid()) is True


def test_process_is_running_false_for_implausible_pid() -> None:
    assert _process_is_running(999999999) is False


def test_process_is_running_false_for_non_positive_pid() -> None:
    assert _process_is_running(0) is False
    assert _process_is_running(-1) is False


# -- mission corrective §3.7 : réentrance intra-processus ------------------------


def test_second_instance_same_process_can_reacquire_the_same_lock(tmp_path) -> None:
    """Jamais un verrouillage récursif (exigence explicite du mandat
    correctif) : une seconde instance ``ProcessLock`` pointant sur le même
    fichier, dans ce même processus, doit pouvoir l'acquérir sans jamais
    se bloquer elle-même — exactement le scénario d'un appel imbriqué
    (ex. l'agent détient déjà le verrou, une méthode de service qu'il
    appelle tente de l'acquérir à nouveau)."""
    lock_path = tmp_path / "agent.lock"
    outer = ProcessLock(lock_path)
    assert outer.acquire() is True

    inner = ProcessLock(lock_path)
    assert inner.acquire() is True


def test_lock_file_not_removed_until_outermost_release(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"
    outer = ProcessLock(lock_path)
    inner = ProcessLock(lock_path)
    outer.acquire()
    inner.acquire()

    inner.release()
    assert lock_path.exists()  # le verrou extérieur le détient toujours.

    outer.release()
    assert not lock_path.exists()


def test_reentrant_lock_still_refuses_a_genuinely_different_process(tmp_path, other_process) -> None:
    """La réentrance ne doit jamais affaiblir la protection contre un AUTRE
    processus réellement actif — seule la réacquisition par CE processus
    est facilitée."""
    lock_path = tmp_path / "agent.lock"
    lock_path.write_text(str(other_process.pid), encoding="utf-8")

    ours = ProcessLock(lock_path)
    assert ours.acquire() is False
    # Même après cet échec, une tentative ultérieure (toujours face au même
    # processus externe) doit continuer d'échouer, jamais mémoriser à tort
    # une acquisition qui n'a pourtant pas eu lieu.
    assert ProcessLock(lock_path).acquire() is False


def test_release_order_does_not_matter_for_reentrant_locks(tmp_path) -> None:
    """Libérer d'abord le verrou EXTÉRIEUR (ordre inhabituel mais possible
    si un appelant ne respecte pas strictement l'imbrication) ne doit
    jamais lever ni laisser le fichier dans un état incohérent."""
    lock_path = tmp_path / "agent.lock"
    outer = ProcessLock(lock_path)
    inner = ProcessLock(lock_path)
    outer.acquire()
    inner.acquire()

    outer.release()  # ne doit jamais lever, même si ce n'est pas le dernier.
    assert lock_path.exists()

    inner.release()
    assert not lock_path.exists()


def test_context_manager_nesting_works_without_deadlock(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"

    with ProcessLock(lock_path):
        with ProcessLock(lock_path):
            assert lock_path.is_file()
        assert lock_path.is_file()  # le verrou extérieur le détient encore.

    assert not lock_path.exists()
