"""Page Administration → Licence (§14) : consultation de la licence active et
activation/remplacement par un nouveau fichier de licence.

Toute action passe par :class:`LicenseService`, qui revérifie la permission
côté service et revalide systématiquement la signature — cette page ne fait
qu'afficher l'état retourné et proposer l'import d'un fichier. La clé privée
n'est jamais manipulée ici (ni nulle part côté client) : seule une clé
publique embarquée sert à vérifier une licence déjà signée.

L'activation elle-même passe désormais par :class:`ActivationService`, qui
choisit entre le mode LOCAL (comportement ci-dessus, inchangé) et un futur
mode SERVER (activation via un serveur TechNova non encore implémenté — voir
``license_server_client.py``). Cette page se contente d'afficher le mode
courant et de proposer son changement ; elle ne contient aucune logique de
validation ou de comptage."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
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
from app.services.licensing.activation_mode import ActivationMode
from app.services.licensing.activation_service import ActivationService
from app.services.licensing.license_service import LicenseInfo, LicenseService, LicenseState
from app.utils.exceptions import AppError

_STATE_LABELS = {
    LicenseState.VALID: "Valide",
    LicenseState.EXPIRED: "Expirée",
    LicenseState.MISSING: "Aucune licence activée",
    LicenseState.INVALID: "Invalide",
    LicenseState.CORRUPTED: "Corrompue",
}

_MODE_LABELS = {
    ActivationMode.LOCAL: "LOCAL",
    ActivationMode.SERVER: "SERVER",
}

_MODE_DESCRIPTIONS = {
    ActivationMode.LOCAL: "Activation hors ligne",
    ActivationMode.SERVER: "Activation via serveur TechNova — Internet requis",
}


class LicensesPage(QWidget):
    def __init__(
        self,
        license_service: LicenseService,
        activation_service: ActivationService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._license_service = license_service
        self._activation_service = activation_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_status_group())
        layout.addWidget(self._build_mode_group())

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

    def _build_mode_group(self) -> QGroupBox:
        group = QGroupBox("Mode d'activation", self)
        layout = QVBoxLayout(group)

        self.mode_combo = QComboBox(self)
        for mode in (ActivationMode.LOCAL, ActivationMode.SERVER):
            self.mode_combo.addItem(_MODE_LABELS[mode], mode)
        self.mode_combo.setEnabled(self._permissions.has_permission("LICENSE_ACTIVATE"))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        self.mode_description_label = QLabel(self)
        self.mode_description_label.setWordWrap(True)
        layout.addWidget(self.mode_description_label)

        return group

    def refresh(self) -> None:
        try:
            info = self._license_service.get_info()
        except AppError as exc:
            self._apply_empty(str(exc))
            return
        self._apply_info(info)
        self._refresh_mode()

    def _refresh_mode(self) -> None:
        """Synchronise le sélecteur avec le mode réellement stocké (jamais
        l'inverse) — signaux bloqués le temps de la synchronisation pour ne
        pas redéclencher ``_on_mode_changed`` (et donc ``set_mode``) à
        chaque rafraîchissement."""
        try:
            mode = self._activation_service.get_mode()
        except AppError:
            mode = ActivationMode.LOCAL

        self.mode_combo.blockSignals(True)
        index = self.mode_combo.findData(mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self.mode_combo.blockSignals(False)
        self.mode_description_label.setText(_MODE_DESCRIPTIONS[mode])

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

    def _on_mode_changed(self, index: int) -> None:
        data = self.mode_combo.itemData(index)
        if data is None:
            return
        # PySide6 déballe un ``str`` (même sous-classé, comme ActivationMode)
        # stocké comme donnée d'item en simple ``str`` Python — reconstruire
        # explicitement le membre d'énumération plutôt que de faire
        # confiance au type retourné par itemData().
        mode = ActivationMode(data)
        try:
            self._activation_service.set_mode(mode)
        except AppError as exc:
            QMessageBox.warning(self, "Changement de mode refusé", str(exc))
            self._refresh_mode()
            return
        self.mode_description_label.setText(_MODE_DESCRIPTIONS[mode])

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
            self._activation_service.activate(content)
        except AppError as exc:
            QMessageBox.warning(self, "Activation refusée", str(exc))
            return False

        self.refresh()
        QMessageBox.information(self, "Licence activée", "La licence a été activée avec succès.")
        return True
