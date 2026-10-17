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
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.account_recovery_service import AccountRecoveryService
from app.services.auth.auth_service import AuthService
from app.utils.exceptions import AccountDisabledError, AuthenticationError, AppError
from app.views.account_recovery_dialog import AccountRecoveryDialog
from app.views.common import run_modal_form
from app.views.password_line_edit import PasswordLineEdit


class LoginWindow(QDialog):
    def __init__(
        self,
        auth_service: AuthService,
        account_recovery_service: AccountRecoveryService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._auth_service = auth_service
        self._account_recovery_service = account_recovery_service

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
        self.password_edit = PasswordLineEdit(self)
        self.password_edit.setPlaceholderText("Mot de passe")
        form.addRow("Utilisateur", self.username_edit)
        form.addRow("Mot de passe", self.password_edit)
        layout.addLayout(form)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        self.forgot_password_button = QPushButton("Mot de passe oublié ?", self)
        self.forgot_password_button.setFlat(True)
        button_row.addWidget(self.forgot_password_button)
        button_row.addStretch(1)
        self.login_button = QPushButton("Se connecter", self)
        self.login_button.setDefault(True)
        button_row.addWidget(self.login_button)
        layout.addLayout(button_row)

        self.login_button.clicked.connect(self._on_login_clicked)
        self.password_edit.returnPressed.connect(self._on_login_clicked)
        self.username_edit.returnPressed.connect(self._on_login_clicked)
        self.forgot_password_button.clicked.connect(self._on_forgot_password_clicked)

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

    def _on_forgot_password_clicked(self) -> None:
        # Nom d'utilisateur conservé d'une tentative à l'autre (confort),
        # jamais le code ni le nouveau mot de passe — même convention que
        # UsersPage._on_add_clicked pour CreateUserDialog.
        state = {"username": self.username_edit.text().strip()}

        def factory() -> AccountRecoveryDialog:
            return AccountRecoveryDialog(initial_username=state["username"], parent=self)

        def submit(dialog: AccountRecoveryDialog) -> bool:
            state["username"] = dialog.username()
            return self._submit_account_recovery(dialog)

        run_modal_form(factory, submit)

    def _submit_account_recovery(self, dialog: AccountRecoveryDialog) -> bool:
        """Isolé de ``_on_forgot_password_clicked`` pour rester testable
        sans dialogue modal (même principe que
        ``UsersPage._submit_create_user``)."""
        try:
            self._account_recovery_service.reset_password_with_code(
                dialog.username(), dialog.code(), dialog.new_password()
            )
        except AppError as exc:
            dialog.set_error(str(exc))
            return False
        QMessageBox.information(
            self, "Mot de passe réinitialisé",
            "Votre mot de passe a été réinitialisé. Vous pouvez maintenant vous connecter.",
        )
        return True
