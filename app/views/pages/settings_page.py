"""Page Paramètres : profil de l'entreprise cliente (nom, coordonnées),
devise d'affichage, logo client — réservée à l'Administrateur
(``SETTINGS_VIEW``/``SETTINGS_UPDATE``).

Le logo géré ici est celui de l'entreprise cliente, destiné aux futurs
reçus/documents PDF qui la concernent : entièrement distinct du logo
StockManager/SM (identité du produit), ni affiché ni modifiable depuis
cette page.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.settings.company_settings_service import (
    CompanySettingsConfig,
    CompanySettingsService,
    SUPPORTED_CURRENCIES,
)
from app.utils.exceptions import AppError
from app.views.common import confirm_action

_LOGO_PREVIEW_SIZE = 160


class SettingsPage(QWidget):
    def __init__(
        self,
        settings_service: CompanySettingsService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_service = settings_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_profile_group())
        layout.addWidget(self._build_logo_group())
        layout.addStretch(1)

        self._load_config_into_form()

    # -- profil de l'entreprise -----------------------------------------------

    def _build_profile_group(self) -> QGroupBox:
        group = QGroupBox("Informations de l'entreprise", self)
        form = QFormLayout(group)

        self.nom_edit = QLineEdit(self)
        form.addRow("Nom de l'entreprise", self.nom_edit)

        self.adresse_edit = QLineEdit(self)
        form.addRow("Adresse", self.adresse_edit)

        self.telephone_edit = QLineEdit(self)
        form.addRow("Téléphone", self.telephone_edit)

        self.email_edit = QLineEdit(self)
        form.addRow("Email", self.email_edit)

        self.devise_combo = QComboBox(self)
        self.devise_combo.addItems(sorted(SUPPORTED_CURRENCIES))
        form.addRow("Devise", self.devise_combo)

        can_update = self._permissions.has_permission("SETTINGS_UPDATE")
        for widget in (
            self.nom_edit, self.adresse_edit, self.telephone_edit, self.email_edit, self.devise_combo,
        ):
            widget.setEnabled(can_update)

        self.save_profile_button = QPushButton("Enregistrer", self)
        self.save_profile_button.setEnabled(can_update)
        form.addRow(self.save_profile_button)

        self.save_profile_button.clicked.connect(self._on_save_profile_clicked)

        return group

    def _load_config_into_form(self) -> None:
        try:
            config = self._settings_service.get_config()
        except AppError:
            return
        self._apply_config_to_form(config)

    def _apply_config_to_form(self, config: CompanySettingsConfig) -> None:
        self.nom_edit.setText(config.nom or "")
        self.adresse_edit.setText(config.adresse or "")
        self.telephone_edit.setText(config.telephone or "")
        self.email_edit.setText(config.email or "")
        index = self.devise_combo.findText(config.devise)
        if index != -1:
            self.devise_combo.setCurrentIndex(index)
        self._apply_logo_preview(config)

    def _on_save_profile_clicked(self) -> None:
        self._save_profile()

    def _save_profile(self) -> bool:
        """Isolé de ``_on_save_profile_clicked`` pour rester testable sans
        dialogue modal."""
        try:
            self._settings_service.update_config(
                nom=self.nom_edit.text(),
                adresse=self.adresse_edit.text(),
                telephone=self.telephone_edit.text(),
                email=self.email_edit.text(),
                devise=self.devise_combo.currentText(),
            )
            QMessageBox.information(
                self, "Paramètres enregistrés", "Les paramètres de l'entreprise ont été enregistrés."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Enregistrement refusé", str(exc))
            return False
        self._load_config_into_form()
        return True

    # -- logo de l'entreprise cliente -------------------------------------------

    def _build_logo_group(self) -> QGroupBox:
        group = QGroupBox("Logo de l'entreprise cliente", self)
        layout = QVBoxLayout(group)

        self.logo_preview_label = QLabel(self)
        self.logo_preview_label.setFixedSize(_LOGO_PREVIEW_SIZE, _LOGO_PREVIEW_SIZE)
        self.logo_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_preview_label.setStyleSheet("border: 1px solid palette(mid);")
        layout.addWidget(self.logo_preview_label)

        can_update = self._permissions.has_permission("SETTINGS_UPDATE")

        buttons_row = QHBoxLayout()
        self.choose_logo_button = QPushButton("Choisir un logo…", self)
        self.choose_logo_button.setEnabled(can_update)
        buttons_row.addWidget(self.choose_logo_button)

        self.clear_logo_button = QPushButton("Supprimer le logo", self)
        self.clear_logo_button.setEnabled(can_update)
        buttons_row.addWidget(self.clear_logo_button)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)

        self.choose_logo_button.clicked.connect(self._on_choose_logo_clicked)
        self.clear_logo_button.clicked.connect(self._on_clear_logo_clicked)

        return group

    def _apply_logo_preview(self, config: CompanySettingsConfig) -> None:
        if config.logo_path is not None and config.logo_path.exists():
            pixmap = QPixmap(str(config.logo_path))
            if not pixmap.isNull():
                self.logo_preview_label.setPixmap(
                    pixmap.scaled(
                        _LOGO_PREVIEW_SIZE, _LOGO_PREVIEW_SIZE,
                        Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.logo_preview_label.setPixmap(QPixmap())
        self.logo_preview_label.setText("Aucun logo")

    def _on_choose_logo_clicked(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(
            self, "Choisir un logo", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not file_path:
            return
        self._set_logo_from_file(file_path)

    def _set_logo_from_file(self, file_path: str) -> bool:
        """Isolé de ``_on_choose_logo_clicked`` pour rester testable sans
        dialogue modal de sélection de fichier."""
        try:
            self._settings_service.set_logo(file_path)
            QMessageBox.information(self, "Logo mis à jour", "Le logo de l'entreprise a été mis à jour.")
        except AppError as exc:
            QMessageBox.warning(self, "Logo refusé", str(exc))
            return False
        self._load_config_into_form()
        return True

    def _on_clear_logo_clicked(self) -> None:
        if not confirm_action(self, "Confirmation", "Voulez-vous vraiment supprimer le logo de l'entreprise ?"):
            return
        self._clear_logo()

    def _clear_logo(self) -> bool:
        """Isolé de ``_on_clear_logo_clicked`` pour rester testable sans
        boîte de confirmation modale."""
        try:
            self._settings_service.clear_logo()
        except AppError as exc:
            QMessageBox.warning(self, "Suppression refusée", str(exc))
            return False
        self._load_config_into_form()
        return True
