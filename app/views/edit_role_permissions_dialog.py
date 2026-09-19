"""Formulaire d'édition des permissions d'un rôle.

Ne connaît rien du service métier : collecte uniquement l'ensemble des
codes de permission cochés (la liste des permissions disponibles et les
codes actuellement associés au rôle sont fournis par l'appelant,
``RolesPage``, qui appelle seul ``RoleService`` et gère la validation
métier — même principe que :class:`app.views.create_user_dialog.CreateUserDialog`).

Les cases correspondant aux permissions protégées du rôle Administrateur
sont affichées cochées et désactivées, par confort d'interface — cela
n'est qu'un confort visuel : la garantie réelle que ces permissions ne
peuvent jamais être retirées est appliquée côté ``RoleService``
(``update_role_permissions``), jamais ici.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services.roles.role_summary import PermissionSummary


class EditRolePermissionsDialog(QDialog):
    def __init__(
        self,
        role_nom: str,
        permissions: list[PermissionSummary],
        current_codes: set[str],
        protected_codes: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Permissions du rôle « {role_nom} »")
        self.setModal(True)
        self.setMinimumSize(480, 560)

        self._checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        if protected_codes:
            notice = QLabel(
                "Les permissions marquées (protégée) sont nécessaires à l'administration "
                "du système et ne peuvent pas être retirées au rôle Administrateur.",
                self,
            )
            notice.setWordWrap(True)
            layout.addWidget(notice)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        modules: dict[str, list[PermissionSummary]] = {}
        for permission in permissions:
            modules.setdefault(permission.module, []).append(permission)

        for module in sorted(modules):
            group = QGroupBox(module, scroll_content)
            group_layout = QVBoxLayout(group)
            for permission in modules[module]:
                is_protected = permission.code in protected_codes
                label = permission.libelle + (" (protégée)" if is_protected else "")
                checkbox = QCheckBox(label, group)
                checkbox.setChecked(permission.code in current_codes or is_protected)
                checkbox.setEnabled(not is_protected)
                group_layout.addWidget(checkbox)
                self._checkboxes[permission.code] = checkbox
            scroll_layout.addWidget(group)

        scroll_layout.addStretch(1)
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area, stretch=1)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        effect_notice = QLabel(
            "Les modifications des permissions prennent effet à la prochaine connexion de l'utilisateur.",
            self,
        )
        effect_notice.setWordWrap(True)
        layout.addWidget(effect_notice)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Enregistrer", self)
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def selected_codes(self) -> list[str]:
        return [code for code, checkbox in self._checkboxes.items() if checkbox.isChecked()]

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
