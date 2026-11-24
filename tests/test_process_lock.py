import os

import pytest

from app.utils.process_lock import ProcessLock, ProcessLockHeldError, _process_is_running


def test_acquire_succeeds_when_no_lock_file_exists(tmp_path) -> None:
    lock = ProcessLock(tmp_path / "agent.lock")

    assert lock.acquire() is True
    assert (tmp_path / "agent.lock").is_file()


def test_acquire_writes_current_pid(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"
    lock = ProcessLock(lock_path)

    lock.acquire()

    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_second_acquire_fails_while_first_process_is_alive(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"
    first = ProcessLock(lock_path)
    first.acquire()  # écrit le PID du processus de test courant, bien réel et actif

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


def test_context_manager_raises_when_lock_already_held(tmp_path) -> None:
    lock_path = tmp_path / "agent.lock"
    holder = ProcessLock(lock_path)
    holder.acquire()

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
