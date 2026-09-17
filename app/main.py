"""Point d'entrée de l'application StockManager Desktop."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config import get_settings
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from app.db.session import session_scope
from app.resources import load_stylesheet
from app.utils.error_handler import install_global_exception_handler
from app.utils.logging_config import get_logger, setup_logging
from app.views.main_window import MainWindow


def bootstrap() -> None:
    """Prépare l'environnement d'exécution avant l'ouverture de l'interface :
    configuration, logging, gestion des erreurs, schéma de base de données."""
    settings = get_settings()
    setup_logging(settings)
    install_global_exception_handler()

    logger = get_logger("bootstrap")
    logger.info("Démarrage de StockManager Desktop (environnement=%s)", settings.environment)

    init_database(settings)
    with session_scope(settings) as session:
        seed_reference_data(session)


def main() -> int:
    bootstrap()

    app = QApplication(sys.argv)
    app.setApplicationName("StockManager Desktop")
    try:
        app.setStyleSheet(load_stylesheet())
    except OSError:
        get_logger("bootstrap").warning("Feuille de style introuvable, style par défaut utilisé.")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
