"""Point d'entrée de l'application StockManager Desktop."""
from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.config.db_config_store import default_db_config_path, promote_pending_to_active
from app.config.settings import Settings, resolve_data_dir
from app.db.init_db import init_database
from app.db.reference_data_sync import sync_reference_data
from app.db.seed import seed_initial_admin, seed_reference_data
from app.db.session import session_scope
from app.db.unite_article_seed import sync_unites_article_reference_data
from app.resources import load_stylesheet
from app.services.registry import ServiceRegistry, build_service_registry
from app.utils.error_handler import install_global_exception_handler
from app.utils.exceptions import AppError
from app.utils.logging_config import get_logger, setup_logging
from app.version import APP_NAME, __version__
from app.views.change_password_dialog import ChangePasswordDialog
from app.views.database_setup_wizard import DatabaseSetupWizard
from app.views.database_unreachable_dialog import DatabaseUnreachableDialog
from app.views.loading_overlay import StartupSplash
from app.views.login_window import LoginWindow
from app.views.main_window import MainWindow

_GENERIC_STARTUP_FAILURE_MESSAGE = (
    "Impossible de démarrer StockManager Desktop : l'initialisation de la base de "
    "données a échoué (connexion refusée, serveur inaccessible, ou configuration "
    "invalide).\n\n"
    "Si une configuration PostgreSQL a été préparée récemment, vérifiez-la depuis "
    "l'écran d'administration de la base de données après un démarrage réussi, ou "
    "contactez votre administrateur.\n\n"
    "Les détails techniques ont été enregistrés dans le journal de l'application."
)


def apply_pending_db_config_if_any() -> None:
    """Fait passer une configuration en attente à l'état actif — à appeler
    une seule fois, avant le premier appel à :func:`get_settings` de ce
    processus (voir ``app.config.db_config_store.promote_pending_to_active`` :
    jamais en cours de session, jamais de changement de moteur à chaud).

    Sans effet si ``STOCKMANAGER_DB_BACKEND`` est défini (déploiement
    scripté, Lot A) : dans ce cas, ``_load_settings_from_env`` ne consulte
    jamais le fichier externe, qui doit donc rester intact — voir
    ``app.config.settings._load_settings_from_env``."""
    if "STOCKMANAGER_DB_BACKEND" in os.environ:
        return
    promote_pending_to_active(default_db_config_path(resolve_data_dir()))


def _is_first_run(settings: Settings) -> bool:
    """Vrai uniquement si rien n'a jamais été configuré sur ce poste : ni
    fichier de configuration externe, ni base SQLite déjà créée par une
    exécution précédente (§4.7 du mandat : l'assistant ne doit jamais
    interrompre une installation existante, même si elle n'a jamais
    possédé de fichier de configuration externe — tout le Lot D est
    postérieur à de telles installations). Un déploiement scripté
    (``STOCKMANAGER_DB_BACKEND`` défini) n'est jamais considéré comme un
    premier lancement : ``settings.db_backend`` y vaut alors directement
    la valeur de la variable, jamais ``'sqlite'`` par absence de
    configuration."""
    if default_db_config_path(settings.data_dir).exists():
        return False
    return settings.db_backend == "sqlite" and not settings.db_path.exists()


def maybe_show_first_run_wizard() -> None:
    """Affiche l'assistant de première configuration si nécessaire — à
    appeler après :func:`apply_pending_db_config_if_any` et avant
    :func:`bootstrap` (donc avant toute connexion à une base, avant toute
    authentification). N'écrit jamais ``active`` : au plus une
    configuration ``pending`` PostgreSQL, qui ne sera appliquée qu'au
    prochain démarrage (voir docstring de ``app.views.database_setup_wizard``)."""
    settings = get_settings()
    if not _is_first_run(settings):
        return
    DatabaseSetupWizard(settings).exec()


def bootstrap() -> None:
    """Prépare l'environnement d'exécution avant l'ouverture de l'interface :
    configuration, logging, gestion des erreurs, schéma de base de données,
    données de référence (rôles/permissions, initialisation puis
    synchronisation additive pour les bases existantes) et compte
    administrateur initial.

    N'applique plus elle-même de configuration en attente (voir
    :func:`apply_pending_db_config_if_any`, appelée séparément par
    :func:`main` avant l'assistant de première configuration) : un second
    appel ici promouvrait immédiatement, dans le même processus, une
    configuration que l'assistant vient d'enregistrer — exactement le
    changement à chaud interdit par le mandat.

    Peut lever (connexion impossible, configuration invalide) : à
    appeler uniquement après la création de ``QApplication`` (voir
    :func:`main`), pour qu'un échec puisse être présenté par une boîte de
    dialogue visible plutôt que de se terminer silencieusement."""
    settings = get_settings()
    setup_logging(settings)
    install_global_exception_handler()

    logger = get_logger("bootstrap")
    logger.info(
        "Démarrage de %s %s (environnement=%s, moteur=%s)",
        APP_NAME, __version__, settings.environment, settings.db_backend,
    )

    init_database(settings)
    with session_scope(settings) as session:
        seed_reference_data(session)
        sync_reference_data(session)
        sync_unites_article_reference_data(session)
        generated_password = seed_initial_admin(session)

    if generated_password:
        logger.warning(
            "Compte administrateur initial créé : identifiant 'admin', "
            "mot de passe temporaire : %s (changement obligatoire à la première connexion).",
            generated_password,
        )


def _show_fatal_startup_error(exc: Exception) -> None:
    """Affiche un message clair et sûr (jamais de secret ni de trace
    technique brute) pour un échec survenu pendant :func:`bootstrap` —
    toujours appelée après la création de ``QApplication`` (voir
    :func:`main`), pour que la boîte de dialogue soit réellement visible
    (``app.utils.error_handler._show_error_dialog`` ne montre rien si
    aucune ``QApplication`` n'existe encore)."""
    get_logger("bootstrap").critical("Échec critique au démarrage : %s", exc, exc_info=True)

    # Une AppError est, par convention de ce projet, déjà un message métier
    # sûr à afficher tel quel (voir app.utils.error_handler.handle_exception) ;
    # toute autre exception (ex. erreur SQLAlchemy/psycopg brute) ne doit
    # jamais être interpolée directement — message générique fixe à la place.
    message = str(exc) if isinstance(exc, AppError) else _GENERIC_STARTUP_FAILURE_MESSAGE

    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("Démarrage impossible")
    box.setText(message)
    box.exec()


def _recover_from_startup_failure(exc: Exception) -> Optional[Exception]:
    """Phase accès réseau, point 1 : si :func:`bootstrap` échoue parce que
    le moteur configuré est PostgreSQL et que le serveur est injoignable
    (ou mal configuré), offre un chemin de correction — écran de
    configuration atteignable, correction des paramètres, test, nouvel
    essai — au lieu de quitter immédiatement l'application.

    Ne s'applique jamais à un déploiement scripté
    (``STOCKMANAGER_DB_BACKEND`` défini : aucun fichier de configuration
    externe à corriger, voir ``apply_pending_db_config_if_any``) ni à
    SQLite (base locale, pas de recours réseau applicable). Ne s'applique
    non plus jamais à une exception qui n'est pas une
    ``sqlalchemy.exc.OperationalError`` (voir ``app.db.session`` : c'est la
    convention déjà établie dans tout ce projet pour distinguer une
    connexion impossible — hôte injoignable, authentification refusée,
    base inexistante — d'une autre cause, notamment une migration Alembic
    qui échoue réellement sur un schéma déjà connecté). Une erreur de
    migration (``ProgrammingError``, ``IntegrityError``, bug Python dans un
    script de migration, etc.) n'a aucune chance d'être corrigée en
    modifiant l'hôte/le port/les identifiants : la présenter comme une
    indisponibilité réseau serait trompeur et retarderait le vrai
    diagnostic. Dans tous ces cas, retourne ``exc`` immédiatement et
    l'appelant le traite comme fatal, exactement comme avant ce lot.

    Retourne ``None`` si l'utilisateur a obtenu, après une ou plusieurs
    corrections, un démarrage réussi (``bootstrap()`` n'a plus levé) ; sinon
    la plus récente exception rencontrée (celle à afficher), que
    l'utilisateur ait renoncé (bouton Quitter, fermeture du dialogue) ou
    qu'une nouvelle tentative ait échoué à son tour — pour une tentative
    suivante aussi, seule une nouvelle ``OperationalError`` fait boucler le
    dialogue ; toute autre exception devient immédiatement la valeur
    retournée, sans nouvel affichage du dialogue de correction réseau."""
    if "STOCKMANAGER_DB_BACKEND" in os.environ:
        return exc
    if not isinstance(exc, OperationalError):
        return exc
    try:
        settings = get_settings()
    except Exception:
        return exc
    if settings.db_backend != "postgresql":
        return exc

    current_failure = exc
    while True:
        dialog = DatabaseUnreachableDialog(settings, current_failure)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return current_failure

        get_settings.cache_clear()
        try:
            bootstrap()
        except Exception as retry_exc:  # noqa: BLE001 - même frontière que main()
            if not isinstance(retry_exc, OperationalError):
                return retry_exc
            current_failure = retry_exc
            try:
                settings = get_settings()
            except Exception:
                return current_failure
            continue
        return None


def run_session(services: ServiceRegistry) -> bool:
    """Exécute un cycle connexion -> fenêtre principale -> déconnexion.

    Retourne True si l'utilisateur s'est déconnecté (relancer un nouveau
    cycle), False s'il a fermé la fenêtre de connexion (quitter l'application).
    """
    login_window = LoginWindow(services.auth, services.account_recovery, services.settings.data_dir)
    if login_window.exec() != QDialog.DialogCode.Accepted:
        return False

    current_user = services.auth.current_user
    if current_user is not None and current_user.must_change_password:
        change_dialog = ChangePasswordDialog(services.auth, forced=True)
        if change_dialog.exec() != QDialog.DialogCode.Accepted:
            services.auth.logout()
            return True

    # Phase amélioration UX, point 3 : entre la fermeture de la fenêtre de
    # connexion (ci-dessus) et l'affichage de la fenêtre principale,
    # MainWindow.__init__ construit toutes les pages (chacune avec son
    # propre chargement de données) — plusieurs secondes sans aucune
    # fenêtre visible, perçues comme un gel de l'application. Une fenêtre
    # de transition comble cet écart ; jamais de QThread autour de cette
    # construction (sessions SQLAlchemy ouvertes par chaque page sur le
    # thread appelant, comme partout ailleurs dans l'application).
    splash = StartupSplash("Chargement des données…")
    splash.show()
    QApplication.processEvents()
    try:
        window = MainWindow(services)
    finally:
        splash.close()

    loop = QEventLoop()
    window.logout_requested.connect(loop.quit)
    window.destroyed.connect(loop.quit)
    window.show()
    loop.exec()

    return True


def main() -> int:
    # Lot D (§4.6 du mandat) : QApplication est créée avant toute
    # initialisation risquée (configuration, connexion à la base), pour
    # qu'un échec critique puisse être présenté par une boîte de dialogue
    # visible plutôt que de se terminer silencieusement sans aucun message
    # (c'était le cas auparavant : QApplication n'existait pas encore
    # lorsque bootstrap() pouvait lever).
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    # Refonte visuelle globale : le style Fusion est le seul rendu de façon
    # fiable et identique par la feuille de style ci-dessous (app.qss) sur
    # Windows/Linux/macOS — un style natif (ex. « windowsvista ») ignore ou
    # rend de façon incohérente certains sélecteurs (QGroupBox::title,
    # indicateurs QCheckBox/QRadioButton, QPushButton[variant=...]).
    # Purement visuel : aucune incidence sur le comportement applicatif.
    app.setStyle("Fusion")

    try:
        apply_pending_db_config_if_any()
        maybe_show_first_run_wizard()
        bootstrap()
    except Exception as exc:  # noqa: BLE001 - frontière explicite : voir _show_fatal_startup_error
        unresolved_failure = _recover_from_startup_failure(exc)
        if unresolved_failure is not None:
            _show_fatal_startup_error(unresolved_failure)
            return 1

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
