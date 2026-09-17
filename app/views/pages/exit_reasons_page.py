"""Page de gestion des motifs de sortie.

Mêmes conventions visuelles et le même comportement que ``CategoriesPage``/
``SuppliersPage`` (tableau, recherche, boutons Ajouter/Modifier/Activer-
désactiver, confirmation avant opération sensible, messages d'erreur/succès).
Toute action passe par :class:`ExitReasonService`, qui revérifie la
permission côté service — les boutons ne sont désactivés que par confort
d'usage. En pratique, seul l'Administrateur dispose des permissions
``STOCK_REASON_*`` (décision métier de cette phase).
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
from app.services.exit_reasons.exit_reason_service import ExitReasonService
from app.utils.exceptions import AppError
from app.views.common import confirm_action, run_modal_form
from app.views.exit_reason_form_dialog import ExitReasonFormDialog

_COLUMNS = ["Libellé", "Description", "Statut", "Créé le", "Modifié le"]


class ExitReasonsPage(QWidget):
    def __init__(
        self,
        exit_reason_service: ExitReasonService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._exit_reason_service = exit_reason_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher un motif…")
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)

        self.add_button = QPushButton("Ajouter", self)
        self.add_button.setEnabled(self._permissions.has_permission("STOCK_REASON_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        self.edit_button.setEnabled(self._permissions.has_permission("STOCK_REASON_UPDATE"))
        toolbar.addWidget(self.edit_button)

        self.toggle_button = QPushButton("Activer / désactiver", self)
        self.toggle_button.setEnabled(
            self._permissions.has_permission("STOCK_REASON_ACTIVATE")
            or self._permissions.has_permission("STOCK_REASON_DEACTIVATE")
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
            reasons = self._exit_reason_service.list_exit_reasons(search=self.search_edit.text())
        except AppError:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(reasons))
        for row, reason in enumerate(reasons):
            label_item = QTableWidgetItem(reason.libelle)
            label_item.setData(Qt.ItemDataRole.UserRole, reason.id)
            self.table.setItem(row, 0, label_item)
            self.table.setItem(row, 1, QTableWidgetItem(reason.description or ""))
            self.table.setItem(row, 2, QTableWidgetItem("Actif" if reason.actif else "Inactif"))
            self.table.setItem(row, 3, QTableWidgetItem(reason.date_creation.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 4, QTableWidgetItem(reason.date_modification.strftime("%Y-%m-%d %H:%M")))

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        self._open_form(reason_id=None, initial_libelle="", initial_description="")

    def _on_edit_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        reason_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        initial_libelle = self.table.item(row, 0).text()
        initial_description = self.table.item(row, 1).text()
        self._open_form(reason_id=reason_id, initial_libelle=initial_libelle, initial_description=initial_description)

    def _open_form(self, reason_id: Optional[int], initial_libelle: str, initial_description: str) -> None:
        state = {"libelle": initial_libelle, "description": initial_description}

        def factory() -> ExitReasonFormDialog:
            return ExitReasonFormDialog(state["libelle"], state["description"], parent=self)

        def submit(dialog: ExitReasonFormDialog) -> bool:
            state["libelle"] = dialog.libelle()
            state["description"] = dialog.description()
            return self._submit_form(reason_id, state["libelle"], state["description"])

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_form(self, reason_id: Optional[int], libelle: str, description: str) -> bool:
        """Effectue l'appel service et affiche le résultat. Isolé de
        ``_open_form`` pour rester testable sans dialogue modal."""
        try:
            if reason_id is None:
                self._exit_reason_service.create_exit_reason(libelle, description)
                QMessageBox.information(self, "Motif créé", f"Le motif « {libelle} » a été créé.")
            else:
                self._exit_reason_service.update_exit_reason(reason_id, libelle, description)
                QMessageBox.information(self, "Motif modifié", f"Le motif « {libelle} » a été modifié.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- activation / désactivation -----------------------------------------

    def _on_toggle_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            return

        reason_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        libelle = self.table.item(row, 0).text()
        currently_active = self.table.item(row, 2).text() == "Actif"
        action_label = "désactiver" if currently_active else "activer"

        if not confirm_action(
            self, "Confirmation", f"Voulez-vous vraiment {action_label} le motif « {libelle} » ?"
        ):
            return

        if self._toggle_status(reason_id, currently_active):
            self.refresh()

    def _toggle_status(self, reason_id: int, currently_active: bool) -> bool:
        """Effectue le changement de statut. Isolé de ``_on_toggle_clicked``
        pour rester testable sans boîte de confirmation modale."""
        try:
            if currently_active:
                updated = self._exit_reason_service.deactivate_exit_reason(reason_id)
                QMessageBox.information(self, "Motif désactivé", f"Le motif « {updated.libelle} » a été désactivé.")
            else:
                updated = self._exit_reason_service.activate_exit_reason(reason_id)
                QMessageBox.information(self, "Motif activé", f"Le motif « {updated.libelle} » a été activé.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True
