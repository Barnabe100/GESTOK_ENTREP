"""Page de gestion des comptes utilisateurs (consultation + activation/désactivation).

Toute action passe par :class:`UserService`, qui revérifie la permission
côté service : le bouton est désactivé par confort d'interface, mais ce
n'est pas ce qui empêche un contournement.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.users.user_service import UserService
from app.utils.exceptions import AppError

_COLUMNS = ["Utilisateur", "Rôle", "Statut", "Dernière connexion"]


class UsersPage(QWidget):
    def __init__(
        self,
        user_service: UserService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._user_service = user_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.toggle_button = QPushButton("Activer / désactiver le compte sélectionné", self)
        self.toggle_button.setEnabled(self._permissions.has_permission("USER_ACTIVATE"))
        button_row.addWidget(self.toggle_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.toggle_button.clicked.connect(self._on_toggle_clicked)

        self.refresh()

    def refresh(self) -> None:
        try:
            users = self._user_service.list_users()
        except AppError:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(users))
        for row, user in enumerate(users):
            username_item = QTableWidgetItem(user.username)
            username_item.setData(Qt.ItemDataRole.UserRole, user.id)
            self.table.setItem(row, 0, username_item)
            self.table.setItem(row, 1, QTableWidgetItem(user.role_name))
            self.table.setItem(row, 2, QTableWidgetItem("Actif" if user.actif else "Inactif"))
            last_login = (
                user.dernier_login.strftime("%Y-%m-%d %H:%M") if user.dernier_login else "—"
            )
            self.table.setItem(row, 3, QTableWidgetItem(last_login))

    def _on_toggle_clicked(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        row = selected[0].row()
        user_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        currently_active = self.table.item(row, 2).text() == "Actif"

        try:
            self._user_service.set_active(user_id, not currently_active)
        except AppError as exc:
            QMessageBox.warning(self, "Action refusée", str(exc))
            return

        self.refresh()
