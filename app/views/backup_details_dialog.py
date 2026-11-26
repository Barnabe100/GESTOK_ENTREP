"""Consultation détaillée, en lecture seule, d'une entrée de l'historique
des sauvegardes (Mission « Sauvegarde automatique et restauration », §3.3 :
action « Consulter les détails »).

Affiche les métadonnées du manifeste de l'archive (voir
``app.services.backups.archive_manifest``) quand il est disponible — une
archive antérieure à ce mécanisme, ou copiée sans son manifeste, n'en
affiche simplement pas moins (jamais une erreur), le reste des informations
(nom, taille, emplacement, statut de vérification) restant toujours
disponible indépendamment du manifeste.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.services.backups import archive_manifest
from app.services.backups.backup_service import STATUS_INVALID, STATUS_UNVERIFIABLE, STATUS_VALID, BackupEntry
from app.utils.exceptions import AppError
from app.views.design_system import COLOR_DANGER, COLOR_SUCCESS, COLOR_TEXT_SECONDARY, COLOR_WARNING

_ENGINE_LABELS = {"sqlite": "SQLite", "postgresql": "PostgreSQL"}
_BACKUP_TYPE_LABELS = {
    archive_manifest.BACKUP_TYPE_LOCAL: "Locale",
    archive_manifest.BACKUP_TYPE_EXTERNAL: "Externe",
    archive_manifest.BACKUP_TYPE_SECURITY: "Sécurité (avant restauration)",
}


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("o", "Ko", "Mo", "Go"):
        if size < 1024 or unit == "Go":
            return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} o"


class BackupDetailsDialog(QDialog):
    def __init__(
        self,
        entry: BackupEntry,
        source_label: str,
        backup_service,
        parent: QWidget | None = None,
    ) -> None:
        """``source_label`` : « Locale »/« Externe », fourni par l'appelant
        (cette boîte ne connaît jamais l'origine d'une entrée par elle-même,
        voir ``BackupsPage``). ``backup_service`` : seulement utilisé pour
        ``verify_backup_file`` (même vérification que la colonne « Statut »
        de l'historique, jamais réimplémentée ici)."""
        super().__init__(parent)
        info = entry.info
        self.setWindowTitle(f"Sauvegarde — {info.name}")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(8)

        form.addRow("Nom", QLabel(info.name, self))
        form.addRow("Type", QLabel(source_label, self))
        form.addRow("Moteur", QLabel(_ENGINE_LABELS.get(entry.engine, entry.engine), self))
        form.addRow("Taille", QLabel(_format_size(info.size_bytes), self))
        form.addRow("Modifié le", QLabel(info.modified_at.strftime("%d/%m/%Y %H:%M:%S"), self))
        form.addRow("Emplacement", QLabel(str(info.path.parent), self))

        try:
            # Mission « Audit, correction et fiabilisation du système de
            # sauvegarde », §10 : ``describe_backup_status`` (jamais
            # ``verify_backup_file`` seul) — son détail (``errors``)
            # n'est plus jamais ignoré, voir ci-dessous.
            report = backup_service.describe_backup_status(info.path)
            statut, errors = report.label, report.errors
        except AppError as exc:
            statut, errors = "Indéterminé", [str(exc)]

        statut_label = QLabel(statut, self)
        statut_colors = {
            STATUS_VALID: COLOR_SUCCESS, STATUS_INVALID: COLOR_DANGER, STATUS_UNVERIFIABLE: COLOR_WARNING,
        }
        statut_label.setStyleSheet(f"font-weight: 600; color: {statut_colors.get(statut, COLOR_TEXT_SECONDARY)};")
        form.addRow("Statut", statut_label)

        if errors:
            # L'utilisateur doit pouvoir consulter la cause exacte d'une
            # anomalie sans ouvrir les journaux techniques (§10 du
            # mandat) — jamais un message générique à la place.
            errors_label = QLabel("• " + "\n• ".join(errors), self)
            errors_label.setWordWrap(True)
            errors_label.setProperty("role", "secondary")
            form.addRow("Détail de la vérification", errors_label)

        manifest = archive_manifest.read_manifest_for(info.path)
        if manifest is not None:
            form.addRow("Version StockManager", QLabel(manifest.stockmanager_version, self))
            form.addRow("Version de schéma", QLabel(manifest.schema_version or "—", self))
            form.addRow(
                "Type de sauvegarde",
                QLabel(_BACKUP_TYPE_LABELS.get(manifest.backup_type, manifest.backup_type), self),
            )
            form.addRow("Chiffrée", QLabel("Oui" if manifest.encrypted else "Non", self))
            form.addRow("Empreinte (SHA-256)", QLabel(f"{manifest.sha256[:16]}…", self))
        else:
            no_manifest_label = QLabel(
                "Aucun manifeste associé (sauvegarde antérieure à ce mécanisme, ou copiée sans lui).", self
            )
            no_manifest_label.setWordWrap(True)
            no_manifest_label.setProperty("role", "secondary")
            form.addRow(no_manifest_label)

        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)
