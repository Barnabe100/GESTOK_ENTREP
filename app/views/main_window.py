"""Fenêtre principale et navigation filtrée par permissions.

Aucune logique métier ni aucune décision d'autorisation « en dur » ici : la
liste des modules visibles est calculée une fois, à la construction, à
partir de :class:`PermissionService`. Le filtrage à l'affichage n'est qu'un
confort d'ergonomie — chaque action sensible (ex. activer/désactiver un
compte) revérifie la permission côté service (voir ``UsersPage``), de sorte
qu'un contournement de l'interface ne suffit jamais à obtenir un accès non
autorisé.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.db.change_listener import PostgreSQLChangeListener
from app.db.seed import INITIAL_ADMIN_USERNAME
from app.resources import APP_ICON_PATH
from app.services.registry import ServiceRegistry
from app.services.settings.company_settings_service import is_rental_module_enabled
from app.utils.logging_config import get_logger
from app.version import __version__
from app.views.about_dialog import AboutDialog
from app.views.change_password_dialog import ChangePasswordDialog
from app.views.onboarding_dialog import OnboardingDialog
from app.views.pages.articles_page import ArticlesPage
from app.views.pages.audit_page import AuditPage
from app.views.pages.backups_page import BackupsPage
from app.views.pages.categories_page import CategoriesPage
from app.views.pages.clients_page import ClientsPage
from app.views.pages.dashboard_page import DashboardPage
from app.views.pages.database_admin_page import DatabaseAdminPage
from app.views.pages.entries_page import EntriesPage
from app.views.pages.exit_reasons_page import ExitReasonsPage
from app.views.pages.exits_page import ExitsPage
from app.views.pages.inventories_page import InventoriesPage
from app.views.pages.licenses_page import LicensesPage
from app.views.pages.locations_page import LocationsPage
from app.views.pages.mouvements_page import MouvementsPage
from app.views.pages.placeholder_page import PlaceholderPage
from app.views.pages.receivables_page import ReceivablesPage
from app.views.pages.reports_page import ReportsPage
from app.views.pages.roles_page import RolesPage
from app.views.pages.sales_page import SalesPage
from app.views.pages.settings_page import SettingsPage
from app.views.pages.suppliers_page import SuppliersPage
from app.views.pages.users_page import UsersPage

logger = get_logger("views.main_window")

# Fréquence de vérification du minuteur de sauvegarde planifiée (§7-8 de la
# phase Sauvegardes) : ce minuteur ne peut s'exécuter que si l'application
# est ouverte — voir app/backup_cli.py pour le cas application fermée.
_BACKUP_SCHEDULER_CHECK_INTERVAL_MS = 60_000

# Chantier D (synchronisation automatique multi-poste) : sondage non
# bloquant (voir app/db/change_listener.py) de la connexion LISTEN dédiée
# — jamais une requête sur les tables métier elles-mêmes, uniquement sur
# la file d'attente de notifications déjà en mémoire côté serveur.
_CHANGE_LISTENER_POLL_INTERVAL_MS = 2_000

# Filet de sécurité (notification manquée pendant une coupure réseau, ou
# émission NOTIFY elle-même en échec côté émetteur — voir
# app/db/change_notifications.py) : rafraîchit l'écran actif indépendamment
# des notifications reçues, à une fréquence volontairement beaucoup plus
# basse que le sondage ci-dessus (c'est une requête réelle sur les données
# de l'écran concerné, contrairement au sondage LISTEN).
_CHANGE_RECONCILIATION_INTERVAL_MS = 90_000

# Ordre de navigation conforme au cahier des charges (§22), complété par
# « Motifs de sortie » (administration réservée à l'Administrateur, cf.
# app/db/seed.py), et permission de consultation requise pour que chaque
# module apparaisse dans le menu.
NAVIGATION_MODULES: list[str] = [
    "Dashboard",
    "Articles",
    "Catégories",
    "Fournisseurs",
    "Motifs de sortie",
    "Entrées",
    "Sorties",
    "Clients",
    "Ventes",
    "Créances",
    "Locations",
    "Mouvements",
    "Inventaires",
    "Rapports",
    "Utilisateurs",
    "Rôles",
    "Paramètres",
    "Base de données",
    "Sauvegardes",
    "Audit",
    "Licences",
]

NAVIGATION_PERMISSIONS: dict[str, str] = {
    "Dashboard": "DASHBOARD_VIEW",
    "Articles": "ARTICLE_VIEW",
    "Catégories": "CATEGORY_VIEW",
    "Fournisseurs": "SUPPLIER_VIEW",
    "Motifs de sortie": "STOCK_REASON_VIEW",
    "Entrées": "STOCK_ENTRY_VIEW",
    "Sorties": "STOCK_EXIT_VIEW",
    "Clients": "CLIENT_VIEW",
    "Ventes": "SALE_VIEW",
    # Réutilise SALE_VIEW (pas de nouvelle permission dédiée à la lecture des
    # créances, qui n'est qu'une vue filtrée des ventes déjà consultables).
    "Créances": "SALE_VIEW",
    "Locations": "LOCATION_VIEW",
    "Mouvements": "STOCK_MOVEMENT_VIEW",
    "Inventaires": "INVENTORY_VIEW",
    "Rapports": "REPORT_VIEW",
    "Utilisateurs": "USER_VIEW",
    "Rôles": "ROLE_VIEW",
    "Paramètres": "SETTINGS_VIEW",
    "Base de données": "DATABASE_CONFIG_VIEW",
    "Sauvegardes": "BACKUP_VIEW",
    "Audit": "AUDIT_VIEW",
    "Licences": "LICENSE_VIEW",
}


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(self, services: ServiceRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._services = services
        self._permissions = services.permissions

        # Lot 16 : « Locations » n'apparaît dans la navigation principale que
        # si le module est actif (``locations.actif``), en plus de la
        # permission déjà requise — jamais l'inverse d'une permission, et
        # indépendant de la licence/FeatureGate. Le consultation des
        # locations existantes reste possible même désactivé, via un chemin
        # explicite distinct (voir _build_top_bar/_open_locations_readonly_dialog),
        # qui revérifie LOCATION_VIEW indépendamment de cette liste.
        self.visible_modules: list[str] = [
            module
            for module in NAVIGATION_MODULES
            if self._permissions.has_permission(NAVIGATION_PERMISSIONS[module])
            and (module != "Locations" or is_rental_module_enabled())
        ]

        self.setWindowTitle("StockManager Desktop")
        self.resize(1200, 750)
        # Lot 22 (anomalie B) : taille minimale explicite égale à la taille
        # de départ. ``QStackedWidget`` réserve, pour sa taille minimale,
        # l'espace nécessaire au plus exigeant de tous les modules qu'il
        # contient (pas seulement celui actuellement affiché) ; cette
        # contribution peut ne se stabiliser qu'au premier affichage réel
        # d'une page jusqu'alors jamais montrée, provoquant un recalcul de
        # géométrie visible (plus particulièrement sous Windows, où les
        # métriques de police par défaut diffèrent). Fixer ce plancher
        # garantit que la fenêtre ne peut plus jamais redescendre sous sa
        # taille d'ouverture lors d'un changement de module, quelle que
        # soit la page concernée — sans aucun appel supplémentaire à
        # resize()/showNormal()/showMaximized()/adjustSize() dans la
        # navigation elle-même.
        self.setMinimumSize(1200, 750)

        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

        central_widget = QWidget(self)
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.navigation_list = self._build_navigation_list()
        root_layout.addWidget(self.navigation_list)

        content_area = self._build_content_area()
        root_layout.addWidget(content_area, stretch=1)

        self.navigation_list.currentRowChanged.connect(self._on_navigation_changed)
        if self.visible_modules:
            self.navigation_list.setCurrentRow(0)

        self.statusBar().showMessage(f"Prêt — StockManager Desktop {__version__}")

        # Minuteur de sauvegarde planifiée (§7-8) : ne peut s'exécuter que
        # tant que cette fenêtre (donc l'application) est ouverte. Le
        # service lui-même décide si une sauvegarde est réellement due
        # (activation/fréquence/heure) ; ce minuteur ne fait que le
        # solliciter régulièrement.
        self._backup_scheduler_timer = QTimer(self)
        self._backup_scheduler_timer.timeout.connect(self._check_scheduled_backup)
        self._backup_scheduler_timer.start(_BACKUP_SCHEDULER_CHECK_INTERVAL_MS)

        # Chantier D (synchronisation automatique) : jamais sous SQLite (un
        # seul poste existe alors, voir app/db/change_notifications.py) —
        # ``self._change_listener`` reste ``None`` dans ce cas, vérifié
        # avant chaque usage ci-dessous. ``services.settings`` (jamais
        # ``app.config.get_settings()``, le paramètre global du processus,
        # qui peut différer de l'instance réellement utilisée par CETTE
        # pile de services, notamment en test) — voir ServiceRegistry.
        self._change_listener: Optional[PostgreSQLChangeListener] = None
        if services.settings.db_backend == "postgresql":
            self._change_listener = PostgreSQLChangeListener(services.settings)
            # LISTEN souscrit dès l'ouverture, jamais paresseusement au
            # premier sondage : une notification émise entre l'ouverture de
            # la fenêtre et le premier passage du minuteur serait sinon
            # silencieusement perdue (NOTIFY n'est jamais un stockage
            # durable, voir app/db/change_notifications.py).
            self._change_listener.connect()

            self._change_listener_timer = QTimer(self)
            self._change_listener_timer.timeout.connect(self._poll_change_notifications)
            self._change_listener_timer.start(_CHANGE_LISTENER_POLL_INTERVAL_MS)

            self._change_reconciliation_timer = QTimer(self)
            self._change_reconciliation_timer.timeout.connect(self._reconcile_current_page)
            self._change_reconciliation_timer.start(_CHANGE_RECONCILIATION_INTERVAL_MS)

        self._maybe_show_onboarding_dialog()

    def closeEvent(self, event) -> None:  # noqa: N802 - signature imposée par Qt
        # Correctif (suite de non-régression) : ``close()`` masque la
        # fenêtre mais ne détruit pas immédiatement les ``QTimer`` qui lui
        # sont parentés (seule la destruction effective de l'objet C++ les
        # arrête, jamais ``close()`` seul) — sans cet arrêt explicite, un
        # minuteur resté actif peut se déclencher bien après la fermeture
        # de cette fenêtre (observé : un sondage tardif échouait sur un mot
        # de passe de test déjà hors de portée dans une suite de tests
        # ultérieure sans rapport). Arrêtés avant toute autre chose, pour
        # qu'aucun sondage/réconciliation ne puisse plus jamais se
        # déclencher après cet appel.
        if self._change_listener is not None:
            self._change_listener_timer.stop()
            self._change_reconciliation_timer.stop()
            self._change_listener.close()
        super().closeEvent(event)

    def _refresh_current_page(self) -> None:
        """Rafraîchit l'écran actuellement affiché — jamais un autre écran
        en arrière-plan (préserve sa saisie/ses filtres en cours, voir le
        mandat de ce lot, §6). Identique au rafraîchissement déjà déclenché
        par ``_on_navigation_changed`` à l'ouverture d'un écran, ici
        déclenché par une notification de changement ou la réconciliation
        périodique plutôt que par la navigation."""
        current_index = self.page_stack.currentIndex()
        if current_index < 0:
            return
        page = self.page_stack.widget(current_index)
        if hasattr(page, "refresh"):
            page.refresh()

    def _poll_change_notifications(self) -> None:
        """Sondage non bloquant (voir ``PostgreSQLChangeListener.poll``) —
        ne rafraîchit l'écran actif que si au moins une notification est
        réellement en attente, jamais à chaque sondage."""
        if self._change_listener is None:
            return
        entity_types = self._change_listener.poll()
        if entity_types:
            self._refresh_current_page()

    def _reconcile_current_page(self) -> None:
        """Filet de sécurité périodique (voir la docstring de
        ``_CHANGE_RECONCILIATION_INTERVAL_MS``) : rafraîchit l'écran actif
        même en l'absence de toute notification reçue."""
        self._refresh_current_page()

    def _build_navigation_list(self) -> QListWidget:
        navigation_list = QListWidget(self)
        navigation_list.setObjectName("navigationList")
        navigation_list.setFixedWidth(220)
        navigation_list.setIconSize(QSize(18, 18))
        for module_name in self.visible_modules:
            QListWidgetItem(module_name, navigation_list)
        return navigation_list

    def _build_content_area(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_top_bar(container))

        self.page_stack = QStackedWidget(container)
        self.page_stack.setObjectName("pageContainer")
        for module_name in self.visible_modules:
            self.page_stack.addWidget(self._build_page(module_name))
            # Correctif revue finale (Point 3) : la construction de toutes
            # les pages (chacune avec son propre chargement de données) est
            # l'opération de 2 à 5 s à l'origine du gel signalé — purger les
            # évènements en attente après chaque page, plutôt qu'une seule
            # fois avant toute la boucle (voir app/main.py:run_session, qui
            # affiche un StartupSplash pendant cet appel), permet au spinner
            # de ce voile de réellement s'animer (son QTimer ne peut se
            # déclencher que si la boucle d'évènements tourne) et réduit le
            # risque qu'un délai sans traitement de message dépasse le
            # seuil « Ne répond pas » de Windows. Sûr à cet instant précis :
            # cette fenêtre n'est pas encore affichée (``show()`` n'intervient
            # qu'après le retour de ce constructeur), self.navigation_list
            # n'est pas encore connecté à _on_navigation_changed (connecté
            # plus bas, après ce bloc) et aucun minuteur de cette fenêtre
            # n'est encore démarré — aucun évènement ne peut donc retomber
            # sur un widget pas encore construit pendant cette purge.
            QApplication.processEvents()
        layout.addWidget(self.page_stack, stretch=1)

        return container

    def _build_page(self, module_name: str) -> QWidget:
        if module_name == "Dashboard":
            return DashboardPage(self._services.dashboard, self._permissions, on_navigate=self.switch_to_module)
        if module_name == "Utilisateurs":
            return UsersPage(self._services.users, self._permissions)
        if module_name == "Rôles":
            return RolesPage(self._services.roles, self._permissions)
        if module_name == "Catégories":
            return CategoriesPage(self._services.categories, self._permissions)
        if module_name == "Fournisseurs":
            return SuppliersPage(self._services.suppliers, self._permissions)
        if module_name == "Motifs de sortie":
            return ExitReasonsPage(self._services.exit_reasons, self._permissions)
        if module_name == "Articles":
            return ArticlesPage(
                self._services.articles,
                self._services.categories,
                self._services.suppliers,
                self._services.unites_article,
                self._permissions,
            )
        if module_name == "Entrées":
            return EntriesPage(
                self._services.entries, self._services.suppliers, self._services.articles, self._permissions
            )
        if module_name == "Sorties":
            return ExitsPage(
                self._services.exits, self._services.exit_reasons, self._services.articles, self._permissions
            )
        if module_name == "Clients":
            return ClientsPage(self._services.clients, self._services.sales, self._permissions)
        if module_name == "Ventes":
            return SalesPage(
                self._services.sales, self._services.articles, self._services.clients,
                self._services.documents, self._permissions,
            )
        if module_name == "Créances":
            return ReceivablesPage(self._services.sales, self._services.clients, self._permissions)
        if module_name == "Locations":
            return LocationsPage(
                self._services.rentals, self._services.articles, self._services.clients, self._permissions,
                receipt_service=self._services.documents,
            )
        if module_name == "Mouvements":
            return MouvementsPage(self._services.movements, self._permissions)
        if module_name == "Inventaires":
            return InventoriesPage(self._services.inventory, self._services.articles, self._permissions)
        if module_name == "Rapports":
            return ReportsPage(
                self._services.reports, self._services.categories, self._services.articles,
                self._services.exit_reasons, self._permissions,
            )
        if module_name == "Paramètres":
            return SettingsPage(
                self._services.parameters, self._permissions, self._services.account_recovery,
                self._services.rentals,
            )
        if module_name == "Base de données":
            return DatabaseAdminPage(self._services.database_admin, self._permissions)
        if module_name == "Sauvegardes":
            return BackupsPage(self._services.backups, self._permissions, self._services.data_reset)
        if module_name == "Audit":
            return AuditPage(self._services.audit, self._permissions)
        if module_name == "Licences":
            return LicensesPage(self._services.licenses, self._services.activation, self._permissions)
        return PlaceholderPage(module_name)

    def _build_top_bar(self, parent: QWidget) -> QWidget:
        top_bar = QWidget(parent)
        top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(20, 14, 20, 14)

        initial_title = self.visible_modules[0] if self.visible_modules else ""
        self.page_title_label = QLabel(initial_title, top_bar)
        self.page_title_label.setObjectName("pageTitle")
        top_bar_layout.addWidget(self.page_title_label)
        top_bar_layout.addStretch(1)

        current_user = self._permissions.current_user
        user_text = (
            f"{current_user.username} ({', '.join(current_user.role_names)})" if current_user else ""
        )
        self.user_label = QLabel(user_text, top_bar)
        top_bar_layout.addWidget(self.user_label)

        # Lot 16 : chemin de consultation explicite des locations existantes
        # quand le module est désactivé — visible seulement dans ce cas (si
        # actif, l'entrée de navigation normale suffit déjà) et seulement
        # pour un utilisateur ayant LOCATION_VIEW (revérifié aussi par
        # LocationService à chaque appel, jamais contourné par ce bouton).
        self.locations_readonly_button = QPushButton("Consulter les locations (lecture seule)", top_bar)
        self.locations_readonly_button.setVisible(
            self._permissions.has_permission("LOCATION_VIEW") and not is_rental_module_enabled()
        )
        self.locations_readonly_button.clicked.connect(self._on_open_locations_readonly_clicked)
        top_bar_layout.addWidget(self.locations_readonly_button)

        self.onboarding_button = QPushButton("Guide de démarrage", top_bar)
        self.onboarding_button.setEnabled(self._permissions.has_permission("SETTINGS_VIEW"))
        self.onboarding_button.clicked.connect(self._open_onboarding_dialog)
        top_bar_layout.addWidget(self.onboarding_button)

        self.about_button = QPushButton("À propos", top_bar)
        self.about_button.clicked.connect(self._on_about_clicked)
        top_bar_layout.addWidget(self.about_button)

        self.change_password_button = QPushButton("Changer le mot de passe", top_bar)
        self.change_password_button.clicked.connect(self._on_change_password_clicked)
        top_bar_layout.addWidget(self.change_password_button)

        self.logout_button = QPushButton("Déconnexion", top_bar)
        self.logout_button.clicked.connect(self._on_logout_clicked)
        top_bar_layout.addWidget(self.logout_button)

        return top_bar

    def _on_navigation_changed(self, index: int) -> None:
        if index < 0:
            return
        # Hook optionnel (voir SalesPage.confirm_can_leave, lot « Écran de
        # caisse ») : une page peut refuser un changement de module si elle
        # contient une saisie non enregistrée — contrairement à un dialogue
        # modal, un écran intégré à la navigation comme la caisse n'empêche
        # pas nativement de cliquer ailleurs dans la liste de gauche. Sans
        # ce hook, cette saisie serait perdue silencieusement. Toute page
        # sans cette méthode continue de fonctionner à l'identique (hasattr).
        current_index = self.page_stack.currentIndex()
        if current_index >= 0:
            current_page = self.page_stack.widget(current_index)
            if hasattr(current_page, "confirm_can_leave") and not current_page.confirm_can_leave():
                self.navigation_list.blockSignals(True)
                self.navigation_list.setCurrentRow(current_index)
                self.navigation_list.blockSignals(False)
                return

        self.page_stack.setCurrentIndex(index)
        self.page_title_label.setText(self.visible_modules[index])
        # Chaque page n'est construite qu'une seule fois (voir
        # _build_content_area) et ne se rafraîchit sinon que sur ses propres
        # actions/filtres internes : sans cet appel, une page déjà ouverte
        # peut afficher des données obsolètes si elles ont changé depuis un
        # autre écran (ex. Créances après un paiement enregistré depuis
        # Ventes). PlaceholderPage n'expose pas de refresh() -> hasattr.
        page = self.page_stack.widget(index)
        if hasattr(page, "refresh"):
            page.refresh()

    def switch_to_module(self, module_name: str, report_preset: Optional[str] = None) -> bool:
        """Bascule vers un autre module de la navigation — utilisé par les
        accès rapides du Dashboard (§12 de la phase Dashboard). Retourne
        ``False`` sans rien faire si le module n'est pas visible pour
        l'utilisateur courant (jamais d'accès à un module non autorisé, même
        via ce raccourci — même filtrage que la navigation elle-même).
        ``report_preset``, si fourni et que la cible est « Rapports »,
        présélectionne le type de rapport correspondant (ex. « Stock
        faible »)."""
        if module_name not in self.visible_modules:
            return False
        index = self.visible_modules.index(module_name)
        self.navigation_list.setCurrentRow(index)
        if report_preset is not None and module_name == "Rapports":
            page = self.page_stack.widget(index)
            if isinstance(page, ReportsPage):
                page.select_report_type(report_preset)
        return True

    def _maybe_show_onboarding_dialog(self) -> None:
        """Ouvre le guide de démarrage automatiquement, une seule fois, à la
        première connexion réussie du compte administrateur initial (voir
        ``OnboardingService.should_show_automatically``). N'importe quel
        autre compte, y compris un second Administrateur, ne le déclenche
        jamais automatiquement — il reste réouvrable via le bouton dédié."""
        current_user = self._permissions.current_user
        if current_user is None:
            return
        if not self._services.onboarding.should_show_automatically(
            current_user.username, initial_admin_username=INITIAL_ADMIN_USERNAME
        ):
            return
        self._open_onboarding_dialog()

    def _open_onboarding_dialog(self) -> None:
        dialog = OnboardingDialog(
            company_settings_service=self._services.parameters,
            user_service=self._services.users,
            license_service=self._services.licenses,
            backup_service=self._services.backups,
            onboarding_service=self._services.onboarding,
            permission_service=self._permissions,
            on_navigate=self.switch_to_module,
            parent=self,
        )
        dialog.exec()

    def _on_open_locations_readonly_clicked(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Locations — consultation (lecture seule)")
        dialog.resize(1000, 650)
        layout = QVBoxLayout(dialog)

        page = LocationsPage(
            self._services.rentals, self._services.articles, self._services.clients, self._permissions,
            receipt_service=self._services.documents, parent=dialog, read_only=True,
        )
        layout.addWidget(page)

        close_button = QPushButton("Fermer", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    def _on_about_clicked(self) -> None:
        dialog = AboutDialog(self._services.licenses, self._permissions, parent=self)
        dialog.exec()

    def _on_change_password_clicked(self) -> None:
        dialog = ChangePasswordDialog(self._services.auth, parent=self)
        dialog.exec()

    def _on_logout_clicked(self) -> None:
        self._backup_scheduler_timer.stop()
        self._services.auth.logout()
        self.logout_requested.emit()
        self.close()

    def _check_scheduled_backup(self) -> None:
        """Sollicite le service de sauvegarde à intervalle régulier ; ne fait
        réellement quelque chose que si une sauvegarde automatique est
        activée et due (voir ``BackupService.run_scheduled_backup_if_due``).
        Échoue silencieusement en journal (jamais d'interruption de
        l'utilisateur pour une opération d'arrière-plan) : l'historique des
        sauvegardes et le journal d'audit restent la source de vérité."""
        try:
            result = self._services.backups.run_scheduled_backup_if_due()
        except Exception:  # défensif : ne doit jamais interrompre la session en cours
            logger.exception("Échec inattendu lors de la vérification de la sauvegarde planifiée.")
            return
        if result is None:
            return
        if result.success:
            logger.info("Sauvegarde automatique planifiée réussie : %s", result.file_path)
        else:
            logger.error("Sauvegarde automatique planifiée échouée : %s", result.message)
