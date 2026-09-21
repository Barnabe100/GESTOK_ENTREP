"""Formulaire de modification des rôles d'un utilisateur existant.

Ne connaît rien du service métier : collecte uniquement les rôles choisis
(liste fournie par l'appelant, ``UsersPage``, qui appelle seul
``UserService`` et gère la validation métier — même principe que
:class:`app.views.create_user_dialog.CreateUserDialog`). Ne permet pas de
modifier le nom d'utilisateur (identifiant de connexion) ni le mot de
passe : cette opération est strictement limitée aux rôles.

Un utilisateur peut avoir plusieurs rôles (§6 du lot multi-rôles) : une
case à cocher par rôle, pré-cochée selon les rôles actuels de
l'utilisateur — si l'administrateur ne touche à aucune case, les mêmes
rôles sont retransmis tels quels à ``UserService.update_user`` (aucun
changement effectif), ce qui satisfait naturellement l'exigence « conserver
les rôles existants si non modifiés » sans logique dédiée."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.views.common import build_required_field_legend, required_label


class EditUserDialog(QDialog):
    def __init__(
        self,
        roles: list[tuple[int, str]],
        current_role_ids: list[int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modifier les rôles de l'utilisateur")
        self.setModal(True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        current_role_ids_set = set(current_role_ids)
        roles_group = QGroupBox(required_label("Rôle(s)"), self)
        roles_layout = QVBoxLayout(roles_group)
        self._role_checkboxes: list[tuple[int, QCheckBox]] = []
        for role_id, role_name in roles:
            checkbox = QCheckBox(role_name, roles_group)
            checkbox.setChecked(role_id in current_role_ids_set)
            roles_layout.addWidget(checkbox)
            self._role_checkboxes.append((role_id, checkbox))
        layout.addWidget(roles_group)

        layout.addWidget(build_required_field_legend(self))

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Enregistrer", self)
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._on_save_clicked)

    def _on_save_clicked(self) -> None:
        if not self.role_ids():
            self.error_label.setText("Veuillez sélectionner au moins un rôle.")
            return
        self.accept()

    def role_ids(self) -> list[int]:
        return [role_id for role_id, checkbox in self._role_checkboxes if checkbox.isChecked()]

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
