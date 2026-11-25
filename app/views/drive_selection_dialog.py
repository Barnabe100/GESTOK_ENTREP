"""Dialogue de sélection d'un lecteur externe (clé USB, disque dur externe)
— remplace le sélecteur de dossier générique (mission corrective
« Correction et validation du module de sauvegarde sous Windows », §2.4) :
l'utilisateur choisit désormais un volume réellement identifié (lettre,
type, étiquette, marqueur déjà présent le cas échéant) parmi la liste
proposée par ``ExternalBackupService.list_available_drives()`` — jamais un
chemin de dossier arbitraire qui pourrait désigner un sous-dossier plutôt
que la racine réelle du lecteur (voir
``external_media.normalize_drive_root`` pour le défaut ainsi évité à la
racine)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.backups.external_media import DriveInfo

_DRIVE_ROOT_ROLE = int(Qt.ItemDataRole.UserRole)

_TYPE_LABELS = {
    "removable": "clé USB / support amovible",
    "fixed": "disque fixe (souvent un disque dur externe)",
}


class DriveSelectionDialog(QDialog):
    def __init__(self, drives: list[DriveInfo], *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choisir un support externe")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Sélectionnez le lecteur correspondant à votre support externe (clé USB ou disque dur "
            "externe) :", self,
        ))

        self.list_widget = QListWidget(self)
        for drive in drives:
            text = str(drive.root)
            if drive.volume_label:
                text += f" — {drive.volume_label}"
            text += f" ({_TYPE_LABELS.get(drive.drive_type, drive.drive_type)})"
            if drive.marker is not None:
                text += f" — déjà configuré : « {drive.marker.label} »"
            item = QListWidgetItem(text)
            item.setData(_DRIVE_ROOT_ROLE, str(drive.root))
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        self.empty_label: Optional[QLabel] = None
        if not drives:
            self.empty_label = QLabel(
                "Aucun support externe approprié n'a été détecté. Branchez une clé USB ou un disque "
                "dur externe, puis réessayez.",
                self,
            )
            self.empty_label.setWordWrap(True)
            layout.addWidget(self.empty_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.choose_button = QPushButton("Choisir", self)
        self.choose_button.setProperty("variant", "primary")
        self.choose_button.setEnabled(False)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.choose_button)
        layout.addLayout(button_row)

        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.cancel_button.clicked.connect(self.reject)
        self.choose_button.clicked.connect(self.accept)

    def _on_selection_changed(self) -> None:
        self.choose_button.setEnabled(bool(self.list_widget.selectedItems()))

    def selected_root(self) -> Optional[Path]:
        items = self.list_widget.selectedItems()
        if not items:
            return None
        return Path(items[0].data(_DRIVE_ROOT_ROLE))
