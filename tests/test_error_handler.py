import logging
import sys
from typing import Iterator

import pytest

from app.utils.error_handler import handle_exception, install_global_exception_handler
from app.utils.exceptions import ValidationError


class _ListHandler(logging.Handler):
    """Capture les enregistrements de log sans dépendre de la propagation racine
    (robuste même si un autre test a déjà appelé setup_logging())."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture()
def captured_error_logs() -> Iterator[_ListHandler]:
    logger = logging.getLogger("stockmanager").getChild("errors")
    handler = _ListHandler()
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def test_install_global_exception_handler_sets_excepthook() -> None:
    original = sys.excepthook
    try:
        install_global_exception_handler()
        assert sys.excepthook is handle_exception
    finally:
        sys.excepthook = original


def test_handle_exception_logs_validation_error(captured_error_logs: _ListHandler) -> None:
    try:
        raise ValidationError("stock négatif refusé")
    except ValidationError:
        handle_exception(*sys.exc_info())

    messages = [record.getMessage() for record in captured_error_logs.records]
    assert any("stock négatif refusé" in message for message in messages)


def test_handle_exception_logs_unexpected_error(captured_error_logs: _ListHandler) -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        handle_exception(*sys.exc_info())

    messages = [record.getMessage() for record in captured_error_logs.records]
    assert any("boom" in message for message in messages)


def test_handle_exception_does_not_raise_without_qapplication(
    captured_error_logs: _ListHandler,
) -> None:
    """En l'absence de QApplication active, le gestionnaire ne doit jamais lever."""
    try:
        raise ValidationError("test sans interface graphique")
    except ValidationError:
        handle_exception(*sys.exc_info())  # ne doit pas lever


def test_handle_exception_reraises_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {}

    def fake_original_hook(exc_type, exc_value, exc_tb) -> None:  # noqa: ANN001
        called["invoked"] = True

    monkeypatch.setattr(sys, "__excepthook__", fake_original_hook)
    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        handle_exception(*sys.exc_info())

    assert called.get("invoked") is True
