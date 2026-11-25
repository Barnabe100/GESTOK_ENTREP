"""Page Sauvegardes (administration) : configuration, protection externe,
sauvegarde manuelle, restauration, historique.

Toute action passe par :class:`BackupService`/:class:`ExternalBackupService`,
qui revérifient la permission côté service ; les boutons ne sont désactivés
ici que par confort d'usage.

Deux chemins de restauration, délibérément complémentaires et jamais une
logique dupliquée (tous deux appellent ``BackupService.restore_backup``) :
le bouton « Restaurer la sauvegarde sélectionnée » ne propose que des
sauvegardes déjà listées dans l'historique combiné (locales + externes,
reconnues par leur nom) — le chemin courant, le plus sûr, pour cette
installation ; l'« Assistant de restauration » (voir
``app.views.backup_restore_wizard_dialog``) expose en plus un sélecteur de
fichier libre, nécessaire pour restaurer depuis un support externe sur un
poste tout juste installé n'ayant encore aucun historique local (Mission
« Sauvegarde automatique et restauration », §3.4/§7) — le service revérifie
de toute façon indépendamment le fichier choisi (intégrité, compatibilité)
avant toute restauration réelle, jamais une confiance aveugle dans le
chemin fourni.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.backups import archive_manifest
from app.services.backups.archive_encryption import EncryptionKeyAlreadyConfiguredError
from app.services.backups.backup_service import BackupConfig, BackupService, FREQUENCY_DAILY, FREQUENCY_WEEKLY
from app.services.backups.external_backup_service import (
    MAX_RETENTION,
    MIN_RETENTION,
    ExternalBackupConfig,
    ExternalBackupService,
)
from app.services.system.data_reset_service import DataResetService
from app.utils.exceptions import AppError
from app.views.background_task import BackgroundTask
from app.views.backup_details_dialog import BackupDetailsDialog
from app.views.backup_restore_wizard_dialog import BackupRestoreWizardDialog
from app.views.common import confirm_action
from app.views.data_reset_confirm_dialog import DataResetConfirmDialog
from app.views.design_system import COLOR_DANGER, COLOR_SUCCESS, COLOR_TEXT_SECONDARY, qcolor
from app.views.loading_overlay import LoadingOverlay

_FREQUENCY_LABELS = {FREQUENCY_DAILY: "Quotidienne", FREQUENCY_WEEKLY: "Hebdomadaire"}
_FREQUENCY_BY_LABEL = {label: value for value, label in _FREQUENCY_LABELS.items()}

# Mission « Sauvegarde automatique et restauration », §3.3 : « Type » (locale
# ou externe) et « Emplacement » s'ajoutent à l'historique déjà existant —
# aucune colonne déjà présente n'est retirée.
_HISTORY_COLUMNS = ["Type", "Moteur", "Date", "Nom", "Taille", "Statut", "Emplacement"]

_SOURCE_LOCAL = "Locale"
_SOURCE_EXTERNAL = "Externe"

# Lot E (§E.3/E.4) : jamais présenter une sauvegarde d'un moteur comme celle
# de l'autre — libellé et description de format distincts, affichés aussi
# bien dans l'historique que dans le bandeau « moteur actif ».
_ENGINE_LABELS = {"sqlite": "SQLite", "postgresql": "PostgreSQL"}
_ENGINE_DESCRIPTIONS = {
    "sqlite": "Fichier de base SQLite (.db), copié par l'API de sauvegarde en ligne.",
    "postgresql": "Archive pg_dump au format personnalisé (.dump) — nécessite pg_dump/pg_restore sur ce poste.",
}


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("o", "Ko", "Mo", "Go"):
        if size < 1024 or unit == "Go":
            return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} o"


class BackupsPage(QWidget):
    def __init__(
        self,
        backup_service: BackupService,
        permission_service: PermissionService,
        data_reset_service: Optional[DataResetService] = None,
        external_backup_service: Optional[ExternalBackupService] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._backup_service = backup_service
        self._permissions = permission_service
        self._data_reset_service = data_reset_service
        self._external_backup_service = external_backup_service
        self._history_entries: list = []
        self._selected_media_root: Optional[str] = None
        # Correctif revue finale (Point 3) : référence à l'opération
        # d'arrière-plan en cours (voir BackgroundTask) — None hors
        # opération, utilisée pour empêcher un second lancement pendant
        # qu'une sauvegarde/restauration est déjà en cours.
        self._backup_task: Optional[BackgroundTask] = None
        self._restore_task: Optional[BackgroundTask] = None
        self._external_copy_task: Optional[BackgroundTask] = None
        # Assistant de restauration (§3.4) : dialogue modal optionnel,
        # suivi ici uniquement pour que ``has_active_background_task``
        # reste vrai tant qu'une restauration qu'il a lancée tourne encore
        # (voir BackupRestoreWizardDialog.has_active_background_task).
        self._restore_wizard_dialog: Optional[BackupRestoreWizardDialog] = None

        try:
            self._active_engine = backup_service.active_engine()
        except AppError:
            self._active_engine = "sqlite"

        try:
            # Jamais le mot de passe (voir BackupService.active_postgresql_target) ;
            # ``None`` en mode SQLite ou si la permission/la configuration
            # manque — l'affichage se limite alors au nom du moteur (Lot E.7, §E.7.2).
            self._active_postgresql_target = backup_service.active_postgresql_target()
        except AppError:
            self._active_postgresql_target = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Zone défilante (régression constatée Mission 3, §2) : les cinq
        # zones de cet écran (moteur actif, configuration automatique,
        # actions, historique, zone dangereuse) dépassent la hauteur
        # disponible à 1366×768 une fois les espacements de la Mission 2
        # appliqués — sans défilement, le `QStackedWidget` de MainWindow
        # (voir page_stack) ne scrolle jamais lui-même, et le contenu en
        # excédent est simplement rogné (champs de configuration et lignes
        # d'historique invisibles). Même principe déjà établi dans
        # ``SettingsPage`` pour la même raison : jamais de champ supprimé,
        # seulement rendu accessible par défilement.
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)
        # Espacement resserré (§2.3 : cinq zones à faire tenir sur
        # 1366×768 sans sacrifier ni les paramètres, ni l'historique) —
        # reste nettement plus aéré que l'état d'avant Mission 2.
        content_layout.setSpacing(10)

        content_layout.addWidget(self._build_engine_group())
        content_layout.addWidget(self._build_config_group())
        content_layout.addLayout(self._build_actions_row())
        content_layout.addWidget(self._build_external_group())
        history_title = QLabel("Historique des sauvegardes", self)
        history_title.setProperty("role", "sectionTitle")
        content_layout.addWidget(history_title)
        content_layout.addWidget(self._build_history_table())
        content_layout.addWidget(self._build_danger_zone_group())

        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        # Phase amélioration UX, point 4 : voile de chargement pendant une
        # sauvegarde/restauration manuelle (opérations potentiellement
        # longues côté pg_dump/pg_restore) — créé après le reste de la mise
        # en page pour recouvrir tout l'écran, y compris les boutons.
        self._loading_overlay = LoadingOverlay(self)

        self._load_config_into_form()
        self._load_external_config_into_form()
        self.refresh_history()

    # -- coordination avec MainWindow (correctif revue finale) ---------------

    def has_active_background_task(self) -> bool:
        """Hook reconnu par ``MainWindow`` (voir
        ``_pages_with_active_background_task``, consulté avant toute
        déconnexion ou fermeture) : ``True`` tant qu'une sauvegarde ou une
        restauration tourne encore dans un ``BackgroundTask`` — y compris
        si cette page n'est plus celle actuellement affichée (changer
        d'écran ne détruit jamais une page, voir ``QStackedWidget`` : la
        page et son opération continuent d'exister en arrière-plan).
        Détruire cette page ou la fenêtre tant que ceci renvoie ``True``
        reproduirait le défaut corrigé par ce lot (``QThread: Destroyed
        while thread is still running``)."""
        return (
            self._backup_task is not None
            or self._restore_task is not None
            or self._external_copy_task is not None
            or (
                self._restore_wizard_dialog is not None
                and self._restore_wizard_dialog.has_active_background_task()
            )
        )

    # -- moteur actif (Lot E, §E.4) ------------------------------------------------

    def _build_engine_group(self) -> QGroupBox:
        group = QGroupBox("Moteur de base de données actif", self)
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self.active_engine_label = QLabel(_ENGINE_LABELS.get(self._active_engine, self._active_engine), self)
        self.active_engine_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #172B4D;")
        layout.addWidget(self.active_engine_label)

        # Lot E.7, §E.7.2 : identifie la base précise (hôte/port/base),
        # jamais seulement le nom du moteur — jamais le mot de passe, jamais
        # un champ permettant de choisir une autre base depuis cet écran
        # (lecture seule de la configuration déjà active, voir
        # BackupService.active_postgresql_target).
        self.active_target_label = QLabel("", self)
        self.active_target_label.setWordWrap(True)
        self.active_target_label.setProperty("role", "secondary")
        if self._active_postgresql_target is not None:
            self.active_target_label.setText(self._active_postgresql_target.label())
            layout.addWidget(self.active_target_label)

        description = QLabel(
            _ENGINE_DESCRIPTIONS.get(self._active_engine, ""), self,
        )
        description.setWordWrap(True)
        description.setProperty("role", "secondary")
        layout.addWidget(description)
        return group

    # -- configuration --------------------------------------------------------

    def _build_config_group(self) -> QGroupBox:
        group = QGroupBox("Configuration de la sauvegarde automatique", self)
        form = QFormLayout(group)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)

        self.auto_enabled_checkbox = QCheckBox("Activer la sauvegarde automatique", self)
        form.addRow(self.auto_enabled_checkbox)

        self.frequency_combo = QComboBox(self)
        self.frequency_combo.addItems([_FREQUENCY_LABELS[FREQUENCY_DAILY], _FREQUENCY_LABELS[FREQUENCY_WEEKLY]])
        self.frequency_combo.setMinimumWidth(180)
        form.addRow("Fréquence", self.frequency_combo)

        self.time_edit = QLineEdit(self)
        self.time_edit.setPlaceholderText("HH:MM")
        self.time_edit.setMinimumWidth(100)
        self.time_edit.setMaximumWidth(140)
        form.addRow("Heure d'exécution", self.time_edit)

        destination_row = QHBoxLayout()
        destination_row.setSpacing(10)
        self.destination_edit = QLineEdit(self)
        self.destination_edit.setMinimumWidth(260)
        destination_row.addWidget(self.destination_edit)
        self.browse_button = QPushButton("Parcourir…", self)
        destination_row.addWidget(self.browse_button)
        form.addRow("Dossier de destination", destination_row)

        self.retention_spin = QSpinBox(self)
        self.retention_spin.setRange(1, 999)
        self.retention_spin.setMinimumWidth(100)
        form.addRow("Sauvegardes à conserver", self.retention_spin)

        # Mission corrective « Fiabilisation du module de sauvegarde »,
        # §3.1 : cette case n'existait jusqu'ici dans aucun écran — sans
        # elle, ``encryption_enabled`` retombait systématiquement à sa
        # valeur par défaut (False) à chaque enregistrement de CETTE MÊME
        # configuration, puisque ``_save_config`` ne la transmettait jamais
        # (voir l'audit ayant motivé cette mission). Son activation reste
        # irréversible en pratique sans la clé : avertissement explicite
        # avant la première activation, voir ``_on_encryption_enabled_toggled``.
        self.encryption_enabled_checkbox = QCheckBox("Chiffrer les sauvegardes (avancé)", self)
        form.addRow(self.encryption_enabled_checkbox)

        can_configure = self._permissions.has_permission("BACKUP_CREATE")
        for widget in (
            self.auto_enabled_checkbox, self.frequency_combo, self.time_edit,
            self.destination_edit, self.browse_button, self.retention_spin,
            self.encryption_enabled_checkbox,
        ):
            widget.setEnabled(can_configure)

        self.save_config_button = QPushButton("Enregistrer", self)
        self.save_config_button.setProperty("variant", "primary")
        self.save_config_button.setEnabled(can_configure)
        form.addRow(self.save_config_button)

        # §3.1 : transfert de la clé vers un autre ordinateur — permission
        # dédiée BACKUP_ENCRYPTION_MANAGE, distincte de BACKUP_CREATE
        # (opération suffisamment sensible pour son propre contrôle d'accès
        # et sa propre trace d'audit). « Importer… » reste accessible même
        # si le chiffrement est désactivé sur ce poste : c'est précisément
        # le cas d'un poste neuf préparant la restauration d'une archive
        # chiffrée apportée depuis un autre ordinateur.
        can_manage_encryption_key = self._permissions.has_permission("BACKUP_ENCRYPTION_MANAGE")
        key_transfer_row = QHBoxLayout()
        self.export_key_button = QPushButton("Exporter la clé de chiffrement…", self)
        self.export_key_button.setEnabled(can_manage_encryption_key)
        key_transfer_row.addWidget(self.export_key_button)
        self.import_key_button = QPushButton("Importer la clé de chiffrement…", self)
        self.import_key_button.setEnabled(can_manage_encryption_key)
        key_transfer_row.addWidget(self.import_key_button)
        self.test_key_button = QPushButton("Tester la clé sur une archive…", self)
        self.test_key_button.setEnabled(self._permissions.has_permission("BACKUP_VIEW"))
        key_transfer_row.addWidget(self.test_key_button)
        form.addRow(key_transfer_row)

        self.browse_button.clicked.connect(self._on_browse_clicked)
        self.save_config_button.clicked.connect(self._on_save_config_clicked)
        self.export_key_button.clicked.connect(self._on_export_encryption_key_clicked)
        self.import_key_button.clicked.connect(self._on_import_encryption_key_clicked)
        self.test_key_button.clicked.connect(self._on_test_encryption_key_clicked)

        return group

    def _load_config_into_form(self) -> None:
        try:
            config = self._backup_service.get_config()
        except AppError:
            return
        self._apply_config_to_form(config)

    def _apply_config_to_form(self, config: BackupConfig) -> None:
        self.auto_enabled_checkbox.setChecked(config.auto_enabled)
        self.frequency_combo.setCurrentText(_FREQUENCY_LABELS.get(config.frequency, _FREQUENCY_LABELS[FREQUENCY_DAILY]))
        self.time_edit.setText(config.time_of_day)
        self.destination_edit.setText(str(config.destination))
        self.retention_spin.setValue(config.retention)
        self.encryption_enabled_checkbox.setChecked(config.encryption_enabled)

    def _on_browse_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Dossier de destination des sauvegardes", self.destination_edit.text())
        if directory:
            self.destination_edit.setText(directory)

    def _on_save_config_clicked(self) -> None:
        self._save_config()

    def _save_config(self) -> bool:
        """Isolé de ``_on_save_config_clicked`` pour rester testable sans
        dialogue modal. Transmet désormais ``encryption_enabled`` (§3.1 —
        voir le commentaire sur ``encryption_enabled_checkbox`` ci-dessus) :
        jamais d'omission qui le ferait silencieusement retomber à
        désactivé à chaque enregistrement."""
        try:
            self._backup_service.update_config(
                auto_enabled=self.auto_enabled_checkbox.isChecked(),
                frequency=_FREQUENCY_BY_LABEL.get(self.frequency_combo.currentText(), FREQUENCY_DAILY),
                time_of_day=self.time_edit.text(),
                destination=self.destination_edit.text(),
                retention=self.retention_spin.value(),
                encryption_enabled=self.encryption_enabled_checkbox.isChecked(),
            )
            QMessageBox.information(self, "Configuration enregistrée", "La configuration des sauvegardes a été enregistrée.")
        except AppError as exc:
            QMessageBox.warning(self, "Configuration refusée", str(exc))
            return False
        # §3.5 : l'heure vient peut-être de changer — signale immédiatement
        # si la tâche planifiée Windows déjà créée ne la reflète plus,
        # jamais après coup seulement au prochain rafraîchissement.
        self._refresh_task_time_sync_warning()
        return True

    # -- transfert de la clé de chiffrement (§3.1) -------------------------------

    def _on_export_encryption_key_clicked(self) -> None:
        """Rassemble les entrées via des dialogues modaux (avertissement de
        sensibilité — §3.1 : « présenter un avertissement sur la
        sensibilité de cette clé » —, mot de passe, emplacement), puis
        délègue à :meth:`_export_encryption_key`, qui reste testable sans
        aucun dialogue (même principe que ``_on_choose_media_clicked`` ->
        ``_configure_media``)."""
        if not confirm_action(
            self, "Exporter la clé de chiffrement",
            "Cette clé permet de déchiffrer TOUTES les sauvegardes chiffrées de ce poste. "
            "Conservez le fichier exporté en lieu sûr, séparément de vos sauvegardes "
            "(jamais sur la même clé USB ou le même disque), et ne le partagez qu'avec "
            "une personne de confiance. Voulez-vous continuer ?",
        ):
            return

        password, confirmed = QInputDialog.getText(
            self, "Mot de passe de protection",
            "Choisissez un mot de passe pour protéger le fichier exporté\n"
            "(nécessaire pour l'importer sur le nouvel ordinateur — ce mot de passe "
            "n'est pas enregistré, conservez-le vous-même) :",
            QLineEdit.EchoMode.Password,
        )
        if not confirmed or not password:
            return

        suggested = str(Path.home() / "StockManager_cle_chiffrement.json")
        destination, _filter = QFileDialog.getSaveFileName(
            self, "Exporter la clé de chiffrement — choisissez un emplacement séparé des sauvegardes",
            suggested,
        )
        if not destination:
            return
        self._export_encryption_key(destination, password)

    def _export_encryption_key(self, destination: str, password: str) -> bool:
        """Isolé de ``_on_export_encryption_key_clicked`` pour rester
        testable sans dialogue modal."""
        try:
            self._backup_service.export_encryption_key(destination, password)
        except AppError as exc:
            QMessageBox.warning(self, "Export refusé", str(exc))
            return False
        QMessageBox.information(
            self, "Clé exportée",
            f"La clé de chiffrement a été exportée vers « {destination} ». "
            "Conservez ce fichier et son mot de passe en lieu sûr.",
        )
        return True

    def _on_import_encryption_key_clicked(self) -> None:
        source, _filter = QFileDialog.getOpenFileName(
            self, "Importer une clé de chiffrement", "", "Fichiers de transfert de clé (*.json);;Tous les fichiers (*)",
        )
        if not source:
            return

        password, confirmed = QInputDialog.getText(
            self, "Mot de passe du fichier de transfert",
            "Mot de passe choisi lors de l'export de cette clé :",
            QLineEdit.EchoMode.Password,
        )
        if not confirmed or not password:
            return
        self._import_encryption_key(source, password)

    def _import_encryption_key(self, source: str, password: str) -> bool:
        """Isolé de ``_on_import_encryption_key_clicked`` pour rester
        testable sans les dialogues de collecte des entrées ci-dessus — la
        confirmation de remplacement, elle, reste ici (§3.1 : « ne jamais
        remplacer silencieusement une clé déjà présente »), déclenchée
        uniquement par l'échec distinctif du service dans ce cas précis,
        jamais présentée par avance à l'utilisateur quand elle ne
        s'applique pas."""
        try:
            self._backup_service.import_encryption_key(source, password)
        except EncryptionKeyAlreadyConfiguredError:
            if not confirm_action(
                self, "Remplacer la clé existante",
                "Une clé de chiffrement est déjà configurée sur ce poste. La remplacer rendra "
                "illisibles toutes les archives déjà chiffrées avec la clé actuelle. "
                "Voulez-vous vraiment la remplacer par la clé importée ?",
            ):
                return False
            try:
                self._backup_service.import_encryption_key(source, password, overwrite=True)
            except AppError as exc:
                QMessageBox.warning(self, "Import refusé", str(exc))
                return False
        except AppError as exc:
            QMessageBox.warning(self, "Import refusé", str(exc))
            return False

        QMessageBox.information(
            self, "Clé importée",
            "La clé de chiffrement a été importée avec succès. Utilisez « Tester la clé sur une "
            "archive… » pour vérifier qu'elle permet bien de déchiffrer une archive apportée de "
            "l'ancien ordinateur.",
        )
        return True

    def _on_test_encryption_key_clicked(self) -> None:
        archive_path, _filter = QFileDialog.getOpenFileName(
            self, "Sélectionner une archive chiffrée à tester", "",
            "Archives StockManager (*.db *.dump);;Tous les fichiers (*)",
        )
        if not archive_path:
            return
        self._test_encryption_key(archive_path)

    def _test_encryption_key(self, archive_path: str) -> bool:
        """Isolé de ``_on_test_encryption_key_clicked`` pour rester
        testable sans dialogue modal de sélection de fichier."""
        try:
            success = self._backup_service.test_encryption_key_against_archive(archive_path)
        except AppError as exc:
            QMessageBox.warning(self, "Test impossible", str(exc))
            return False
        if success:
            QMessageBox.information(self, "Clé valide", "Cette clé permet bien de déchiffrer l'archive sélectionnée.")
        else:
            QMessageBox.warning(
                self, "Clé invalide",
                "Cette clé ne permet pas de déchiffrer l'archive sélectionnée — mauvaise clé, "
                "archive non chiffrée, ou archive corrompue.",
            )
        return success

    # -- protection externe (Mission « Sauvegarde automatique et restauration ») -----

    def _build_external_group(self) -> QGroupBox:
        group = QGroupBox("Protection externe (clé USB / disque externe)", self)
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        can_configure = (
            self._external_backup_service is not None
            and self._permissions.has_permission("BACKUP_EXTERNAL_CONFIGURE")
        )
        can_copy = (
            self._external_backup_service is not None and self._permissions.has_permission("BACKUP_CREATE")
        )

        self.external_status_label = QLabel("", group)
        self.external_status_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.external_status_label)

        # §3.2 : rappel discret lorsque la protection externe n'est pas
        # activée — masqué dès qu'elle l'est (voir _apply_external_config_to_form).
        self.external_reminder_label = QLabel(
            "Rappel : sans protection externe, les sauvegardes restent uniquement sur le "
            "disque interne — une panne de ce disque pourrait entraîner leur perte.",
            group,
        )
        self.external_reminder_label.setWordWrap(True)
        self.external_reminder_label.setProperty("role", "secondary")
        layout.addWidget(self.external_reminder_label)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(16)

        self.external_enabled_checkbox = QCheckBox("Activer la protection externe", group)
        form.addRow(self.external_enabled_checkbox)

        media_row = QHBoxLayout()
        self.external_media_label = QLabel("Aucun support configuré.", group)
        self.external_media_label.setWordWrap(True)
        media_row.addWidget(self.external_media_label, 1)
        self.choose_media_button = QPushButton("Choisir/modifier le support…", group)
        media_row.addWidget(self.choose_media_button)
        form.addRow("Support externe", media_row)

        self.external_retention_spin = QSpinBox(group)
        self.external_retention_spin.setRange(MIN_RETENTION, MAX_RETENTION)
        self.external_retention_spin.setMinimumWidth(100)
        form.addRow("Sauvegardes externes à conserver", self.external_retention_spin)

        self.external_last_run_label = QLabel("—", group)
        form.addRow("Dernière copie", self.external_last_run_label)

        self.external_last_result_label = QLabel("—", group)
        self.external_last_result_label.setWordWrap(True)
        form.addRow("Résultat de la dernière exécution", self.external_last_result_label)

        self.external_task_status_label = QLabel("—", group)
        self.external_task_status_label.setWordWrap(True)
        form.addRow("Tâche planifiée Windows", self.external_task_status_label)

        layout.addLayout(form)

        # Mission corrective « Fiabilisation du module de sauvegarde »,
        # §3.5 : avertissement explicite si l'heure actuellement configurée
        # (section « Configuration de la sauvegarde automatique » plus
        # haut) ne correspond plus à celle réellement enregistrée dans la
        # tâche planifiée Windows — jamais laisser croire, à tort, qu'elles
        # restent synchronisées après une modification de l'heure suivie
        # d'un simple « Enregistrer » sans reconfigurer la tâche (voir
        # ``_save_config``/``_refresh_task_time_sync_warning`` ci-dessous).
        self.task_time_sync_warning_label = QLabel("", group)
        self.task_time_sync_warning_label.setWordWrap(True)
        self.task_time_sync_warning_label.setStyleSheet(f"font-weight: 600; color: {COLOR_DANGER};")
        self.task_time_sync_warning_label.setVisible(False)
        layout.addWidget(self.task_time_sync_warning_label)

        for widget in (self.external_enabled_checkbox, self.choose_media_button, self.external_retention_spin):
            widget.setEnabled(can_configure)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)
        self.save_external_config_button = QPushButton("Enregistrer", group)
        self.save_external_config_button.setProperty("variant", "primary")
        self.save_external_config_button.setEnabled(can_configure)
        buttons_row.addWidget(self.save_external_config_button)

        self.test_media_button = QPushButton("Tester l'accessibilité", group)
        self.test_media_button.setEnabled(
            self._external_backup_service is not None and self._permissions.has_permission("BACKUP_VIEW")
        )
        buttons_row.addWidget(self.test_media_button)

        self.copy_now_button = QPushButton("Copier maintenant", group)
        self.copy_now_button.setEnabled(can_copy)
        buttons_row.addWidget(self.copy_now_button)

        self.configure_task_button = QPushButton("Configurer/réparer la tâche planifiée", group)
        self.configure_task_button.setEnabled(can_configure)
        # Mission corrective « Fiabilisation du module de sauvegarde »,
        # §3.14 : cette action RECRÉE entièrement la tâche planifiée
        # Windows (voir ``ExternalBackupService.configure_scheduled_task``)
        # — toute personnalisation apportée manuellement à cette tâche
        # directement depuis le Planificateur de tâches Windows (horaire
        # modifié à la main, déclencheur supplémentaire, etc.) est donc
        # perdue et remplacée par la configuration actuelle de
        # StockManager. Jamais découvert après coup seulement : annoncé
        # ici, au survol du bouton, avant même de cliquer.
        self.configure_task_button.setToolTip(
            "Recrée entièrement la tâche planifiée Windows à partir de la configuration actuelle de "
            "StockManager. Toute personnalisation apportée manuellement à cette tâche depuis le "
            "Planificateur de tâches Windows sera perdue et remplacée."
        )
        buttons_row.addWidget(self.configure_task_button)

        self.remove_task_button = QPushButton("Supprimer la tâche planifiée", group)
        self.remove_task_button.setProperty("variant", "danger")
        self.remove_task_button.setEnabled(can_configure)
        buttons_row.addWidget(self.remove_task_button)

        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)

        self.choose_media_button.clicked.connect(self._on_choose_media_clicked)
        self.save_external_config_button.clicked.connect(self._on_save_external_config_clicked)
        self.test_media_button.clicked.connect(self._on_test_media_clicked)
        self.copy_now_button.clicked.connect(self._on_copy_now_clicked)
        self.configure_task_button.clicked.connect(self._on_configure_task_clicked)
        self.remove_task_button.clicked.connect(self._on_remove_task_clicked)

        return group

    def _load_external_config_into_form(self) -> None:
        if self._external_backup_service is None:
            self.external_status_label.setText("Protection externe non disponible.")
            self.external_reminder_label.setVisible(False)
            return
        try:
            config = self._external_backup_service.get_config()
        except AppError:
            return
        self._apply_external_config_to_form(config)
        self._refresh_scheduled_task_status()

    def _apply_external_config_to_form(self, config: ExternalBackupConfig) -> None:
        self.external_enabled_checkbox.setChecked(config.enabled)
        self.external_retention_spin.setValue(config.retention)
        self.external_media_label.setText(
            f"« {config.label} »" if config.is_configured else "Aucun support configuré."
        )
        self.external_status_label.setText(
            "Protection externe : activée" if config.enabled else "Protection externe : désactivée"
        )
        # §3.2 : rappel visible uniquement tant que la protection n'est pas activée.
        self.external_reminder_label.setVisible(not config.enabled)
        self.external_last_run_label.setText(config.last_run_at or "—")
        self.external_last_result_label.setText(config.last_result or "—")

    def _refresh_scheduled_task_status(self) -> None:
        if self._external_backup_service is None:
            return
        try:
            status = self._external_backup_service.scheduled_task_status()
        except AppError as exc:
            self.external_task_status_label.setText(f"Indisponible sur ce poste : {exc}")
            self.task_time_sync_warning_label.setVisible(False)
            return
        if not status.exists:
            self.external_task_status_label.setText("Non configurée.")
            self.task_time_sync_warning_label.setVisible(False)
            return
        self.external_task_status_label.setText(
            f"{status.status or '—'} — dernière exécution : {status.last_run_time or '—'} "
            f"(résultat : {status.last_result or '—'})"
        )
        self._refresh_task_time_sync_warning()

    def _refresh_task_time_sync_warning(self) -> None:
        """Isolé de ``_refresh_scheduled_task_status`` pour être également
        appelable juste après ``_save_config`` (§3.5 du mandat correctif) —
        jamais une exception laissée remonter ici : l'absence de retour
        fiable (ex. hors Windows) ne doit jamais faire échouer tout le
        reste du rafraîchissement de l'écran."""
        if self._external_backup_service is None:
            return
        try:
            synchronized = self._external_backup_service.is_scheduled_task_time_synchronized()
        except AppError:
            self.task_time_sync_warning_label.setVisible(False)
            return
        if synchronized is False:
            self.task_time_sync_warning_label.setText(
                "⚠ L'heure configurée ci-dessus ne correspond plus à celle enregistrée dans la "
                "tâche planifiée Windows — cliquez sur « Configurer/réparer la tâche planifiée » "
                "pour la mettre à jour, sans quoi la sauvegarde planifiée continuera de se "
                "déclencher à l'ancienne heure lorsque StockManager est fermé."
            )
            self.task_time_sync_warning_label.setVisible(True)
        else:
            self.task_time_sync_warning_label.setVisible(False)

    def _on_choose_media_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Support externe (clé USB / disque externe)", "")
        if not directory:
            return
        label, confirmed = QInputDialog.getText(
            self, "Nom du support", "Donnez un nom à ce support (ex. « Disque externe bureau ») :"
        )
        if not confirmed or not label.strip():
            return
        self._configure_media(directory, label)

    def _configure_media(self, directory: str, label: str) -> bool:
        """Isolé de ``_on_choose_media_clicked`` pour rester testable sans
        dialogues modaux."""
        try:
            config = self._external_backup_service.configure_media(Path(directory), label)
        except AppError as exc:
            QMessageBox.warning(self, "Support refusé", str(exc))
            return False
        self._apply_external_config_to_form(config)
        QMessageBox.information(self, "Support configuré", f"Le support « {label} » a été configuré avec succès.")
        return True

    def _on_save_external_config_clicked(self) -> None:
        self._save_external_config()

    def _save_external_config(self) -> bool:
        try:
            config = self._external_backup_service.update_config(
                enabled=self.external_enabled_checkbox.isChecked(),
                retention=self.external_retention_spin.value(),
            )
            self._apply_external_config_to_form(config)
            QMessageBox.information(
                self, "Configuration enregistrée", "La configuration de la protection externe a été enregistrée."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Configuration refusée", str(exc))
            return False
        return True

    def _on_test_media_clicked(self) -> None:
        self._test_media_accessible()

    def _test_media_accessible(self) -> bool:
        try:
            accessible = self._external_backup_service.test_media_accessible()
        except AppError as exc:
            QMessageBox.warning(self, "Test impossible", str(exc))
            return False
        if accessible:
            QMessageBox.information(self, "Support accessible", "Le support externe configuré est actuellement accessible.")
        else:
            QMessageBox.warning(
                self, "Support inaccessible",
                "Le support externe configuré n'est pas actuellement accessible. Vérifiez qu'il est bien branché.",
            )
        return accessible

    def _on_copy_now_clicked(self) -> None:
        # Même principe que ``_on_backup_now_clicked`` (thread d'arrière-plan,
        # voile de chargement, garde anti-double-lancement).
        if self._external_copy_task is not None:
            return
        self.copy_now_button.setEnabled(False)
        self._loading_overlay.show_with_message("Copie externe en cours…")

        def _on_success(result) -> None:
            self._finish_external_copy_task()
            self._show_external_copy_result(result)
            self.refresh_history()

        def _on_failure(exc: Exception) -> None:
            self._finish_external_copy_task()
            message = str(exc) if isinstance(exc, AppError) else f"Erreur inattendue lors de la copie externe : {exc}"
            QMessageBox.warning(self, "Copie externe refusée", message)

        self._external_copy_task = BackgroundTask(self._external_backup_service.copy_now)
        self._external_copy_task.start(_on_success, _on_failure)

    def _finish_external_copy_task(self) -> None:
        self._external_copy_task = None
        self._loading_overlay.hide_overlay()
        self.copy_now_button.setEnabled(
            self._external_backup_service is not None and self._permissions.has_permission("BACKUP_CREATE")
        )
        self._load_external_config_into_form()

    def _show_external_copy_result(self, result) -> bool:
        if result.success:
            QMessageBox.information(self, "Copie externe réussie", result.message)
        else:
            QMessageBox.warning(self, "Échec de la copie externe", result.message)
        return result.success

    def _run_external_copy_now(self) -> bool:
        """Appel direct et synchrone, isolé pour rester testable sans
        dialogue modal ni thread — même principe que ``_run_manual_backup``."""
        try:
            result = self._external_backup_service.copy_now()
        except AppError as exc:
            QMessageBox.warning(self, "Copie externe refusée", str(exc))
            return False
        success = self._show_external_copy_result(result)
        self.refresh_history()
        self._load_external_config_into_form()
        return success

    def _on_configure_task_clicked(self) -> None:
        self._configure_scheduled_task()

    def _configure_scheduled_task(self) -> bool:
        try:
            time_of_day = self._backup_service.get_config().time_of_day
            self._external_backup_service.configure_scheduled_task(time_of_day)
            QMessageBox.information(
                self, "Tâche planifiée configurée",
                "La tâche planifiée Windows a été configurée/réparée avec succès.",
            )
        except AppError as exc:
            QMessageBox.warning(self, "Configuration refusée", str(exc))
            return False
        self._refresh_scheduled_task_status()
        return True

    def _on_remove_task_clicked(self) -> None:
        if not confirm_action(
            self, "Supprimer la tâche planifiée",
            "Voulez-vous vraiment supprimer la tâche planifiée Windows ? La sauvegarde "
            "automatique et la copie externe ne s'exécuteront plus lorsque StockManager "
            "est fermé.",
        ):
            return
        self._remove_scheduled_task()

    def _remove_scheduled_task(self) -> bool:
        try:
            self._external_backup_service.remove_scheduled_task()
            QMessageBox.information(self, "Tâche supprimée", "La tâche planifiée Windows a été supprimée.")
        except AppError as exc:
            QMessageBox.warning(self, "Suppression refusée", str(exc))
            return False
        self._refresh_scheduled_task_status()
        return True

    # -- actions ----------------------------------------------------------------

    def _build_actions_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self.backup_now_button = QPushButton("Sauvegarder maintenant", self)
        self.backup_now_button.setProperty("variant", "primary")
        self.backup_now_button.setEnabled(self._permissions.has_permission("BACKUP_CREATE"))
        row.addWidget(self.backup_now_button)

        # Restauration : action sensible mais non destructive en soi (une
        # sauvegarde de sécurité de l'état actuel est créée automatiquement
        # avant tout remplacement, voir _on_restore_clicked) — orange, pas
        # rouge (§7.3 : le rouge est réservé aux actions réellement
        # destructives, ex. réinitialisation des données métier ci-dessous).
        self.restore_button = QPushButton("Restaurer la sauvegarde sélectionnée", self)
        self.restore_button.setProperty("variant", "warning")
        self.restore_button.setEnabled(False)
        row.addWidget(self.restore_button)

        # §3.3 : actions pertinentes sur la ligne d'historique sélectionnée —
        # jamais de suppression manuelle proposée ici (voir le mandat : « ne
        # pas proposer une suppression manuelle sans vérifier les
        # conséquences sur la protection des données »).
        self.view_details_button = QPushButton("Consulter les détails", self)
        self.view_details_button.setEnabled(False)
        row.addWidget(self.view_details_button)

        self.export_button = QPushButton("Exporter…", self)
        self.export_button.setEnabled(False)
        row.addWidget(self.export_button)

        # §3.4 : assistant de restauration — chemin complémentaire au bouton
        # « Restaurer la sauvegarde sélectionnée » ci-dessus (qui ne propose
        # que l'historique déjà reconnu de cette installation) : permet de
        # parcourir n'importe quel emplacement accessible et de restaurer
        # depuis une archive externe, y compris sur un poste tout juste
        # installé n'ayant encore aucun historique local (§7 du mandat).
        self.restore_wizard_button = QPushButton("Assistant de restauration…", self)
        self.restore_wizard_button.setEnabled(self._permissions.has_permission("BACKUP_RESTORE"))
        row.addWidget(self.restore_wizard_button)

        row.addStretch(1)

        self.backup_now_button.clicked.connect(self._on_backup_now_clicked)
        self.restore_button.clicked.connect(self._on_restore_clicked)
        self.view_details_button.clicked.connect(self._on_view_details_clicked)
        self.export_button.clicked.connect(self._on_export_clicked)
        self.restore_wizard_button.clicked.connect(self._on_open_restore_wizard_clicked)
        return row

    def _on_open_restore_wizard_clicked(self) -> None:
        if self._restore_wizard_dialog is not None:
            return
        dialog = BackupRestoreWizardDialog(
            self._backup_service, parent=self, external_backup_service=self._external_backup_service,
        )
        self._restore_wizard_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._restore_wizard_dialog = None
        if dialog.result() == QDialog.DialogCode.Accepted:
            self.refresh_history()

    def _on_backup_now_clicked(self) -> None:
        # Correctif revue finale (Point 3) : l'appel au service s'exécute
        # désormais dans un thread d'arrière-plan (voir BackgroundTask et
        # sa docstring pour la justification de sécurité — aucune session
        # SQLAlchemy existante n'est déplacée, BackupService.create_manual_backup
        # ouvre et referme la sienne à l'intérieur de l'appel), afin que
        # la boucle d'évènements Qt continue de tourner pendant
        # pg_dump/pg_restore : le voile reste réellement animé, et la
        # fenêtre ne risque plus d'être signalée « Ne répond pas » par
        # Windows sur une sauvegarde longue. Garde contre un second
        # lancement : ``self._backup_task`` n'est jamais ``None`` pendant
        # qu'une opération est déjà en cours.
        if self._backup_task is not None:
            return
        self.backup_now_button.setEnabled(False)
        self._loading_overlay.show_with_message("Sauvegarde en cours…")

        def _on_success(result) -> None:
            self._finish_backup_task()
            if self._show_backup_result(result):
                self.refresh_history()

        def _on_failure(exc: Exception) -> None:
            self._finish_backup_task()
            message = str(exc) if isinstance(exc, AppError) else f"Erreur inattendue lors de la sauvegarde : {exc}"
            QMessageBox.warning(self, "Sauvegarde refusée", message)

        self._backup_task = BackgroundTask(self._backup_service.create_manual_backup)
        self._backup_task.start(_on_success, _on_failure)

    def _finish_backup_task(self) -> None:
        self._backup_task = None
        self._loading_overlay.hide_overlay()
        self.backup_now_button.setEnabled(self._permissions.has_permission("BACKUP_CREATE"))

    def _show_backup_result(self, result) -> bool:
        """Partagé entre ``_run_manual_backup`` (appel direct, synchrone,
        conservé pour les tests existants) et le callback de succès de
        ``_on_backup_now_clicked`` (appel asynchrone) — un seul endroit
        pour le texte affiché à l'utilisateur, jamais dupliqué."""
        if result.success:
            QMessageBox.information(self, "Sauvegarde réussie", result.message)
        else:
            QMessageBox.warning(self, "Échec de la sauvegarde", result.message)
        return result.success

    def _run_manual_backup(self) -> bool:
        """Appel direct et synchrone, isolé de ``_on_backup_now_clicked``
        pour rester testable sans dialogue modal ni thread — ``_on_backup_now_clicked``
        utilise désormais un thread d'arrière-plan (voir ``BackgroundTask``)
        mais appelle le même service et affiche le même résultat via
        ``_show_backup_result``."""
        try:
            result = self._backup_service.create_manual_backup()
        except AppError as exc:
            QMessageBox.warning(self, "Sauvegarde refusée", str(exc))
            return False
        return self._show_backup_result(result)

    # -- historique ---------------------------------------------------------------

    def _build_history_table(self) -> QTableWidget:
        self.history_table = QTableWidget(0, len(_HISTORY_COLUMNS), self)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setHorizontalHeaderLabels(_HISTORY_COLUMNS)
        header = self.history_table.horizontalHeader()
        header.setStretchLastSection(True)
        # Largeurs adaptées au contenu réel de chaque colonne (§7.4/§3.3) :
        # Type/Moteur/Date/Taille/Statut tiennent sur un contenu court et
        # fixe, Nom (potentiellement long) s'étire ; Emplacement s'étire
        # aussi (dernière colonne, voir setStretchLastSection ci-dessus).
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.verticalHeader().setDefaultSectionSize(30)
        # §2.2 : au moins cinq sauvegardes visibles simultanément sans avoir
        # à faire défiler le tableau lui-même — en-tête (~32px) + 5 lignes
        # (30px) + bordures ; la barre de défilement verticale propre à ce
        # tableau (comportement par défaut de QTableWidget) prend ensuite le
        # relais pour les sauvegardes au-delà des cinq premières visibles.
        self.history_table.setMinimumHeight(32 + 5 * 30 + 12)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.itemSelectionChanged.connect(self._update_restore_button)
        self.history_table.itemSelectionChanged.connect(self._update_history_action_buttons)
        return self.history_table

    def refresh_history(self) -> None:
        """Historique combiné (§3.3) : sauvegardes locales
        (``BackupService.list_backups``) et externes
        (``ExternalBackupService.list_external_backups``, vide si le
        support n'est pas actuellement accessible — jamais une erreur dans
        ce cas), chaque entrée gardant la trace de son origine (colonne
        « Type »)."""
        combined: list[tuple[str, object]] = []
        try:
            combined.extend((_SOURCE_LOCAL, entry) for entry in self._backup_service.list_backups())
        except AppError:
            pass
        if self._external_backup_service is not None:
            try:
                combined.extend(
                    (_SOURCE_EXTERNAL, entry) for entry in self._external_backup_service.list_external_backups()
                )
            except AppError:
                pass
        combined.sort(key=lambda pair: pair[1].info.name, reverse=True)

        self._history_entries = combined
        self.history_table.setRowCount(len(combined))
        for row, (source, entry) in enumerate(combined):
            info = entry.info
            try:
                verification = self._backup_service.verify_backup_file(info.path)
                statut = "Valide" if verification.valid else "Invalide"
            except AppError:
                statut = "?"

            self.history_table.setItem(row, 0, QTableWidgetItem(source))
            self.history_table.setItem(row, 1, QTableWidgetItem(_ENGINE_LABELS.get(entry.engine, entry.engine)))
            # §2.2 : format français, cohérent avec le reste de l'application
            # depuis la Mission 2 (dd/MM/yyyy) — jamais le format ISO brut,
            # moins lisible au premier coup d'œil.
            self.history_table.setItem(row, 2, QTableWidgetItem(info.modified_at.strftime("%d/%m/%Y %H:%M:%S")))
            name_item = QTableWidgetItem(info.name)
            name_item.setToolTip(info.name)
            self.history_table.setItem(row, 3, name_item)
            self.history_table.setItem(row, 4, QTableWidgetItem(_format_size(info.size_bytes)))
            statut_item = QTableWidgetItem(statut)
            # Couleurs de statut cohérentes (§2.2) : vert = valide, rouge =
            # invalide, gris neutre pour le cas « indéterminé » (``?``, une
            # erreur de vérification n'est ni un succès ni un échec confirmé).
            if statut == "Valide":
                statut_item.setForeground(qcolor(COLOR_SUCCESS))
            elif statut == "Invalide":
                statut_item.setForeground(qcolor(COLOR_DANGER))
            else:
                statut_item.setForeground(qcolor(COLOR_TEXT_SECONDARY))
            font = statut_item.font()
            font.setBold(True)
            statut_item.setFont(font)
            self.history_table.setItem(row, 5, statut_item)
            location_item = QTableWidgetItem(str(info.path.parent))
            location_item.setToolTip(str(info.path))
            self.history_table.setItem(row, 6, location_item)

        self._update_restore_button()
        self._update_history_action_buttons()

    def _selected_entry(self):
        """Retourne ``(source, entry)`` (voir :meth:`refresh_history`), ou
        ``None`` si rien n'est sélectionné."""
        selected = self.history_table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        if row >= len(self._history_entries):
            return None
        return self._history_entries[row]

    def _update_restore_button(self) -> None:
        can_restore = self._permissions.has_permission("BACKUP_RESTORE")
        selection = self._selected_entry()
        # §E.3 : ne jamais proposer la restauration d'une sauvegarde d'un
        # moteur différent du moteur actif — refusée de toute façon côté
        # service (voir BackupService.restore_backup), mais déjà empêchée
        # ici pour ne pas laisser croire que l'opération est possible.
        matches_active_engine = selection is not None and selection[1].engine == self._active_engine
        self.restore_button.setEnabled(can_restore and matches_active_engine)

    def _update_history_action_buttons(self) -> None:
        has_selection = self._selected_entry() is not None
        self.view_details_button.setEnabled(has_selection)
        self.export_button.setEnabled(has_selection and self._permissions.has_permission("BACKUP_VIEW"))

    # -- consulter les détails / exporter (§3.3) -------------------------------------

    def _on_view_details_clicked(self) -> None:
        selection = self._selected_entry()
        if selection is None:
            return
        source, entry = selection
        BackupDetailsDialog(entry, source, self._backup_service, parent=self).exec()

    def _on_export_clicked(self) -> None:
        selection = self._selected_entry()
        if selection is None:
            return
        _source, entry = selection
        suggested = str(Path.home() / entry.info.name)
        destination, _filter = QFileDialog.getSaveFileName(self, "Exporter la sauvegarde", suggested)
        if not destination:
            return
        self._export_entry_to(entry, destination)

    def _export_entry_to(self, entry, destination: str) -> bool:
        """Isolé de ``_on_export_clicked`` pour rester testable sans
        dialogue modal de sélection de fichier — copie l'archive ET son
        manifeste (s'il existe) vers tout emplacement choisi par
        l'utilisateur (clé USB, disque externe, autre dossier — §C du
        mandat), indépendamment de toute politique de rétention."""
        try:
            destination_path = Path(destination)
            shutil.copyfile(entry.info.path, destination_path)
            manifest_source = archive_manifest.manifest_path_for(entry.info.path)
            if manifest_source.is_file():
                shutil.copyfile(manifest_source, archive_manifest.manifest_path_for(destination_path))
        except OSError as exc:
            QMessageBox.warning(self, "Export refusé", f"Impossible d'exporter la sauvegarde : {exc}")
            return False
        QMessageBox.information(self, "Export réussi", f"La sauvegarde a été exportée vers « {destination} ».")
        return True

    def _on_restore_clicked(self) -> None:
        selection = self._selected_entry()
        if selection is None:
            return
        _source, entry = selection
        if entry.engine != self._active_engine:
            QMessageBox.warning(
                self, "Restauration impossible",
                f"Cette sauvegarde provient du moteur {_ENGINE_LABELS.get(entry.engine, entry.engine)}, "
                f"alors que le moteur actif est {_ENGINE_LABELS.get(self._active_engine, self._active_engine)}.",
            )
            return
        # Lot E.7, §E.7.2 : la base précise (hôte/port/base) apparaît dans la
        # confirmation lorsqu'elle est connue — jamais seulement le nom du
        # moteur — pour qu'un administrateur gérant plusieurs environnements
        # sache exactement laquelle sera affectée avant de confirmer.
        target_clause = ""
        if entry.engine == "postgresql" and self._active_postgresql_target is not None:
            target_clause = f"Base ciblée : {self._active_postgresql_target.label()}\n\n"
        if not confirm_action(
            self, "Confirmation de restauration",
            f"Voulez-vous vraiment restaurer cette sauvegarde {_ENGINE_LABELS.get(entry.engine, entry.engine)} ?\n\n"
            f"{target_clause}"
            "La base de données actuelle sera remplacée (une sauvegarde de "
            "sécurité de l'état actuel sera créée automatiquement avant toute "
            "modification). L'application devra être redémarrée après une "
            "restauration réussie. Cette action est irréversible sans cette "
            "sauvegarde de sécurité.",
        ):
            return
        # Correctif revue finale (Point 3) : même principe que pour la
        # sauvegarde manuelle (voir ``_on_backup_now_clicked``) — exécution
        # dans un thread d'arrière-plan pour que le voile reste réellement
        # animé et l'interface réactive pendant un ``pg_restore`` long.
        if self._restore_task is not None:
            return
        self.restore_button.setEnabled(False)
        self._loading_overlay.show_with_message("Restauration en cours…")
        backup_path = str(entry.info.path)

        def _on_success(result) -> None:
            self._finish_restore_task()
            self._show_restore_result(result)

        def _on_failure(exc: Exception) -> None:
            self._finish_restore_task()
            message = str(exc) if isinstance(exc, AppError) else f"Erreur inattendue lors de la restauration : {exc}"
            QMessageBox.warning(self, "Restauration refusée", message)

        self._restore_task = BackgroundTask(lambda: self._backup_service.restore_backup(backup_path))
        self._restore_task.start(_on_success, _on_failure)

    def _finish_restore_task(self) -> None:
        self._restore_task = None
        self._loading_overlay.hide_overlay()
        self._update_restore_button()

    def _show_restore_result(self, result) -> bool:
        """Partagé entre ``_restore_selected`` (appel direct, synchrone,
        conservé pour les tests existants) et le callback de succès de
        ``_on_restore_clicked`` (appel asynchrone)."""
        if result.success:
            QMessageBox.information(
                self, "Restauration réussie",
                result.message + "\n\nVeuillez fermer et relancer StockManager Desktop maintenant.",
            )
            if result.destination_warning:
                self._offer_to_reconfigure_destination(result.destination_warning)
        else:
            QMessageBox.critical(self, "Échec de la restauration", result.message)
        return result.success

    def _offer_to_reconfigure_destination(self, warning: str) -> None:
        """Mission corrective « Fiabilisation du module de sauvegarde »,
        §3.11 : la sauvegarde restaurée désignait un dossier de
        destination inaccessible sur CE poste (typiquement un changement
        d'ordinateur, voir ``BackupService.RestoreResult.destination_warning``)
        — proposé immédiatement, plutôt que laissé à découvrir seulement
        au prochain échec de sauvegarde planifiée."""
        if not confirm_action(
            self, "Dossier de destination à reconfigurer",
            warning + "\n\nVoulez-vous choisir un nouveau dossier de destination maintenant ?",
        ):
            return
        directory = QFileDialog.getExistingDirectory(self, "Nouveau dossier de destination des sauvegardes", "")
        if not directory:
            return
        config = self._backup_service.get_config()
        try:
            self._backup_service.update_config(
                auto_enabled=config.auto_enabled, frequency=config.frequency, time_of_day=config.time_of_day,
                destination=directory, retention=config.retention, encryption_enabled=config.encryption_enabled,
            )
        except AppError as exc:
            QMessageBox.warning(self, "Configuration refusée", str(exc))
            return
        self._apply_config_to_form(self._backup_service.get_config())
        QMessageBox.information(self, "Dossier mis à jour", "Le nouveau dossier de destination a été enregistré.")

    def _restore_selected(self, backup_path: str) -> bool:
        """Appel direct et synchrone, isolé de ``_on_restore_clicked`` pour
        rester testable sans boîte de dialogue modale ni thread —
        ``_on_restore_clicked`` utilise désormais un thread d'arrière-plan
        (voir ``BackgroundTask``) mais appelle le même service et affiche
        le même résultat via ``_show_restore_result``."""
        try:
            result = self._backup_service.restore_backup(backup_path)
        except AppError as exc:
            QMessageBox.warning(self, "Restauration refusée", str(exc))
            return False
        return self._show_restore_result(result)

    # -- réinitialisation des données métier (§3 du lot) -----------------------------

    def _build_danger_zone_group(self) -> QGroupBox:
        group = QGroupBox("Zone dangereuse — Réinitialisation des données métier", self)
        # Accent rouge discret (§7.5) : la zone doit se distinguer visuellement
        # du reste de l'écran avant même la lecture du texte, sans jamais
        # modifier le mécanisme de réinitialisation lui-même.
        group.setProperty("variant", "danger")
        layout = QVBoxLayout(group)

        description = QLabel(
            "Réservé à l'Administrateur. Permet de repartir avec une base métier "
            "propre après une période de test client, sans désinstaller "
            "StockManager. Une sauvegarde de sécurité est créée et vérifiée "
            "automatiquement avant toute suppression.",
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.reset_business_data_button = QPushButton("Réinitialiser les données métier…", self)
        self.reset_business_data_button.setProperty("variant", "danger")
        can_reset = (
            self._data_reset_service is not None
            and self._permissions.has_permission("SYSTEM_RESET_BUSINESS_DATA")
        )
        self.reset_business_data_button.setEnabled(can_reset)
        self.reset_business_data_button.clicked.connect(self._on_reset_business_data_clicked)
        layout.addWidget(self.reset_business_data_button)

        return group

    def _on_reset_business_data_clicked(self) -> None:
        if self._data_reset_service is None:
            return
        dialog = DataResetConfirmDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_reset_business_data()

    def _run_reset_business_data(self) -> bool:
        """Isolé de ``_on_reset_business_data_clicked`` pour rester testable
        sans dialogue modal de confirmation."""
        try:
            result = self._data_reset_service.reset_business_data()
        except AppError as exc:
            QMessageBox.critical(self, "Réinitialisation refusée", str(exc))
            return False
        QMessageBox.information(self, "Réinitialisation réussie", result.message)
        self.refresh_history()
        return True
