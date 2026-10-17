"""Dialogue de récupération du mot de passe administrateur par code à usage
unique, accessible depuis l'écran de connexion (avant toute authentification
— voir :class:`app.services.auth.account_recovery_service.AccountRecoveryService`).

Collecte uniquement la saisie, comme :class:`app.views.create_user_dialog.CreateUserDialog` :
la vérification du code et le changement effectif du mot de passe restent
entièrement du côté du service, jamais dupliqués ici. Le code est traité
comme un second secret, au même titre que le mot de passe : saisi via
:class:`app.views.password_line_edit.PasswordLineEdit`, jamais conservé
d'une tentative à l'autre en cas d'échec."""
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

from app.views.common import build_required_field_legend, required_label
from app.views.password_line_edit import PasswordLineEdit


class AccountRecoveryDialog(QDialog):
    def __init__(self, initial_username: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Récupérer l'accès administrateur")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        notice = QLabel(
            "Saisissez votre identifiant, le code de récupération généré "
            "depuis les Paramètres, puis votre nouveau mot de passe.",
            self,
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        form = QFormLayout()
        self.username_edit = QLineEdit(self)
        self.username_edit.setText(initial_username)
        form.addRow(required_label("Identifiant"), self.username_edit)

        self.code_edit = PasswordLineEdit(self)
        form.addRow(required_label("Code de récupération"), self.code_edit)

        self.new_password_edit = PasswordLineEdit(self)
        form.addRow(required_label("Nouveau mot de passe"), self.new_password_edit)

        self.confirm_password_edit = PasswordLineEdit(self)
        form.addRow(required_label("Confirmer le nouveau mot de passe"), self.confirm_password_edit)

        layout.addLayout(form)
        layout.addWidget(build_required_field_legend(self))

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.submit_button = QPushButton("Réinitialiser le mot de passe", self)
        self.submit_button.setDefault(True)
        layout.addWidget(self.submit_button)

        self.submit_button.clicked.connect(self._on_submit)

    def _on_submit(self) -> None:
        if self.new_password_edit.text() != self.confirm_password_edit.text():
            self.error_label.setText("Les deux mots de passe ne correspondent pas.")
            return
        self.accept()

    def username(self) -> str:
        return self.username_edit.text().strip()

    def code(self) -> str:
        return self.code_edit.text()

    def new_password(self) -> str:
        return self.new_password_edit.text()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
