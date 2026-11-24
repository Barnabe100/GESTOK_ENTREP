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
from app.services.backups.backup_service import BackupEntry
from app.utils.exceptions import AppError

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
            verification = backup_service.verify_backup_file(info.path)
            statut = "Valide" if verification.valid else "Invalide"
        except AppError:
            statut = "Indéterminé"
        form.addRow("Statut", QLabel(statut, self))

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
