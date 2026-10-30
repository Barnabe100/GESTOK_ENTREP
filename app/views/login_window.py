"""Écran de connexion.

Ne contient aucune logique métier : délègue entièrement la vérification des
identifiants à :class:`AuthService`.

« Se souvenir de moi » (phase amélioration UX, point 1) : préremplit les
champs à l'ouverture si des identifiants sont mémorisés
(``app.security.remembered_login``), les enregistre après une connexion
réussie si la case est cochée, les efface si elle est décochée. Passe
toujours par le mécanisme d'authentification existant (``AuthService.login``,
inchangé) — ne le contourne jamais et ne mémorise jamais un mot de passe
PostgreSQL (coffre dédié, distinct, voir
``app.security.credential_vault.get_login_credential_vault``). Une
indisponibilité du coffre n'empêche jamais la connexion déjà réussie,
seulement la mémorisation elle-même."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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

from app.security.remembered_login import (
    forget_remembered_login,
    get_remembered_password,
    get_remembered_username,
    remember_login,
)
from app.services.auth.account_recovery_service import AccountRecoveryService
from app.services.auth.auth_service import AuthService
from app.utils.exceptions import AccountDisabledError, AuthenticationError, AppError, CredentialVaultUnavailableError
from app.views.account_recovery_dialog import AccountRecoveryDialog
from app.views.common import confirm_action, run_modal_form
from app.views.loading_overlay import LoadingOverlay
from app.views.password_line_edit import PasswordLineEdit


class LoginWindow(QDialog):
    def __init__(
        self,
        auth_service: AuthService,
        account_recovery_service: AccountRecoveryService,
        data_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._auth_service = auth_service
        self._account_recovery_service = account_recovery_service
        self._data_dir = data_dir

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

        remember_row = QHBoxLayout()
        self.remember_me_checkbox = QCheckBox("Se souvenir de moi", self)
        remember_row.addWidget(self.remember_me_checkbox)
        remember_row.addStretch(1)
        self.forget_remembered_button = QPushButton("Oublier les identifiants mémorisés", self)
        self.forget_remembered_button.setFlat(True)
        remember_row.addWidget(self.forget_remembered_button)
        layout.addLayout(remember_row)

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
        self.login_button.setProperty("variant", "primary")
        self.login_button.setDefault(True)
        button_row.addWidget(self.login_button)
        layout.addLayout(button_row)

        self.login_button.clicked.connect(self._on_login_clicked)
        self.password_edit.returnPressed.connect(self._on_login_clicked)
        self.username_edit.returnPressed.connect(self._on_login_clicked)
        self.forgot_password_button.clicked.connect(self._on_forgot_password_clicked)
        self.forget_remembered_button.clicked.connect(self._on_forget_remembered_clicked)

        # Phase amélioration UX, point 3 : voile affiché pendant l'appel à
        # AuthService.login (créé en dernier pour recouvrir tout le reste).
        self._loading_overlay = LoadingOverlay(self)

        self._prefill_remembered_login()

    # -- « Se souvenir de moi » ---------------------------------------------

    def _prefill_remembered_login(self) -> None:
        """Préremplit l'identifiant et, si disponible, le mot de passe
        mémorisés — jamais une erreur bloquante : une absence de
        mémorisation ou un coffre indisponible laisse simplement les champs
        vides, la connexion manuelle restant toujours possible."""
        remembered_username = get_remembered_username(self._data_dir)
        self.forget_remembered_button.setEnabled(remembered_username is not None)
        if remembered_username is None:
            return
        self.username_edit.setText(remembered_username)
        self.remember_me_checkbox.setChecked(True)
        remembered_password = get_remembered_password(self._data_dir, remembered_username)
        if remembered_password is not None:
            self.password_edit.setText(remembered_password)

    def _on_forget_remembered_clicked(self) -> None:
        if not confirm_action(
            self, "Confirmation",
            "Voulez-vous vraiment oublier les identifiants mémorisés sur ce poste ?",
        ):
            return
        forget_remembered_login(self._data_dir)
        self.remember_me_checkbox.setChecked(False)
        self.forget_remembered_button.setEnabled(False)

    def _apply_remember_me_choice(self, username: str, password: str) -> None:
        """Appelée uniquement après une connexion déjà réussie (voir
        ``_on_login_clicked``) — ne détermine jamais, elle-même, si la
        connexion est acceptée."""
        if self.remember_me_checkbox.isChecked():
            try:
                remember_login(self._data_dir, username, password)
            except CredentialVaultUnavailableError as exc:
                QMessageBox.warning(
                    self, "Mémorisation impossible",
                    "Vous êtes connecté, mais vos identifiants n'ont pas pu être mémorisés "
                    f"sur ce poste : {exc}",
                )
        else:
            forget_remembered_login(self._data_dir)

    def _on_login_clicked(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        if not username or not password:
            self.error_label.setText("Veuillez renseigner l'identifiant et le mot de passe.")
            return

        # Phase amélioration UX, point 3 : empêche les doubles soumissions
        # (bouton désactivé) et affiche un retour explicite pendant l'appel
        # — jamais de QThread ici, AuthService.login utilise une session
        # SQLAlchemy sur le thread appelant comme partout ailleurs dans
        # cette fenêtre.
        self.login_button.setEnabled(False)
        self._loading_overlay.show_with_message("Connexion en cours…")
        QApplication.processEvents()
        login_succeeded = False
        try:
            self._auth_service.login(username, password)
            login_succeeded = True
        except AccountDisabledError:
            self.error_label.setText("Ce compte est désactivé.")
            self.password_edit.clear()
        except AuthenticationError:
            self.error_label.setText("Identifiant ou mot de passe incorrect.")
            self.password_edit.clear()
        finally:
            self._loading_overlay.hide_overlay()
            self.login_button.setEnabled(True)

        if login_succeeded:
            self._apply_remember_me_choice(username, password)
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
