"""Formulaire de création d'un utilisateur.

Ne connaît rien du service métier : collecte uniquement une saisie (la
liste des rôles proposés est fournie par l'appelant, ``UsersPage``, qui
appelle seul ``UserService`` et gère la validation métier — même principe
que :class:`app.views.category_form_dialog.CategoryFormDialog`).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.views.common import build_required_field_legend, required_label


class CreateUserDialog(QDialog):
    def __init__(
        self, roles: list[tuple[int, str]], initial_username: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouvel utilisateur")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.username_edit = QLineEdit(self)
        self.username_edit.setText(initial_username)
        form.addRow(required_label("Nom d'utilisateur"), self.username_edit)

        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(required_label("Mot de passe"), self.password_edit)

        self.confirm_password_edit = QLineEdit(self)
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(required_label("Confirmer le mot de passe"), self.confirm_password_edit)

        self.role_combo = QComboBox(self)
        for role_id, role_name in roles:
            self.role_combo.addItem(role_name, role_id)
        form.addRow(required_label("Rôle"), self.role_combo)

        self.active_checkbox = QCheckBox("Compte actif", self)
        self.active_checkbox.setChecked(True)
        form.addRow(self.active_checkbox)

        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Créer", self)
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._on_save_clicked)

    def _on_save_clicked(self) -> None:
        if self.password_edit.text() != self.confirm_password_edit.text():
            self.error_label.setText("Les deux mots de passe ne correspondent pas.")
            return
        self.accept()

    def username(self) -> str:
        return self.username_edit.text()

    def password(self) -> str:
        return self.password_edit.text()

    def role_id(self) -> Optional[int]:
        return self.role_combo.currentData()

    def is_active(self) -> bool:
        return self.active_checkbox.isChecked()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
