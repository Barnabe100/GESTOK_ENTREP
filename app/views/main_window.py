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

from PySide6.QtCore import QSize, Signal
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
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.services.categories.category_service import CategoryService
from app.services.users.user_service import UserService
from app.views.change_password_dialog import ChangePasswordDialog
from app.views.pages.categories_page import CategoriesPage
from app.views.pages.placeholder_page import PlaceholderPage
from app.views.pages.users_page import UsersPage

# Ordre de navigation conforme au cahier des charges (§22), et permission
# de consultation requise pour que chaque module apparaisse dans le menu.
NAVIGATION_MODULES: list[str] = [
    "Dashboard",
    "Articles",
    "Catégories",
    "Fournisseurs",
    "Entrées",
    "Sorties",
    "Ventes",
    "Mouvements",
    "Inventaires",
    "Rapports",
    "Utilisateurs",
    "Paramètres",
]

NAVIGATION_PERMISSIONS: dict[str, str] = {
    "Dashboard": "DASHBOARD_VIEW",
    "Articles": "ARTICLE_VIEW",
    "Catégories": "CATEGORY_VIEW",
    "Fournisseurs": "SUPPLIER_VIEW",
    "Entrées": "STOCK_ENTRY_VIEW",
    "Sorties": "STOCK_EXIT_VIEW",
    "Ventes": "SALE_VIEW",
    "Mouvements": "STOCK_MOVEMENT_VIEW",
    "Inventaires": "INVENTORY_VIEW",
    "Rapports": "REPORT_VIEW",
    "Utilisateurs": "USER_VIEW",
    "Paramètres": "SETTINGS_VIEW",
}


class MainWindow(QMainWindow):
    logout_requested = Signal()

    def __init__(
        self,
        auth_service: AuthService,
        permission_service: PermissionService,
        user_service: UserService,
        category_service: CategoryService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._auth_service = auth_service
        self._permissions = permission_service
        self._user_service = user_service
        self._category_service = category_service

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

        self.statusBar().showMessage("Prêt")

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
        if module_name == "Utilisateurs":
            return UsersPage(self._user_service, self._permissions)
        if module_name == "Catégories":
            return CategoriesPage(self._category_service, self._permissions)
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

    def _on_change_password_clicked(self) -> None:
        dialog = ChangePasswordDialog(self._auth_service, parent=self)
        dialog.exec()

    def _on_logout_clicked(self) -> None:
        self._auth_service.logout()
        self.logout_requested.emit()
        self.close()
