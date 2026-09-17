import logging
from typing import Iterator

import pytest

import app.utils.logging_config as logging_config
from app.config.settings import Settings


@pytest.fixture(autouse=True)
def _isolated_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isole chaque test de l'état global du logger 'stockmanager' (singleton process-wide)."""
    logger = logging.getLogger("stockmanager")
    monkeypatch.setattr(logging_config, "_configured", False)
    saved_handlers = logger.handlers[:]
    logger.handlers.clear()
    yield
    logger.handlers.clear()
    logger.handlers.extend(saved_handlers)


def test_setup_logging_creates_log_file(test_settings: Settings) -> None:
    logger = logging_config.setup_logging(test_settings)
    logger.info("message de test")
    for handler in logger.handlers:
        handler.flush()

    log_file = test_settings.log_dir / logging_config.LOG_FILENAME
    assert log_file.exists()
    assert "message de test" in log_file.read_text(encoding="utf-8")


def test_setup_logging_sets_configured_level(test_settings: Settings) -> None:
    logger = logging_config.setup_logging(test_settings)
    assert logger.level == logging.DEBUG  # STOCKMANAGER_LOG_LEVEL=DEBUG dans test_settings


def test_setup_logging_is_idempotent(test_settings: Settings) -> None:
    logger1 = logging_config.setup_logging(test_settings)
    handler_count_after_first = len(logger1.handlers)

    logger2 = logging_config.setup_logging(test_settings)

    assert logger2 is logger1
    assert len(logger2.handlers) == handler_count_after_first == 2


def test_get_logger_returns_child_of_stockmanager() -> None:
    logger = logging_config.get_logger("some.module")
    assert logger.name == "stockmanager.some.module"
