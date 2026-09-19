"""Dialogue de réinitialisation administrative du mot de passe d'un
utilisateur.

Contrairement à :class:`app.views.change_password_dialog.ChangePasswordDialog`
(qui change le mot de passe de l'utilisateur connecté lui-même et appelle
directement ``AuthService.change_password``), ce dialogue ne fait que
collecter et valider la saisie (correspondance des deux champs) : c'est
``UsersPage`` qui appelle ``UserService.reset_password`` — la personne qui
effectue la réinitialisation n'est pas le titulaire du compte concerné, il
n'y a donc pas d'ancien mot de passe à demander ici. La longueur minimale
reste validée côté service, jamais dupliquée dans la vue.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ResetPasswordDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Réinitialiser le mot de passe")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_edit = QLineEdit(self)
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Nouveau mot de passe", self.password_edit)
        form.addRow("Confirmer le nouveau mot de passe", self.confirm_password_edit)
        layout.addLayout(form)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.submit_button = QPushButton("Réinitialiser", self)
        self.submit_button.setDefault(True)
        layout.addWidget(self.submit_button)

        self.submit_button.clicked.connect(self._on_submit)

    def _on_submit(self) -> None:
        if self.password_edit.text() != self.confirm_password_edit.text():
            self.error_label.setText("Les deux mots de passe ne correspondent pas.")
            return
        self.accept()

    def password(self) -> str:
        return self.password_edit.text()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
