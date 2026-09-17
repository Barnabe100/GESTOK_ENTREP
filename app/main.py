"""Point d'entrée de l'application StockManager Desktop."""
from __future__ import annotations

import sys

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QDialog

from app.config import get_settings
from app.db.init_db import init_database
from app.db.seed import seed_initial_admin, seed_reference_data
from app.db.session import session_scope
from app.resources import load_stylesheet
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.services.categories.category_service import CategoryService
from app.services.users.user_service import UserService
from app.utils.error_handler import install_global_exception_handler
from app.utils.logging_config import get_logger, setup_logging
from app.views.change_password_dialog import ChangePasswordDialog
from app.views.login_window import LoginWindow
from app.views.main_window import MainWindow


def bootstrap() -> None:
    """Prépare l'environnement d'exécution avant l'ouverture de l'interface :
    configuration, logging, gestion des erreurs, schéma de base de données,
    données de référence (rôles/permissions) et compte administrateur initial."""
    settings = get_settings()
    setup_logging(settings)
    install_global_exception_handler()

    logger = get_logger("bootstrap")
    logger.info("Démarrage de StockManager Desktop (environnement=%s)", settings.environment)

    init_database(settings)
    with session_scope(settings) as session:
        seed_reference_data(session)
        generated_password = seed_initial_admin(session)

    if generated_password:
        logger.warning(
            "Compte administrateur initial créé : identifiant 'admin', "
            "mot de passe temporaire : %s (changement obligatoire à la première connexion).",
            generated_password,
        )


def run_session(
    auth_service: AuthService,
    permission_service: PermissionService,
    user_service: UserService,
    category_service: CategoryService,
) -> bool:
    """Exécute un cycle connexion -> fenêtre principale -> déconnexion.

    Retourne True si l'utilisateur s'est déconnecté (relancer un nouveau
    cycle), False s'il a fermé la fenêtre de connexion (quitter l'application).
    """
    login_window = LoginWindow(auth_service)
    if login_window.exec() != QDialog.DialogCode.Accepted:
        return False

    current_user = auth_service.current_user
    if current_user is not None and current_user.must_change_password:
        change_dialog = ChangePasswordDialog(auth_service, forced=True)
        if change_dialog.exec() != QDialog.DialogCode.Accepted:
            auth_service.logout()
            return True

    window = MainWindow(auth_service, permission_service, user_service, category_service)

    loop = QEventLoop()
    window.logout_requested.connect(loop.quit)
    window.destroyed.connect(loop.quit)
    window.show()
    loop.exec()

    return True


def main() -> int:
    bootstrap()

    app = QApplication(sys.argv)
    app.setApplicationName("StockManager Desktop")
    try:
        app.setStyleSheet(load_stylesheet())
    except OSError:
        get_logger("bootstrap").warning("Feuille de style introuvable, style par défaut utilisé.")

    settings = get_settings()
    auth_service = AuthService(settings)
    permission_service = PermissionService(auth_service)
    user_service = UserService(permission_service, settings)
    category_service = CategoryService(permission_service, settings)

    while run_session(auth_service, permission_service, user_service, category_service):
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
