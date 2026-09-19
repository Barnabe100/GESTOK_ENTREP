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

from app.resources import APP_ICON_PATH
from app.services.registry import ServiceRegistry
from app.utils.logging_config import get_logger
from app.version import __version__
from app.views.about_dialog import AboutDialog
from app.views.change_password_dialog import ChangePasswordDialog
from app.views.pages.articles_page import ArticlesPage
from app.views.pages.audit_page import AuditPage
from app.views.pages.backups_page import BackupsPage
from app.views.pages.categories_page import CategoriesPage
from app.views.pages.clients_page import ClientsPage
from app.views.pages.dashboard_page import DashboardPage
from app.views.pages.entries_page import EntriesPage
from app.views.pages.exit_reasons_page import ExitReasonsPage
from app.views.pages.exits_page import ExitsPage
from app.views.pages.inventories_page import InventoriesPage
from app.views.pages.licenses_page import LicensesPage
from app.views.pages.mouvements_page import MouvementsPage
from app.views.pages.placeholder_page import PlaceholderPage
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
    "Mouvements",
    "Inventaires",
    "Rapports",
    "Utilisateurs",
    "Rôles",
    "Paramètres",
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
    "Mouvements": "STOCK_MOVEMENT_VIEW",
    "Inventaires": "INVENTORY_VIEW",
    "Rapports": "REPORT_VIEW",
    "Utilisateurs": "USER_VIEW",
    "Rôles": "ROLE_VIEW",
    "Paramètres": "SETTINGS_VIEW",
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

        self.visible_modules: list[str] = [
            module
            for module in NAVIGATION_MODULES
            if self._permissions.has_permission(NAVIGATION_PERMISSIONS[module])
        ]

        self.setWindowTitle("StockManager Desktop")
        self.resize(1200, 750)

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
                self._services.articles, self._services.categories, self._services.suppliers, self._permissions
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
            return SettingsPage(self._services.parameters, self._permissions)
        if module_name == "Sauvegardes":
            return BackupsPage(self._services.backups, self._permissions)
        if module_name == "Audit":
            return AuditPage(self._services.audit, self._permissions)
        if module_name == "Licences":
            return LicensesPage(self._services.licenses, self._permissions)
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
            f"{current_user.username} ({current_user.role_name})" if current_user else ""
        )
        self.user_label = QLabel(user_text, top_bar)
        top_bar_layout.addWidget(self.user_label)

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
        self.page_stack.setCurrentIndex(index)
        self.page_title_label.setText(self.visible_modules[index])

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
