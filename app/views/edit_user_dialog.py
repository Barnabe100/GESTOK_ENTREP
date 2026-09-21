"""Formulaire de modification du rôle d'un utilisateur existant.

Ne connaît rien du service métier : collecte uniquement le nouveau rôle
choisi (liste fournie par l'appelant, ``UsersPage``, qui appelle seul
``UserService`` et gère la validation métier — même principe que
:class:`app.views.create_user_dialog.CreateUserDialog`). Ne permet pas de
modifier le nom d'utilisateur (identifiant de connexion) ni le mot de
passe : cette opération est strictement limitée au changement de rôle.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
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
        current_role_id: Optional[int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modifier le rôle de l'utilisateur")
        self.setModal(True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.role_combo = QComboBox(self)
        for role_id, role_name in roles:
            self.role_combo.addItem(role_name, role_id)
        index = self.role_combo.findData(current_role_id)
        if index >= 0:
            self.role_combo.setCurrentIndex(index)
        form.addRow(required_label("Rôle"), self.role_combo)
        layout.addLayout(form)

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
        self.save_button.clicked.connect(self.accept)

    def role_id(self) -> Optional[int]:
        return self.role_combo.currentData()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
