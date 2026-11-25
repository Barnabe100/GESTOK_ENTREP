"""Assistant de restauration (Mission « Sauvegarde automatique et
restauration », §3.4) : complète le choix rapide depuis l'historique déjà
proposé par ``BackupsPage`` (restauration directe d'une entrée déjà listée
et déjà vérifiée) par un chemin plus général — parcourir n'importe quel
emplacement accessible (dossier local, support externe monté manuellement,
clé USB) et sélectionner directement un fichier d'archive, y compris sur un
poste tout juste installé n'ayant encore aucun historique local (§7 du
mandat : « la restauration doit être possible après installation de
StockManager sur un nouvel ordinateur, à partir d'une archive externe »).

Toute la mécanique de vérification/restauration reste entièrement portée
par ``BackupService.restore_backup`` (jamais réimplémentée ici) : ce
dialogue ne fait qu'orchestrer le choix du fichier, un aperçu de ses
informations avant engagement (nom, moteur, taille, métadonnées du
manifeste si présent), un verdict de compatibilité, la confirmation
explicite, puis l'appel au service — exactement comme
``BackupsPage._on_restore_clicked``, dont il partage la même méthode de
service (jamais une seconde logique de restauration).

Exposer un sélecteur de fichier libre ici est délibéré (contrairement à
l'historique de ``BackupsPage``, qui ne propose que des sauvegardes déjà
reconnues) : le service revérifie de toute façon indépendamment le fichier
choisi (intégrité, tables attendues, compatibilité de version) avant toute
restauration réelle — jamais une confiance aveugle dans le chemin fourni.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.backups import archive_manifest
from app.services.backups.backup_service import BackupService
from app.utils.exceptions import AppError
from app.views.background_task import BackgroundTask
from app.views.common import confirm_action
from app.views.design_system import COLOR_DANGER, COLOR_SUCCESS

_ENGINE_LABELS = {"sqlite": "SQLite", "postgresql": "PostgreSQL"}


class BackupRestoreWizardDialog(QDialog):
    def __init__(
        self,
        backup_service: BackupService,
        parent: QWidget | None = None,
        *,
        external_backup_service=None,
    ) -> None:
        super().__init__(parent)
        self._backup_service = backup_service
        self._external_backup_service = external_backup_service
        self._selected_path: Optional[Path] = None
        self._restore_task: Optional[BackgroundTask] = None

        self.setWindowTitle("Assistant de restauration")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Sélectionnez un fichier de sauvegarde StockManager (local, sur une clé "
            "USB, un disque externe, ou tout autre emplacement accessible).", self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        browse_row = QHBoxLayout()
        self.path_label = QLabel("Aucun fichier sélectionné.", self)
        self.path_label.setWordWrap(True)
        browse_row.addWidget(self.path_label, 1)
        self.browse_button = QPushButton("Parcourir…", self)
        browse_row.addWidget(self.browse_button)
        layout.addLayout(browse_row)

        self.info_group = QGroupBox("Informations de la sauvegarde", self)
        self.info_form = QFormLayout(self.info_group)
        self.info_group.setVisible(False)
        layout.addWidget(self.info_group)

        self.compatibility_label = QLabel("", self)
        self.compatibility_label.setWordWrap(True)
        self.compatibility_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.compatibility_label)

        layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        button_row.addWidget(self.cancel_button)
        self.restore_button = QPushButton("Restaurer…", self)
        self.restore_button.setProperty("variant", "warning")
        self.restore_button.setEnabled(False)
        button_row.addWidget(self.restore_button)
        layout.addLayout(button_row)

        self.browse_button.clicked.connect(self._on_browse_clicked)
        self.cancel_button.clicked.connect(self.reject)
        self.restore_button.clicked.connect(self._on_restore_clicked)

    # -- sélection du fichier ---------------------------------------------------------

    def _on_browse_clicked(self) -> None:
        # Pré-positionne le sélecteur sur le support externe configuré s'il
        # est actuellement accessible (§3.4 : « parcourir un support
        # externe ») — jamais obligatoire, l'utilisateur reste libre de
        # naviguer ailleurs (dossier local, autre support).
        start_dir = ""
        if self._external_backup_service is not None:
            try:
                media_root = self._external_backup_service.find_current_media_root()
            except AppError:
                media_root = None
            if media_root is not None:
                start_dir = str(media_root)
        path, _filter = QFileDialog.getOpenFileName(
            self, "Sélectionner une archive de sauvegarde", start_dir,
            "Archives StockManager (*.db *.dump);;Tous les fichiers (*)",
        )
        if not path:
            return
        self.select_file(Path(path))

    def select_file(self, path: Path) -> None:
        """Isolé de ``_on_browse_clicked`` pour rester testable sans
        dialogue modal de sélection de fichier."""
        self._selected_path = path
        self.path_label.setText(str(path))
        self._refresh_preview()

    # -- aperçu avant restauration (§3.4 : « présenter les informations avant ») -----

    def _refresh_preview(self) -> None:
        while self.info_form.rowCount() > 0:
            self.info_form.removeRow(0)
        self.info_group.setVisible(False)
        self.restore_button.setEnabled(False)
        self.compatibility_label.setStyleSheet("font-weight: 600;")
        self.compatibility_label.setText("")

        path = self._selected_path
        if path is None or not path.is_file():
            self.compatibility_label.setText("Fichier introuvable.")
            return

        engine = "postgresql" if path.suffix == ".dump" else "sqlite"
        self.info_form.addRow("Nom", QLabel(path.name, self))
        self.info_form.addRow("Moteur", QLabel(_ENGINE_LABELS.get(engine, engine), self))
        try:
            size = path.stat().st_size
            self.info_form.addRow("Taille", QLabel(f"{size / 1024:.1f} Ko", self))
        except OSError:
            pass

        manifest = archive_manifest.read_manifest_for(path)
        if manifest is not None:
            self.info_form.addRow("Date de création", QLabel(manifest.created_at, self))
            self.info_form.addRow("Version StockManager", QLabel(manifest.stockmanager_version, self))
            self.info_form.addRow("Version de schéma", QLabel(manifest.schema_version or "—", self))
            self.info_form.addRow("Chiffrée", QLabel("Oui" if manifest.encrypted else "Non", self))
        self.info_group.setVisible(True)

        try:
            verification = self._backup_service.verify_backup_file(path)
        except AppError as exc:
            self.compatibility_label.setText(f"Vérification impossible : {exc}")
            return

        if not verification.valid:
            self.compatibility_label.setText(
                "Archive invalide ou corrompue : " + "; ".join(verification.errors)
            )
            self.compatibility_label.setStyleSheet(f"font-weight: 600; color: {COLOR_DANGER};")
            return

        try:
            active_engine = self._backup_service.active_engine()
        except AppError:
            active_engine = None
        if active_engine is not None and engine != active_engine:
            self.compatibility_label.setText(
                f"Cette archive provient du moteur {_ENGINE_LABELS.get(engine, engine)}, alors que "
                f"le moteur actif est {_ENGINE_LABELS.get(active_engine, active_engine)} — "
                "restauration impossible."
            )
            self.compatibility_label.setStyleSheet(f"font-weight: 600; color: {COLOR_DANGER};")
            return

        self.compatibility_label.setText("Archive valide et compatible avec cette installation.")
        self.compatibility_label.setStyleSheet(f"font-weight: 600; color: {COLOR_SUCCESS};")
        self.restore_button.setEnabled(True)

    # -- restauration -----------------------------------------------------------------

    def _on_restore_clicked(self) -> None:
        if self._selected_path is None or self._restore_task is not None:
            return
        if not confirm_action(
            self, "Confirmation de restauration",
            "Voulez-vous vraiment restaurer cette sauvegarde ?\n\n"
            "La base de données actuelle sera remplacée (une sauvegarde de sécurité "
            "de l'état actuel sera créée automatiquement avant toute modification). "
            "L'application devra être redémarrée après une restauration réussie. Cette "
            "action est irréversible sans cette sauvegarde de sécurité.",
        ):
            return
        # Même principe que ``BackupsPage._on_restore_clicked`` : un
        # ``pg_restore`` long ne doit jamais geler l'interface (voir
        # BackgroundTask) — jamais de construction/affichage de widget Qt
        # depuis le thread d'arrière-plan, uniquement dans les callbacks.
        backup_path = str(self._selected_path)
        self._set_busy(True)

        def _on_success(result) -> None:
            self._finish_restore_task()
            self._show_restore_result(result)

        def _on_failure(exc: Exception) -> None:
            self._finish_restore_task()
            message = str(exc) if isinstance(exc, AppError) else f"Erreur inattendue lors de la restauration : {exc}"
            QMessageBox.warning(self, "Restauration refusée", message)

        self._restore_task = BackgroundTask(lambda: self._backup_service.restore_backup(backup_path))
        self._restore_task.start(_on_success, _on_failure)

    def _set_busy(self, busy: bool) -> None:
        self.browse_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)
        self.restore_button.setEnabled(not busy)
        self.compatibility_label.setText("Restauration en cours…" if busy else self.compatibility_label.text())

    def _finish_restore_task(self) -> None:
        self._restore_task = None
        self._set_busy(False)
        self._refresh_preview()

    def has_active_background_task(self) -> bool:
        """Utilisé par l'appelant (``BackupsPage``) pour refuser une
        fermeture de l'application tant qu'une restauration lancée depuis
        cet assistant est en cours — même garde que pour les opérations de
        la page elle-même (voir ``BackgroundTask``, docstring de module)."""
        return self._restore_task is not None

    def reject(self) -> None:
        if self._restore_task is not None:
            return
        super().reject()

    def _show_restore_result(self, result) -> bool:
        """Partagé entre ``_restore_selected`` (appel direct, synchrone,
        conservé pour les tests existants) et le callback de succès de
        ``_on_restore_clicked`` (appel asynchrone) — même principe que
        ``BackupsPage._show_restore_result``."""
        if result.success:
            QMessageBox.information(
                self, "Restauration réussie",
                result.message + "\n\nVeuillez fermer et relancer StockManager Desktop maintenant.",
            )
            if result.destination_warning:
                self._offer_to_reconfigure_destination(result.destination_warning)
            self.accept()
        else:
            QMessageBox.critical(self, "Échec de la restauration", result.message)
        return result.success

    def _offer_to_reconfigure_destination(self, warning: str) -> None:
        """Même principe que ``BackupsPage._offer_to_reconfigure_destination``
        (mission corrective, §3.11) — ce dialogue n'a pas de formulaire de
        configuration à rafraîchir ensuite (il se ferme juste après, voir
        ``_show_restore_result``), seul l'enregistrement du nouveau dossier
        via le service compte ici."""
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
        QMessageBox.information(self, "Dossier mis à jour", "Le nouveau dossier de destination a été enregistré.")

    def _restore_selected(self) -> bool:
        """Isolé de ``_on_restore_clicked`` pour rester testable sans
        dialogue modal de confirmation ni thread d'arrière-plan — appel
        direct et synchrone à ``BackupService.restore_backup`` (même
        service, même vérification, même sauvegarde de sécurité que la
        restauration rapide depuis l'historique de ``BackupsPage``, jamais
        une logique dupliquée)."""
        try:
            result = self._backup_service.restore_backup(str(self._selected_path))
        except AppError as exc:
            QMessageBox.warning(self, "Restauration refusée", str(exc))
            return False
        return self._show_restore_result(result)
