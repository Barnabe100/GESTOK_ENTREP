"""Gestion centralisée des erreurs non interceptées.

Toute exception qui remonte jusqu'à la boucle d'événements Qt sans avoir été
gérée localement passe par ce point unique : elle est journalisée, puis
présentée à l'utilisateur de façon lisible, sans faire planter l'application.
"""
from __future__ import annotations

import logging
import sys
import traceback
from types import TracebackType

from app.utils.exceptions import AppError

_logger = logging.getLogger("stockmanager").getChild("errors")

_GENERIC_MESSAGE = (
    "Une erreur inattendue est survenue. L'opération a été annulée.\n"
    "Les détails techniques ont été enregistrés dans le journal de l'application."
)


def _show_error_dialog(title: str, message: str) -> None:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        return

    app = QApplication.instance()
    if app is None:
        return

    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    box.setText(message)
    box.exec()


def handle_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    """Point d'entrée unique pour toute exception non interceptée."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    _logger.critical("Exception non interceptée :\n%s", formatted)

    if issubclass(exc_type, AppError):
        _show_error_dialog("Opération refusée", str(exc_value))
    else:
        _show_error_dialog("Erreur inattendue", _GENERIC_MESSAGE)


def install_global_exception_handler() -> None:
    """Installe :data:`handle_exception` comme ``sys.excepthook`` global."""
    sys.excepthook = handle_exception
