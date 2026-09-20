"""Point d'entrée de l'application StockManager Desktop."""
from __future__ import annotations

import sys

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QDialog

from app.config import get_settings
from app.db.init_db import init_database
from app.db.reference_data_sync import sync_reference_data
from app.db.seed import seed_initial_admin, seed_reference_data
from app.db.session import session_scope
from app.resources import load_stylesheet
from app.services.registry import ServiceRegistry, build_service_registry
from app.utils.error_handler import install_global_exception_handler
from app.utils.logging_config import get_logger, setup_logging
from app.version import APP_NAME, __version__
from app.views.change_password_dialog import ChangePasswordDialog
from app.views.login_window import LoginWindow
from app.views.main_window import MainWindow


def bootstrap() -> None:
    """Prépare l'environnement d'exécution avant l'ouverture de l'interface :
    configuration, logging, gestion des erreurs, schéma de base de données,
    données de référence (rôles/permissions, initialisation puis
    synchronisation additive pour les bases existantes) et compte
    administrateur initial."""
    settings = get_settings()
    setup_logging(settings)
    install_global_exception_handler()

    logger = get_logger("bootstrap")
    logger.info(
        "Démarrage de %s %s (environnement=%s)", APP_NAME, __version__, settings.environment
    )

    init_database(settings)
    with session_scope(settings) as session:
        seed_reference_data(session)
        sync_reference_data(session)
        generated_password = seed_initial_admin(session)

    if generated_password:
        logger.warning(
            "Compte administrateur initial créé : identifiant 'admin', "
            "mot de passe temporaire : %s (changement obligatoire à la première connexion).",
            generated_password,
        )


def run_session(services: ServiceRegistry) -> bool:
    """Exécute un cycle connexion -> fenêtre principale -> déconnexion.

    Retourne True si l'utilisateur s'est déconnecté (relancer un nouveau
    cycle), False s'il a fermé la fenêtre de connexion (quitter l'application).
    """
    login_window = LoginWindow(services.auth)
    if login_window.exec() != QDialog.DialogCode.Accepted:
        return False

    current_user = services.auth.current_user
    if current_user is not None and current_user.must_change_password:
        change_dialog = ChangePasswordDialog(services.auth, forced=True)
        if change_dialog.exec() != QDialog.DialogCode.Accepted:
            services.auth.logout()
            return True

    window = MainWindow(services)

    loop = QEventLoop()
    window.logout_requested.connect(loop.quit)
    window.destroyed.connect(loop.quit)
    window.show()
    loop.exec()

    return True


def main() -> int:
    bootstrap()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    try:
        app.setStyleSheet(load_stylesheet())
    except OSError:
        get_logger("bootstrap").warning("Feuille de style introuvable, style par défaut utilisé.")

    services = build_service_registry(get_settings())

    while run_session(services):
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
