"""Configuration centralisée de la journalisation applicative (logs techniques).

Ceci est distinct de la table ``audit_logs`` (journalisation métier en base),
qui sera alimentée par les services des phases suivantes.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app.config import Settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FILENAME = "stockmanager.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 Mo
BACKUP_COUNT = 5

_configured = False


def setup_logging(settings: Settings) -> logging.Logger:
    """Configure le logger racine de l'application.

    Idempotent : un appel répété ne duplique pas les handlers.
    """
    global _configured

    root_logger = logging.getLogger("stockmanager")
    root_logger.setLevel(settings.log_level)

    if _configured:
        return root_logger

    settings.ensure_directories()
    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    log_file: Path = settings.log_dir / LOG_FILENAME
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    root_logger.propagate = False
    _configured = True
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger enfant du logger applicatif (ex. ``get_logger(__name__)``)."""
    return logging.getLogger("stockmanager").getChild(name)
