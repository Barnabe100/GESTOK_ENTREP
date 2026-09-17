"""Écran de connexion.

Ne contient aucune logique métier : délègue entièrement la vérification des
identifiants à :class:`AuthService`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.auth_service import AuthService
from app.utils.exceptions import AccountDisabledError, AuthenticationError


class LoginWindow(QDialog):
    def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._auth_service = auth_service

        self.setWindowTitle("Connexion — StockManager Desktop")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        title = QLabel("StockManager Desktop")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        self.username_edit = QLineEdit(self)
        self.username_edit.setPlaceholderText("Identifiant")
        self.password_edit = QLineEdit(self)
        self.password_edit.setPlaceholderText("Mot de passe")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Utilisateur", self.username_edit)
        form.addRow("Mot de passe", self.password_edit)
        layout.addLayout(form)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.login_button = QPushButton("Se connecter", self)
        self.login_button.setDefault(True)
        button_row.addWidget(self.login_button)
        layout.addLayout(button_row)

        self.login_button.clicked.connect(self._on_login_clicked)
        self.password_edit.returnPressed.connect(self._on_login_clicked)
        self.username_edit.returnPressed.connect(self._on_login_clicked)

    def _on_login_clicked(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        if not username or not password:
            self.error_label.setText("Veuillez renseigner l'identifiant et le mot de passe.")
            return

        try:
            self._auth_service.login(username, password)
        except AccountDisabledError:
            self.error_label.setText("Ce compte est désactivé.")
            self.password_edit.clear()
        except AuthenticationError:
            self.error_label.setText("Identifiant ou mot de passe incorrect.")
            self.password_edit.clear()
        else:
            self.accept()
