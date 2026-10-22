"""Page Paramètres : profil de l'entreprise cliente (nom, coordonnées),
devise d'affichage, logo client — réservée à l'Administrateur
(``SETTINGS_VIEW``/``SETTINGS_UPDATE``).

Le logo géré ici est celui de l'entreprise cliente, destiné aux futurs
reçus/documents PDF qui la concernent : entièrement distinct du logo
StockManager/SM (identité du produit), ni affiché ni modifiable depuis
cette page.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import StatutLocation
from app.services.auth.account_recovery_service import AccountRecoveryService
from app.services.auth.permission_service import PermissionService
from app.services.rentals.location_service import LocationService
from app.services.settings.company_settings_service import (
    CompanySettingsConfig,
    CompanySettingsService,
    DEFAULT_RECEIPT_FOOTER,
    SUPPORTED_CURRENCIES,
    is_rental_module_enabled,
)
from app.utils.exceptions import AppError
from app.views.common import build_required_field_legend, confirm_action, required_label
from app.views.recovery_code_display_dialog import RecoveryCodeDisplayDialog

# Lot 16 : seul le statut EN_COURS représente une location « encore en
# cours » au sens de la décision métier (le départ, CONFIRMEE -> EN_COURS,
# est le seul moment où LocationService décrémente réellement le stock —
# voir sa docstring de module : BROUILLON/CONFIRMEE ne réservent rien
# physiquement et peuvent être modifiées/annulées/supprimées sans aucune
# conséquence sur le stock, les paiements ou la caution). Avertir aussi
# pour BROUILLON/CONFIRMEE élargirait l'avertissement sans justification
# opérationnelle réelle.
_ONGOING_LOCATION_STATUSES = (StatutLocation.EN_COURS,)

_LOGO_PREVIEW_SIZE = 160


class SettingsPage(QWidget):
    def __init__(
        self,
        settings_service: CompanySettingsService,
        permission_service: PermissionService,
        account_recovery_service: AccountRecoveryService,
        rental_service: LocationService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings_service = settings_service
        self._permissions = permission_service
        self._account_recovery_service = account_recovery_service
        self._rental_service = rental_service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Zone défilante (Lot 22, anomalie C) : regroupe les cinq sections —
        # même principe déjà établi dans ``SaleDetailDialog`` (Lot 15) —
        # pour qu'un empilement de groupes plus haut que l'espace disponible
        # (notamment sous Windows, où les métriques de police par défaut
        # diffèrent) défile au lieu de comprimer les champs des
        # ``QFormLayout`` ou de couper l'aperçu du logo.
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(self._build_profile_group())
        content_layout.addWidget(self._build_logo_group())
        content_layout.addWidget(self._build_receipt_footer_group())
        content_layout.addWidget(self._build_modules_group())
        content_layout.addWidget(self._build_security_group())
        content_layout.addStretch(1)

        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        self._load_config_into_form()
        self._load_modules_into_form()

    # -- profil de l'entreprise -----------------------------------------------

    def _build_profile_group(self) -> QGroupBox:
        group = QGroupBox("Informations de l'entreprise", self)
        form = QFormLayout(group)

        self.nom_edit = QLineEdit(self)
        form.addRow(required_label("Nom de l'entreprise"), self.nom_edit)

        self.adresse_edit = QLineEdit(self)
        form.addRow("Adresse", self.adresse_edit)

        self.telephone_edit = QLineEdit(self)
        form.addRow("Téléphone", self.telephone_edit)

        self.email_edit = QLineEdit(self)
        form.addRow("Email", self.email_edit)

        self.devise_combo = QComboBox(self)
        self.devise_combo.addItems(sorted(SUPPORTED_CURRENCIES))
        form.addRow(required_label("Devise"), self.devise_combo)

        can_update = self._permissions.has_permission("SETTINGS_UPDATE")
        for widget in (
            self.nom_edit, self.adresse_edit, self.telephone_edit, self.email_edit, self.devise_combo,
        ):
            widget.setEnabled(can_update)

        self.save_profile_button = QPushButton("Enregistrer", self)
        self.save_profile_button.setEnabled(can_update)
        form.addRow(self.save_profile_button)

        form.addRow(build_required_field_legend(self))

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
        self.receipt_footer_edit.setText(config.recu_pied_de_page)

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

    # -- pied de reçu (Lot 21 — reçu unifié) --------------------------------------

    def _build_receipt_footer_group(self) -> QGroupBox:
        group = QGroupBox("Pied de reçu", self)
        form = QFormLayout(group)

        self.receipt_footer_edit = QLineEdit(self)
        self.receipt_footer_edit.setPlaceholderText(DEFAULT_RECEIPT_FOOTER)
        form.addRow("Phrase affichée en bas du reçu", self.receipt_footer_edit)

        hint = QLabel(
            "Laissez ce champ vide pour n'imprimer aucun pied de reçu.", group
        )
        hint.setWordWrap(True)
        form.addRow(hint)

        can_update = self._permissions.has_permission("SETTINGS_UPDATE")
        self.receipt_footer_edit.setEnabled(can_update)

        self.save_receipt_footer_button = QPushButton("Enregistrer", self)
        self.save_receipt_footer_button.setEnabled(can_update)
        form.addRow(self.save_receipt_footer_button)

        self.save_receipt_footer_button.clicked.connect(self._on_save_receipt_footer_clicked)

        return group

    def _on_save_receipt_footer_clicked(self) -> None:
        self._save_receipt_footer()

    def _save_receipt_footer(self) -> bool:
        """Isolé de ``_on_save_receipt_footer_clicked`` pour rester testable
        sans boîte modale. La modification ne touche jamais les ventes ou
        paiements déjà enregistrés (voir ``CompanySettingsService.set_receipt_footer``,
        une simple clé de paramètres) — seuls les futurs reçus imprimés en
        tiennent compte."""
        try:
            self._settings_service.set_receipt_footer(self.receipt_footer_edit.text())
            QMessageBox.information(
                self, "Paramètres enregistrés", "Le pied de reçu a été mis à jour."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Enregistrement refusé", str(exc))
            return False
        self._load_config_into_form()
        return True

    # -- modules optionnels (Lot 16) ---------------------------------------------

    def _build_modules_group(self) -> QGroupBox:
        group = QGroupBox("Modules optionnels", self)
        layout = QVBoxLayout(group)

        self.locations_module_checkbox = QCheckBox("Activer le module Location", self)
        layout.addWidget(self.locations_module_checkbox)

        can_update = self._permissions.has_permission("SETTINGS_UPDATE")
        self.locations_module_checkbox.setEnabled(can_update)

        self.save_modules_button = QPushButton("Enregistrer", self)
        self.save_modules_button.setEnabled(can_update)
        layout.addWidget(self.save_modules_button)

        self.save_modules_button.clicked.connect(self._on_save_modules_clicked)

        return group

    def _load_modules_into_form(self) -> None:
        self.locations_module_checkbox.setChecked(is_rental_module_enabled())

    def _has_ongoing_locations(self) -> bool:
        """Utilisée uniquement pour l'avertissement non bloquant avant une
        désactivation — ``LocationService.list_locations`` existant,
        jamais modifié ni dupliqué ; le filtrage « en cours » reste une
        simple lecture du statut déjà exposé par ``LocationSummary``."""
        try:
            locations = self._rental_service.list_locations()
        except AppError:
            return False
        return any(location.statut in _ONGOING_LOCATION_STATUSES for location in locations)

    def _on_save_modules_clicked(self) -> None:
        self._save_modules()

    def _save_modules(self) -> bool:
        """Isolé de ``_on_save_modules_clicked`` pour rester testable sans
        boîte modale. Le changement prend effet à la prochaine ouverture de
        la fenêtre principale (navigation calculée une fois à la
        construction, voir ``MainWindow``) — jamais en direct dans cette
        même session."""
        enabled = self.locations_module_checkbox.isChecked()
        is_deactivating = not enabled and is_rental_module_enabled()
        if is_deactivating and self._has_ongoing_locations():
            if not confirm_action(
                self, "Confirmation",
                "Des locations sont encore en cours (article(s) remis au client, retour non "
                "effectué). Désactiver le module Location rendra leur suivi opérationnel "
                "(retour, paiement, caution) inaccessible jusqu'à réactivation — aucune donnée "
                "ni aucun statut ne sera modifié. Voulez-vous vraiment continuer ?",
            ):
                return False

        try:
            self._settings_service.set_rental_module_enabled(enabled)
            QMessageBox.information(
                self, "Paramètres enregistrés",
                "Le module Location a été mis à jour. Ce changement prendra effet à la "
                "prochaine ouverture de la fenêtre principale.",
            )
        except AppError as exc:
            QMessageBox.warning(self, "Enregistrement refusé", str(exc))
            return False
        self._load_modules_into_form()
        return True

    # -- récupération administrateur --------------------------------------------

    def _build_security_group(self) -> QGroupBox:
        group = QGroupBox("Sécurité — récupération administrateur", self)
        layout = QVBoxLayout(group)

        notice = QLabel(
            "Génère un code de récupération à usage unique pour votre propre "
            "compte, utilisable depuis l'écran de connexion en cas de mot de "
            "passe oublié. Régénérer un code invalide immédiatement le précédent.",
            self,
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        can_manage = self._permissions.has_permission("ADMIN_RECOVERY_MANAGE")
        self.generate_recovery_code_button = QPushButton("Générer un nouveau code de récupération", self)
        self.generate_recovery_code_button.setEnabled(can_manage)
        layout.addWidget(self.generate_recovery_code_button)

        self.generate_recovery_code_button.clicked.connect(self._on_generate_recovery_code_clicked)

        return group

    def _on_generate_recovery_code_clicked(self) -> None:
        if not confirm_action(
            self, "Confirmation",
            "Générer un nouveau code de récupération ? Le code actuel (s'il en existe un) sera "
            "immédiatement invalidé.",
        ):
            return
        self._generate_recovery_code()

    def _generate_recovery_code(self) -> Optional[str]:
        """Isolé de ``_on_generate_recovery_code_clicked`` pour rester
        testable sans boîte de confirmation modale (même principe que
        ``_clear_logo``)."""
        try:
            code = self._account_recovery_service.generate_code()
        except AppError as exc:
            QMessageBox.warning(self, "Génération refusée", str(exc))
            return None
        RecoveryCodeDisplayDialog(code, parent=self).exec()
        return code

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
