"""Page Sauvegardes (administration) : configuration, sauvegarde manuelle,
restauration, historique.

Toute action passe par :class:`BackupService`, qui revérifie la permission
côté service ; les boutons ne sont désactivés ici que par confort d'usage.
La restauration ne propose que des sauvegardes déjà listées dans
l'historique (fichiers créés par StockManager, reconnus par leur nom) plutôt
qu'un sélecteur de fichier libre — évite d'exposer la restauration
« aveugle » d'un fichier arbitraire (§10 du cahier des charges de cette
phase) ; le service revérifie de toute façon indépendamment le fichier
choisi avant toute restauration.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.backups.backup_service import BackupConfig, BackupService, FREQUENCY_DAILY, FREQUENCY_WEEKLY
from app.services.system.data_reset_service import DataResetService
from app.utils.exceptions import AppError
from app.views.background_task import BackgroundTask
from app.views.common import confirm_action
from app.views.data_reset_confirm_dialog import DataResetConfirmDialog
from app.views.loading_overlay import LoadingOverlay

_FREQUENCY_LABELS = {FREQUENCY_DAILY: "Quotidienne", FREQUENCY_WEEKLY: "Hebdomadaire"}
_FREQUENCY_BY_LABEL = {label: value for value, label in _FREQUENCY_LABELS.items()}

_HISTORY_COLUMNS = ["Moteur", "Date", "Nom", "Taille", "Statut"]

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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._backup_service = backup_service
        self._permissions = permission_service
        self._data_reset_service = data_reset_service
        self._history_entries: list = []
        # Correctif revue finale (Point 3) : référence à l'opération
        # d'arrière-plan en cours (voir BackgroundTask) — None hors
        # opération, utilisée pour empêcher un second lancement pendant
        # qu'une sauvegarde/restauration est déjà en cours.
        self._backup_task: Optional[BackgroundTask] = None
        self._restore_task: Optional[BackgroundTask] = None

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

        layout.addWidget(self._build_engine_group())
        layout.addWidget(self._build_config_group())
        layout.addLayout(self._build_actions_row())
        layout.addWidget(QLabel("Historique des sauvegardes", self))
        layout.addWidget(self._build_history_table())
        layout.addWidget(self._build_danger_zone_group())

        # Phase amélioration UX, point 4 : voile de chargement pendant une
        # sauvegarde/restauration manuelle (opérations potentiellement
        # longues côté pg_dump/pg_restore) — créé après le reste de la mise
        # en page pour recouvrir tout l'écran, y compris les boutons.
        self._loading_overlay = LoadingOverlay(self)

        self._load_config_into_form()
        self.refresh_history()

    # -- moteur actif (Lot E, §E.4) ------------------------------------------------

    def _build_engine_group(self) -> QGroupBox:
        group = QGroupBox("Moteur de base de données actif", self)
        layout = QVBoxLayout(group)
        self.active_engine_label = QLabel(_ENGINE_LABELS.get(self._active_engine, self._active_engine), self)
        self.active_engine_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.active_engine_label)

        # Lot E.7, §E.7.2 : identifie la base précise (hôte/port/base),
        # jamais seulement le nom du moteur — jamais le mot de passe, jamais
        # un champ permettant de choisir une autre base depuis cet écran
        # (lecture seule de la configuration déjà active, voir
        # BackupService.active_postgresql_target).
        self.active_target_label = QLabel("", self)
        self.active_target_label.setWordWrap(True)
        if self._active_postgresql_target is not None:
            self.active_target_label.setText(self._active_postgresql_target.label())
            layout.addWidget(self.active_target_label)

        description = QLabel(
            _ENGINE_DESCRIPTIONS.get(self._active_engine, ""), self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        return group

    # -- configuration --------------------------------------------------------

    def _build_config_group(self) -> QGroupBox:
        group = QGroupBox("Configuration de la sauvegarde automatique", self)
        form = QFormLayout(group)

        self.auto_enabled_checkbox = QCheckBox("Activer la sauvegarde automatique", self)
        form.addRow(self.auto_enabled_checkbox)

        self.frequency_combo = QComboBox(self)
        self.frequency_combo.addItems([_FREQUENCY_LABELS[FREQUENCY_DAILY], _FREQUENCY_LABELS[FREQUENCY_WEEKLY]])
        form.addRow("Fréquence", self.frequency_combo)

        self.time_edit = QLineEdit(self)
        self.time_edit.setPlaceholderText("HH:MM")
        form.addRow("Heure d'exécution", self.time_edit)

        destination_row = QHBoxLayout()
        self.destination_edit = QLineEdit(self)
        destination_row.addWidget(self.destination_edit)
        self.browse_button = QPushButton("Parcourir…", self)
        destination_row.addWidget(self.browse_button)
        form.addRow("Dossier de destination", destination_row)

        self.retention_spin = QSpinBox(self)
        self.retention_spin.setRange(1, 999)
        form.addRow("Sauvegardes à conserver", self.retention_spin)

        can_configure = self._permissions.has_permission("BACKUP_CREATE")
        for widget in (
            self.auto_enabled_checkbox, self.frequency_combo, self.time_edit,
            self.destination_edit, self.browse_button, self.retention_spin,
        ):
            widget.setEnabled(can_configure)

        self.save_config_button = QPushButton("Enregistrer", self)
        self.save_config_button.setEnabled(can_configure)
        form.addRow(self.save_config_button)

        self.browse_button.clicked.connect(self._on_browse_clicked)
        self.save_config_button.clicked.connect(self._on_save_config_clicked)

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

    def _on_browse_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Dossier de destination des sauvegardes", self.destination_edit.text())
        if directory:
            self.destination_edit.setText(directory)

    def _on_save_config_clicked(self) -> None:
        self._save_config()

    def _save_config(self) -> bool:
        """Isolé de ``_on_save_config_clicked`` pour rester testable sans
        dialogue modal."""
        try:
            self._backup_service.update_config(
                auto_enabled=self.auto_enabled_checkbox.isChecked(),
                frequency=_FREQUENCY_BY_LABEL.get(self.frequency_combo.currentText(), FREQUENCY_DAILY),
                time_of_day=self.time_edit.text(),
                destination=self.destination_edit.text(),
                retention=self.retention_spin.value(),
            )
            QMessageBox.information(self, "Configuration enregistrée", "La configuration des sauvegardes a été enregistrée.")
        except AppError as exc:
            QMessageBox.warning(self, "Configuration refusée", str(exc))
            return False
        return True

    # -- actions ----------------------------------------------------------------

    def _build_actions_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.backup_now_button = QPushButton("Sauvegarder maintenant", self)
        self.backup_now_button.setEnabled(self._permissions.has_permission("BACKUP_CREATE"))
        row.addWidget(self.backup_now_button)

        self.restore_button = QPushButton("Restaurer la sauvegarde sélectionnée", self)
        self.restore_button.setEnabled(False)
        row.addWidget(self.restore_button)
        row.addStretch(1)

        self.backup_now_button.clicked.connect(self._on_backup_now_clicked)
        self.restore_button.clicked.connect(self._on_restore_clicked)
        return row

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
        self.history_table.setHorizontalHeaderLabels(_HISTORY_COLUMNS)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.itemSelectionChanged.connect(self._update_restore_button)
        return self.history_table

    def refresh_history(self) -> None:
        try:
            entries = self._backup_service.list_backups()
        except AppError:
            self._history_entries = []
            self.history_table.setRowCount(0)
            self._update_restore_button()
            return

        self._history_entries = entries
        self.history_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            info = entry.info
            try:
                verification = self._backup_service.verify_backup_file(info.path)
                statut = "Valide" if verification.valid else "Invalide"
            except AppError:
                statut = "?"

            engine_item = QTableWidgetItem(_ENGINE_LABELS.get(entry.engine, entry.engine))
            self.history_table.setItem(row, 0, engine_item)
            self.history_table.setItem(row, 1, QTableWidgetItem(info.modified_at.strftime("%Y-%m-%d %H:%M:%S")))
            self.history_table.setItem(row, 2, QTableWidgetItem(info.name))
            self.history_table.setItem(row, 3, QTableWidgetItem(_format_size(info.size_bytes)))
            self.history_table.setItem(row, 4, QTableWidgetItem(statut))

        self._update_restore_button()

    def _selected_entry(self):
        selected = self.history_table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        if row >= len(self._history_entries):
            return None
        return self._history_entries[row]

    def _update_restore_button(self) -> None:
        can_restore = self._permissions.has_permission("BACKUP_RESTORE")
        entry = self._selected_entry()
        # §E.3 : ne jamais proposer la restauration d'une sauvegarde d'un
        # moteur différent du moteur actif — refusée de toute façon côté
        # service (voir BackupService.restore_backup), mais déjà empêchée
        # ici pour ne pas laisser croire que l'opération est possible.
        matches_active_engine = entry is not None and entry.engine == self._active_engine
        self.restore_button.setEnabled(can_restore and matches_active_engine)

    def _on_restore_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
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
        else:
            QMessageBox.critical(self, "Échec de la restauration", result.message)
        return result.success

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
