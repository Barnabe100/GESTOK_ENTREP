"""Page d'administration des rôles et permissions (Lot C).

Consultation des 4 rôles système et modification de leurs permissions
uniquement — aucune création, suppression, désactivation ni renommage de
rôle, explicitement hors périmètre de cette V1 (voir
``app.services.roles.role_service``).

Toute action passe par :class:`RoleService`, qui revérifie la permission
côté service : le bouton « Modifier les permissions » est désactivé par
confort d'interface, mais ce n'est pas ce qui empêche un contournement — ni
ce qui protège le rôle Administrateur (cases à cocher grisées dans
``EditRolePermissionsDialog`` par confort visuel uniquement, la garantie
réelle vit dans ``RoleService.update_role_permissions``).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.roles.role_service import RoleService
from app.services.roles.role_summary import PermissionSummary
from app.utils.exceptions import AppError
from app.views.common import run_modal_form
from app.views.edit_role_permissions_dialog import EditRolePermissionsDialog

_COLUMNS = ["Rôle", "Description", "Utilisateurs actifs"]

_ROLE_ADMINISTRATEUR = "Administrateur"
# Purement pour l'affichage (verrouillage visuel des cases dans le panneau
# de consultation et dans EditRolePermissionsDialog) : la garantie réelle
# est appliquée par RoleService.update_role_permissions, jamais ici.
_ADMIN_PROTECTED_PERMISSIONS = frozenset({"ROLE_VIEW", "ROLE_UPDATE", "USER_VIEW", "USER_UPDATE"})

_EFFECT_NOTICE = "Les modifications des permissions prennent effet à la prochaine connexion de l'utilisateur."


class RolesPage(QWidget):
    def __init__(
        self,
        role_service: RoleService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._role_service = role_service
        self._permissions = permission_service
        self._all_permissions: list[PermissionSummary] = []
        self._selected_role_id: Optional[int] = None
        self._selected_role_nom: Optional[str] = None

        layout = QVBoxLayout(self)

        content = QHBoxLayout()

        left = QVBoxLayout()
        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        left.addWidget(self.table)
        content.addLayout(left, stretch=1)

        right = QVBoxLayout()
        self.role_title_label = QLabel("Sélectionnez un rôle pour consulter ses permissions.", self)
        self.role_title_label.setWordWrap(True)
        right.addWidget(self.role_title_label)

        self.permissions_scroll = QScrollArea(self)
        self.permissions_scroll.setWidgetResizable(True)
        self._permissions_container = QWidget()
        self._permissions_layout = QVBoxLayout(self._permissions_container)
        self.permissions_scroll.setWidget(self._permissions_container)
        right.addWidget(self.permissions_scroll, stretch=1)

        self.edit_button = QPushButton("Modifier les permissions", self)
        self.edit_button.setEnabled(False)
        right.addWidget(self.edit_button)

        content.addLayout(right, stretch=1)
        layout.addLayout(content, stretch=1)

        self.notice_label = QLabel(_EFFECT_NOTICE, self)
        self.notice_label.setWordWrap(True)
        layout.addWidget(self.notice_label)

        self.table.itemSelectionChanged.connect(self._on_role_selection_changed)
        self.edit_button.clicked.connect(self._on_edit_clicked)

        self.refresh()

    # -- rafraîchissement -----------------------------------------------------

    def refresh(self) -> None:
        try:
            self._all_permissions = self._role_service.list_permissions()
            roles = self._role_service.list_roles()
        except AppError:
            self.table.setRowCount(0)
            self._selected_role_id = None
            self._selected_role_nom = None
            self._clear_permissions_panel()
            self.edit_button.setEnabled(False)
            return

        previously_selected_id = self._selected_role_id

        self.table.setRowCount(len(roles))
        for row, role in enumerate(roles):
            nom_item = QTableWidgetItem(role.nom)
            nom_item.setData(Qt.ItemDataRole.UserRole, role.id)
            self.table.setItem(row, 0, nom_item)
            self.table.setItem(row, 1, QTableWidgetItem(role.description or "—"))
            self.table.setItem(row, 2, QTableWidgetItem(str(role.nombre_utilisateurs_actifs)))

        if previously_selected_id is not None:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == previously_selected_id:
                    self.table.selectRow(row)
                    return

        self._selected_role_id = None
        self._selected_role_nom = None
        self._clear_permissions_panel()
        self.edit_button.setEnabled(False)

    def _clear_permissions_panel(self) -> None:
        while self._permissions_layout.count():
            item = self._permissions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.role_title_label.setText("Sélectionnez un rôle pour consulter ses permissions.")

    # -- sélection / consultation -------------------------------------------------

    def _on_role_selection_changed(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            self._selected_role_id = None
            self._selected_role_nom = None
            self._clear_permissions_panel()
            self.edit_button.setEnabled(False)
            return

        row = selected[0].row()
        role_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        role_nom = self.table.item(row, 0).text()

        try:
            current_codes = set(self._role_service.get_role_permissions(role_id))
        except AppError as exc:
            QMessageBox.warning(self, "Consultation refusée", str(exc))
            return

        self._selected_role_id = role_id
        self._selected_role_nom = role_nom
        self._render_permissions_panel(role_nom, current_codes)
        self.edit_button.setEnabled(self._permissions.has_permission("ROLE_UPDATE"))

    def _render_permissions_panel(self, role_nom: str, current_codes: set[str]) -> None:
        self._clear_permissions_panel()
        self.role_title_label.setText(f"Permissions du rôle « {role_nom} »")

        protected_codes = _ADMIN_PROTECTED_PERMISSIONS if role_nom == _ROLE_ADMINISTRATEUR else frozenset()

        modules: dict[str, list[PermissionSummary]] = {}
        for permission in self._all_permissions:
            modules.setdefault(permission.module, []).append(permission)

        for module in sorted(modules):
            group = QGroupBox(module, self._permissions_container)
            group_layout = QVBoxLayout(group)
            for permission in modules[module]:
                is_protected = permission.code in protected_codes
                label = permission.libelle + (" (protégée)" if is_protected else "")
                checkbox = QCheckBox(label, group)
                checkbox.setChecked(permission.code in current_codes)
                # Panneau de consultation : jamais éditable directement, que
                # la permission soit protégée ou non — l'édition passe
                # exclusivement par EditRolePermissionsDialog.
                checkbox.setEnabled(False)
                group_layout.addWidget(checkbox)
            self._permissions_layout.addWidget(group)
        self._permissions_layout.addStretch(1)

    # -- édition ------------------------------------------------------------------

    def _on_edit_clicked(self) -> None:
        role_id = self._selected_role_id
        role_nom = self._selected_role_nom
        if role_id is None or role_nom is None:
            return

        try:
            current_codes = set(self._role_service.get_role_permissions(role_id))
        except AppError as exc:
            QMessageBox.warning(self, "Consultation refusée", str(exc))
            return

        protected_codes = _ADMIN_PROTECTED_PERMISSIONS if role_nom == _ROLE_ADMINISTRATEUR else frozenset()

        def factory() -> EditRolePermissionsDialog:
            return EditRolePermissionsDialog(
                role_nom, self._all_permissions, current_codes, protected_codes, parent=self
            )

        def submit(dialog: EditRolePermissionsDialog) -> bool:
            return self._submit_update_permissions(role_id, dialog.selected_codes())

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_update_permissions(self, role_id: int, codes: list[str]) -> bool:
        """Effectue l'appel service et affiche le résultat. Isolé de
        ``_on_edit_clicked`` pour rester testable sans dialogue modal."""
        try:
            self._role_service.update_role_permissions(role_id, codes)
            QMessageBox.information(
                self,
                "Permissions mises à jour",
                "Les permissions du rôle ont été mises à jour. " + _EFFECT_NOTICE,
            )
        except AppError as exc:
            QMessageBox.warning(self, "Modification refusée", str(exc))
            return False
        return True
