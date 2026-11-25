"""Dialogue de saisie du mot de passe de transfert de la clé de
chiffrement (export/import) — remplace ``QInputDialog.getText`` (mission
corrective « Correction et validation du module de sauvegarde sous
Windows », §3.4/§6.2) : ``QInputDialog`` ne permet ni confirmation, ni
bouton supplémentaire, ni bascule d'affichage temporaire du mot de passe,
ni avertissement dédié — un dialogue ``QDialog`` personnalisé est la seule
option Qt pour satisfaire ces exigences sans bibliothèque supplémentaire.

Ne connaît rien du chiffrement lui-même : collecte uniquement un mot de
passe (et sa confirmation, à l'export) et le restitue via :meth:`password`
— c'est l'appelant (``BackupsPage``) qui reste seul responsable d'appeler
``BackupService.export_encryption_key``/``import_encryption_key`` et d'en
traiter le résultat."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Même valeur que la politique de mot de passe des comptes utilisateurs
# (voir ``app.services.auth.auth_service.MIN_PASSWORD_LENGTH``) — jamais
# importée directement d'un module d'authentification sans rapport avec le
# transfert de clé de chiffrement, mais la même exigence minimale par
# cohérence pour l'utilisateur.
MIN_TRANSFER_PASSWORD_LENGTH = 8

MODE_EXPORT = "export"
MODE_IMPORT = "import"


class KeyPasswordDialog(QDialog):
    """``mode=MODE_EXPORT`` : champ mot de passe + confirmation + rappel de
    conservation + avertissement d'irrécupérabilité. ``mode=MODE_IMPORT`` :
    champ mot de passe seul (celui choisi lors de l'export correspondant,
    jamais de nouvelle exigence de robustesse à l'import — le mot de passe
    doit simplement correspondre à celui déjà utilisé). Bascule
    d'affichage temporaire disponible dans les deux cas."""

    def __init__(self, mode: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if mode not in (MODE_EXPORT, MODE_IMPORT):
            raise ValueError(f"Mode de dialogue de mot de passe inconnu : {mode!r}")
        self._mode = mode

        self.setWindowTitle(
            "Mot de passe de protection" if mode == MODE_EXPORT else "Mot de passe du fichier de transfert"
        )
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        if mode == MODE_EXPORT:
            intro = QLabel(
                "Choisissez un mot de passe pour protéger le fichier exporté — il sera nécessaire "
                "pour l'importer sur le nouvel ordinateur. Ce mot de passe n'est enregistré nulle "
                "part par StockManager : conservez-le vous-même, séparément du fichier exporté.",
                self,
            )
        else:
            intro = QLabel("Saisissez le mot de passe choisi lors de l'export de cette clé :", self)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Mot de passe", self.password_edit)

        self.confirm_edit: QLineEdit | None = None
        if mode == MODE_EXPORT:
            self.confirm_edit = QLineEdit(self)
            self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("Confirmer le mot de passe", self.confirm_edit)

        layout.addLayout(form)

        self.show_password_checkbox = QCheckBox("Afficher le mot de passe", self)
        layout.addWidget(self.show_password_checkbox)

        if mode == MODE_EXPORT:
            hint = QLabel(f"Au moins {MIN_TRANSFER_PASSWORD_LENGTH} caractères.", self)
            hint.setWordWrap(True)
            layout.addWidget(hint)

            warning = QLabel(
                "Important : ce mot de passe n'est conservé nulle part. TechNova ne peut en aucun "
                "cas le récupérer ou le réinitialiser pour vous — s'il est perdu, le fichier exporté "
                "devient définitivement inutilisable.",
                self,
            )
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #B45309; font-weight: 600;")
            layout.addWidget(warning)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.ok_button = QPushButton("OK", self)
        self.ok_button.setProperty("variant", "primary")
        self.ok_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)
        layout.addLayout(button_row)

        self.show_password_checkbox.toggled.connect(self._on_show_password_toggled)
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self._on_ok_clicked)

    def _on_show_password_toggled(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.password_edit.setEchoMode(mode)
        if self.confirm_edit is not None:
            self.confirm_edit.setEchoMode(mode)

    def _on_ok_clicked(self) -> None:
        password = self.password_edit.text()
        if not password:
            self.error_label.setText("Le mot de passe est obligatoire.")
            return
        if self._mode == MODE_EXPORT:
            if len(password) < MIN_TRANSFER_PASSWORD_LENGTH:
                self.error_label.setText(
                    f"Le mot de passe doit contenir au moins {MIN_TRANSFER_PASSWORD_LENGTH} caractères."
                )
                return
            if password != self.confirm_edit.text():
                self.error_label.setText("Les deux mots de passe ne correspondent pas.")
                return
        self.accept()

    def password(self) -> str:
        return self.password_edit.text()
