"""Fenêtre principale et navigation de base.

Aucune logique métier ici : la fenêtre assemble des pages et gère le
changement de page sélectionnée. Le filtrage des pages selon les
permissions de l'utilisateur connecté sera ajouté dans une phase
ultérieure (Authentification et rôles), une fois AuthService/PermissionService
implémentés.
"""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.resources import APP_ICON_PATH
from app.views.pages.placeholder_page import PlaceholderPage

# Ordre de navigation conforme au cahier des charges (§22).
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


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        self.navigation_list.setCurrentRow(0)

        self.statusBar().showMessage("Prêt")

    def _build_navigation_list(self) -> QListWidget:
        navigation_list = QListWidget(self)
        navigation_list.setObjectName("navigationList")
        navigation_list.setFixedWidth(220)
        navigation_list.setIconSize(QSize(18, 18))
        for module_name in NAVIGATION_MODULES:
            QListWidgetItem(module_name, navigation_list)
        return navigation_list

    def _build_content_area(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget(container)
        top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(20, 14, 20, 14)
        self.page_title_label = QLabel(NAVIGATION_MODULES[0], top_bar)
        self.page_title_label.setObjectName("pageTitle")
        top_bar_layout.addWidget(self.page_title_label)
        top_bar_layout.addStretch(1)
        layout.addWidget(top_bar)

        self.page_stack = QStackedWidget(container)
        self.page_stack.setObjectName("pageContainer")
        for module_name in NAVIGATION_MODULES:
            self.page_stack.addWidget(PlaceholderPage(module_name))
        layout.addWidget(self.page_stack, stretch=1)

        return container

    def _on_navigation_changed(self, index: int) -> None:
        if index < 0:
            return
        self.page_stack.setCurrentIndex(index)
        self.page_title_label.setText(NAVIGATION_MODULES[index])
