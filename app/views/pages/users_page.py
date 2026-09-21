"""Page de gestion des comptes utilisateurs (consultation + création +
activation/désactivation).

Toute action passe par :class:`UserService`, qui revérifie la permission
côté service : le bouton est désactivé par confort d'interface, mais ce
n'est pas ce qui empêche un contournement.
"""
from __future__ import annotations

from typing import Optional

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
from app.utils.exceptions import AppError, ValidationError
from app.views.common import confirm_action, run_modal_form
from app.views.create_user_dialog import CreateUserDialog
from app.views.edit_user_dialog import EditUserDialog
from app.views.reset_password_dialog import ResetPasswordDialog

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
        self.add_button = QPushButton("Ajouter un utilisateur", self)
        self.add_button.setEnabled(self._permissions.has_permission("USER_CREATE"))
        button_row.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        self.edit_button.setEnabled(self._permissions.has_permission("USER_UPDATE"))
        button_row.addWidget(self.edit_button)

        self.reset_password_button = QPushButton("Réinitialiser le mot de passe", self)
        self.reset_password_button.setEnabled(self._permissions.has_permission("USER_RESET_PASSWORD"))
        button_row.addWidget(self.reset_password_button)

        self.toggle_button = QPushButton("Activer / désactiver le compte sélectionné", self)
        self.toggle_button.setEnabled(self._permissions.has_permission("USER_ACTIVATE"))
        button_row.addWidget(self.toggle_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.reset_password_button.clicked.connect(self._on_reset_password_clicked)
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

    # -- création --------------------------------------------------------------

    def _on_add_clicked(self) -> None:
        try:
            roles = [(role.id, role.nom) for role in self._user_service.list_roles()]
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return
        if not roles:
            QMessageBox.warning(self, "Aucun rôle disponible", "Aucun rôle n'est configuré.")
            return

        # Conserve le nom d'utilisateur saisi d'une tentative à l'autre (ex.
        # nom déjà utilisé) — le mot de passe n'est volontairement pas
        # reporté, à ressaisir à chaque tentative.
        state = {"username": ""}

        def factory() -> CreateUserDialog:
            return CreateUserDialog(roles, initial_username=state["username"], parent=self)

        def submit(dialog: CreateUserDialog) -> bool:
            state["username"] = dialog.username()
            return self._submit_create_user(
                dialog.username(), dialog.password(), dialog.role_id(), dialog.is_active()
            )

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_create_user(
        self, username: str, password: str, role_id: Optional[int], actif: bool
    ) -> bool:
        """Effectue l'appel service et affiche le résultat. Isolé de
        ``_on_add_clicked`` pour rester testable sans dialogue modal."""
        try:
            if role_id is None:
                raise ValidationError("Veuillez sélectionner un rôle.")
            self._user_service.create_user(username, password, role_id, actif=actif)
            QMessageBox.information(self, "Utilisateur créé", f"Le compte « {username} » a été créé.")
        except AppError as exc:
            QMessageBox.warning(self, "Création refusée", str(exc))
            return False
        return True

    # -- modification du rôle ---------------------------------------------------

    def _on_edit_clicked(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        row = selected[0].row()
        user_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        current_role_name = self.table.item(row, 1).text()

        try:
            roles = [(role.id, role.nom) for role in self._user_service.list_roles()]
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return
        if not roles:
            QMessageBox.warning(self, "Aucun rôle disponible", "Aucun rôle n'est configuré.")
            return
        current_role_id = next(
            (role_id for role_id, role_name in roles if role_name == current_role_name), roles[0][0]
        )

        def factory() -> EditUserDialog:
            return EditUserDialog(roles, current_role_id, parent=self)

        def submit(dialog: EditUserDialog) -> bool:
            return self._submit_update_user(user_id, dialog.role_id())

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_update_user(self, user_id: int, role_id: Optional[int]) -> bool:
        """Effectue l'appel service et affiche le résultat. Isolé de
        ``_on_edit_clicked`` pour rester testable sans dialogue modal."""
        try:
            if role_id is None:
                raise ValidationError("Veuillez sélectionner un rôle.")
            self._user_service.update_user(user_id, role_id)
            QMessageBox.information(self, "Rôle modifié", "Le rôle de l'utilisateur a été mis à jour.")
        except AppError as exc:
            QMessageBox.warning(self, "Modification refusée", str(exc))
            return False
        return True

    # -- réinitialisation du mot de passe -----------------------------------------

    def _on_reset_password_clicked(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        row = selected[0].row()
        user_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        username = self.table.item(row, 0).text()

        if not confirm_action(
            self,
            "Réinitialiser le mot de passe",
            f"Réinitialiser le mot de passe de « {username} » ? "
            "Ce compte devra en choisir un nouveau à sa prochaine connexion.",
        ):
            return

        def factory() -> ResetPasswordDialog:
            return ResetPasswordDialog(parent=self)

        def submit(dialog: ResetPasswordDialog) -> bool:
            return self._submit_reset_password(user_id, dialog.password())

        run_modal_form(factory, submit)

    def _submit_reset_password(self, user_id: int, new_password: str) -> bool:
        """Effectue l'appel service et affiche le résultat. Isolé de
        ``_on_reset_password_clicked`` pour rester testable sans dialogue modal."""
        try:
            self._user_service.reset_password(user_id, new_password)
            QMessageBox.information(
                self, "Mot de passe réinitialisé", "Le mot de passe a été réinitialisé."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Réinitialisation refusée", str(exc))
            return False
        return True

    # -- activation / désactivation ----------------------------------------------

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
