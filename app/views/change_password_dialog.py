"""Dialogue de changement de mot de passe (volontaire ou imposé).

Ne fait aucune vérification de sécurité elle-même : délègue à
:meth:`AuthService.change_password`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.auth_service import AuthService
from app.utils.exceptions import AppError


class ChangePasswordDialog(QDialog):
    def __init__(
        self, auth_service: AuthService, parent: QWidget | None = None, forced: bool = False
    ) -> None:
        super().__init__(parent)
        self._auth_service = auth_service
        self._forced = forced

        self.setWindowTitle(
            "Changement de mot de passe obligatoire" if forced else "Changer le mot de passe"
        )
        self.setModal(True)
        if forced:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        layout = QVBoxLayout(self)

        if forced:
            notice = QLabel("Votre mot de passe temporaire doit être changé avant de continuer.")
            notice.setWordWrap(True)
            layout.addWidget(notice)

        form = QFormLayout()
        self.old_password_edit = QLineEdit(self)
        self.old_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_edit = QLineEdit(self)
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_edit = QLineEdit(self)
        self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Mot de passe actuel", self.old_password_edit)
        form.addRow("Nouveau mot de passe", self.new_password_edit)
        form.addRow("Confirmer le nouveau mot de passe", self.confirm_password_edit)
        layout.addLayout(form)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.submit_button = QPushButton("Valider", self)
        self.submit_button.setDefault(True)
        layout.addWidget(self.submit_button)

        self.submit_button.clicked.connect(self._on_submit)

    def _on_submit(self) -> None:
        new_password = self.new_password_edit.text()
        confirm_password = self.confirm_password_edit.text()

        if new_password != confirm_password:
            self.error_label.setText("Les deux mots de passe ne correspondent pas.")
            return

        try:
            self._auth_service.change_password(self.old_password_edit.text(), new_password)
        except AppError as exc:
            self.error_label.setText(str(exc))
            return

        self.accept()
