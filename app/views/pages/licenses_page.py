"""Page Administration → Licence (§14) : consultation de la licence active et
activation/remplacement par un nouveau fichier de licence.

Toute action passe par :class:`LicenseService`, qui revérifie la permission
côté service et revalide systématiquement la signature — cette page ne fait
qu'afficher l'état retourné et proposer l'import d'un fichier. La clé privée
n'est jamais manipulée ici (ni nulle part côté client) : seule une clé
publique embarquée sert à vérifier une licence déjà signée.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.licensing.license_service import LicenseInfo, LicenseService, LicenseState
from app.utils.exceptions import AppError

_STATE_LABELS = {
    LicenseState.VALID: "Valide",
    LicenseState.EXPIRED: "Expirée",
    LicenseState.MISSING: "Aucune licence activée",
    LicenseState.INVALID: "Invalide",
    LicenseState.CORRUPTED: "Corrompue",
}


class LicensesPage(QWidget):
    def __init__(
        self,
        license_service: LicenseService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._license_service = license_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_status_group())

        self.activate_button = QPushButton("Importer / activer une licence…", self)
        self.activate_button.setEnabled(self._permissions.has_permission("LICENSE_ACTIVATE"))
        self.activate_button.clicked.connect(self._on_activate_clicked)
        layout.addWidget(self.activate_button)
        layout.addStretch(1)

        self.refresh()

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("Licence active", self)
        form = QFormLayout(group)

        self.state_label = QLabel(self)
        form.addRow("Statut", self.state_label)
        self.client_label = QLabel(self)
        form.addRow("Client", self.client_label)
        self.edition_label = QLabel(self)
        form.addRow("Édition", self.edition_label)
        self.license_id_label = QLabel(self)
        form.addRow("Identifiant de licence", self.license_id_label)
        self.issued_at_label = QLabel(self)
        form.addRow("Date d'émission", self.issued_at_label)
        self.expires_at_label = QLabel(self)
        form.addRow("Date d'expiration", self.expires_at_label)
        self.max_users_label = QLabel(self)
        form.addRow("Utilisateurs maximum", self.max_users_label)
        self.max_devices_label = QLabel(self)
        form.addRow("Postes maximum", self.max_devices_label)
        self.features_label = QLabel(self)
        self.features_label.setWordWrap(True)
        form.addRow("Fonctionnalités activées", self.features_label)
        self.device_id_label = QLabel(self)
        form.addRow("Identifiant de ce poste", self.device_id_label)

        return group

    def refresh(self) -> None:
        try:
            info = self._license_service.get_info()
        except AppError as exc:
            self._apply_empty(str(exc))
            return
        self._apply_info(info)

    def _apply_empty(self, message: str) -> None:
        self.state_label.setText(message)
        for label in (
            self.client_label, self.edition_label, self.license_id_label, self.issued_at_label,
            self.expires_at_label, self.max_users_label, self.max_devices_label, self.features_label,
            self.device_id_label,
        ):
            label.setText("—")

    def _apply_info(self, info: LicenseInfo) -> None:
        self.state_label.setText(_STATE_LABELS.get(info.state, info.state.value))
        self.client_label.setText(info.client or "—")
        self.edition_label.setText(info.edition.value if info.edition else "—")
        self.license_id_label.setText(info.license_id or "—")
        self.issued_at_label.setText(info.issued_at.isoformat() if info.issued_at else "—")
        self.expires_at_label.setText(info.expires_at.isoformat() if info.expires_at else "Sans expiration")
        self.max_users_label.setText(str(info.max_users) if info.max_users is not None else "—")
        self.max_devices_label.setText(str(info.max_devices) if info.max_devices is not None else "—")
        self.features_label.setText(", ".join(sorted(info.features)) if info.features else "—")
        self.device_id_label.setText(info.device_id or "—")

    def _on_activate_clicked(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier de licence", "", "Licences StockManager (*.lic *.json);;Tous les fichiers (*)"
        )
        if not file_path:
            return
        self._activate_from_file(file_path)

    def _activate_from_file(self, file_path: str) -> bool:
        """Isolé de ``_on_activate_clicked`` pour rester testable sans
        dialogue modal de sélection de fichier."""
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except OSError as exc:
            QMessageBox.warning(self, "Lecture impossible", f"Impossible de lire le fichier : {exc}")
            return False

        try:
            self._license_service.activate_license(content)
        except AppError as exc:
            QMessageBox.warning(self, "Activation refusée", str(exc))
            return False

        self.refresh()
        QMessageBox.information(self, "Licence activée", "La licence a été activée avec succès.")
        return True
