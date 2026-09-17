"""Page de gestion des catégories.

Toute action (création, modification, activation/désactivation) passe par
:class:`CategoryService`, qui revérifie la permission côté service. Les
boutons sont activés/désactivés selon les permissions par confort d'usage
uniquement — ce n'est jamais ce qui empêche un contournement.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.categories.category_service import CategoryService
from app.utils.exceptions import AppError
from app.views.category_form_dialog import CategoryFormDialog
from app.views.common import confirm_action, run_modal_form

_COLUMNS = ["Nom", "Statut", "Créée le", "Modifiée le"]


class CategoriesPage(QWidget):
    def __init__(
        self,
        category_service: CategoryService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._category_service = category_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher une catégorie…")
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)

        self.add_button = QPushButton("Ajouter", self)
        self.add_button.setEnabled(self._permissions.has_permission("CATEGORY_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        self.edit_button.setEnabled(self._permissions.has_permission("CATEGORY_UPDATE"))
        toolbar.addWidget(self.edit_button)

        self.toggle_button = QPushButton("Activer / désactiver", self)
        self.toggle_button.setEnabled(
            self._permissions.has_permission("CATEGORY_ACTIVATE")
            or self._permissions.has_permission("CATEGORY_DEACTIVATE")
        )
        toolbar.addWidget(self.toggle_button)

        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.search_edit.textChanged.connect(self.refresh)
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.toggle_button.clicked.connect(self._on_toggle_clicked)

        self.refresh()

    # -- affichage ---------------------------------------------------------

    def refresh(self) -> None:
        try:
            categories = self._category_service.list_categories(search=self.search_edit.text())
        except AppError:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(categories))
        for row, category in enumerate(categories):
            name_item = QTableWidgetItem(category.nom)
            name_item.setData(Qt.ItemDataRole.UserRole, category.id)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem("Actif" if category.actif else "Inactif"))
            self.table.setItem(row, 2, QTableWidgetItem(category.date_creation.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 3, QTableWidgetItem(category.date_modification.strftime("%Y-%m-%d %H:%M")))

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        self._open_form(category_id=None, initial_name="")

    def _on_edit_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        category_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        current_name = self.table.item(row, 0).text()
        self._open_form(category_id=category_id, initial_name=current_name)

    def _open_form(self, category_id: Optional[int], initial_name: str) -> None:
        state = {"name": initial_name}

        def factory() -> CategoryFormDialog:
            return CategoryFormDialog(state["name"], parent=self)

        def submit(dialog: CategoryFormDialog) -> bool:
            state["name"] = dialog.name()
            return self._submit_form(category_id, state["name"])

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_form(self, category_id: Optional[int], name: str) -> bool:
        """Effectue l'appel service et affiche le résultat. Isolé de
        ``_open_form_dialog`` pour rester testable sans dialogue modal."""
        try:
            if category_id is None:
                self._category_service.create_category(name)
                QMessageBox.information(self, "Catégorie créée", f"La catégorie « {name} » a été créée.")
            else:
                self._category_service.update_category(category_id, name)
                QMessageBox.information(
                    self, "Catégorie modifiée", f"La catégorie « {name} » a été modifiée."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- activation / désactivation -----------------------------------------

    def _on_toggle_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            return

        category_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        name = self.table.item(row, 0).text()
        currently_active = self.table.item(row, 1).text() == "Actif"
        action_label = "désactiver" if currently_active else "activer"

        if not confirm_action(
            self, "Confirmation", f"Voulez-vous vraiment {action_label} la catégorie « {name} » ?"
        ):
            return

        if self._toggle_status(category_id, currently_active):
            self.refresh()

    def _toggle_status(self, category_id: int, currently_active: bool) -> bool:
        """Effectue le changement de statut. Isolé de ``_on_toggle_clicked``
        pour rester testable sans boîte de confirmation modale."""
        try:
            if currently_active:
                updated = self._category_service.deactivate_category(category_id)
                QMessageBox.information(
                    self, "Catégorie désactivée", f"La catégorie « {updated.nom} » a été désactivée."
                )
            else:
                updated = self._category_service.activate_category(category_id)
                QMessageBox.information(
                    self, "Catégorie activée", f"La catégorie « {updated.nom} » a été activée."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True
