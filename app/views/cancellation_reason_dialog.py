"""Dialogue de confirmation d'annulation, commun aux Entrées/Sorties/Ventes.

Collecte et valide (longueur minimale) le motif d'annulation obligatoire —
la validation ici n'est qu'un confort pour l'utilisateur : la garantie
réelle vit côté service (``EntryService.cancel_entry`` /
``ExitService.cancel_exit`` / ``SaleService.cancel_sale``, voir leur
``_validate_annulation_motif``), qui refuse de toute façon une annulation
sans motif même si ce dialogue était contourné.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.views.common import build_required_field_legend, required_label

# Alignée sur MIN_ANNULATION_MOTIF_LENGTH des services concernés (entry_service.py/
# exit_service.py/sale_service.py) — dupliquée ici à l'identique des autres
# constantes UI de confort (voir ex. les longueurs max des formulaires), la
# vérification autoritaire restant toujours côté service.
MIN_REASON_LENGTH = 5


class CancellationReasonDialog(QDialog):
    def __init__(self, operation_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Annuler l'opération")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        message = QLabel(
            f"Voulez-vous vraiment annuler {operation_label} ? "
            "Cette action met à jour le stock et n'est pas réversible.",
            self,
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        self.reason_edit = QTextEdit(self)
        self.reason_edit.setPlaceholderText("Expliquez la raison de cette annulation…")
        self.reason_edit.setFixedHeight(80)
        form = QFormLayout()
        form.addRow(required_label("Motif d'annulation"), self.reason_edit)
        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.reject)
        button_row.addWidget(self.close_button)
        self.confirm_button = QPushButton("Confirmer l'annulation", self)
        self.confirm_button.setDefault(True)
        button_row.addWidget(self.confirm_button)
        layout.addLayout(button_row)

        self.confirm_button.clicked.connect(self._on_confirm)

    def _on_confirm(self) -> None:
        if len(self.reason().strip()) < MIN_REASON_LENGTH:
            self.error_label.setText(
                f"Le motif d'annulation est obligatoire et doit contenir au moins "
                f"{MIN_REASON_LENGTH} caractères."
            )
            return
        self.accept()

    def reason(self) -> str:
        return self.reason_edit.toPlainText().strip()
