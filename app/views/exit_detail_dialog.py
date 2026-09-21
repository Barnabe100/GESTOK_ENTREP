"""Consultation détaillée, en lecture seule, d'une sortie de stock.

Affiche l'en-tête, les lignes (avec le coût de valorisation CMUP réellement
appliqué à la validation), et les mouvements de stock générés.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import StatutOperation
from app.services.exits.exit_service import SortieSummary
from app.services.stock.movement_summary import MouvementSummary
from app.utils.money import format_money
from app.utils.quantity import format_quantity

_LINE_COLUMNS = ["Article", "Quantité", "Coût unitaire (CMUP)", "Montant"]
_MOVEMENT_COLUMNS = ["Date/heure", "Type", "Quantité", "Stock avant", "Stock après", "Utilisateur"]

_STATUT_LABELS = {
    StatutOperation.BROUILLON: "Brouillon",
    StatutOperation.VALIDEE: "Validée",
    StatutOperation.ANNULEE: "Annulée",
}


class ExitDetailDialog(QDialog):
    def __init__(
        self,
        exit_: SortieSummary,
        movements: list[MouvementSummary],
        currency_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sortie — {exit_.numero}")
        self.setModal(True)
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Numéro", QLabel(exit_.numero, self))
        form.addRow("Date", QLabel(str(exit_.date), self))
        form.addRow("Motif", QLabel(exit_.motif_libelle, self))
        form.addRow("Bénéficiaire / service", QLabel(exit_.beneficiaire or "—", self))
        form.addRow("Référence document", QLabel(exit_.reference or "—", self))
        form.addRow("Créée par", QLabel(exit_.username, self))
        form.addRow("Commentaire", QLabel(exit_.commentaire or "—", self))
        form.addRow("Statut", QLabel(_STATUT_LABELS.get(exit_.statut, str(exit_.statut)), self))
        if exit_.statut == StatutOperation.ANNULEE:
            motif_label = QLabel(exit_.annulation_motif or "—", self)
            motif_label.setWordWrap(True)
            form.addRow("Motif d'annulation", motif_label)
        form.addRow("Créée le", QLabel(exit_.date_creation.strftime("%Y-%m-%d %H:%M"), self))
        form.addRow("Modifiée le", QLabel(exit_.date_modification.strftime("%Y-%m-%d %H:%M"), self))

        layout.addLayout(form)

        layout.addWidget(QLabel("Lignes", self))
        lines_table = QTableWidget(len(exit_.lignes), len(_LINE_COLUMNS), self)
        lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        lines_table.horizontalHeader().setStretchLastSection(True)
        lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, ligne in enumerate(exit_.lignes):
            lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(ligne.quantite)))
            lines_table.setItem(row, 2, QTableWidgetItem(format_money(ligne.cout_unitaire, currency_code)))
            lines_table.setItem(row, 3, QTableWidgetItem(format_money(ligne.montant, currency_code)))
        layout.addWidget(lines_table)

        total_label = QLabel(f"Total : {format_money(exit_.total, currency_code)}", self)
        total_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(total_label)

        layout.addWidget(QLabel("Mouvements de stock générés", self))
        movements_table = QTableWidget(len(movements), len(_MOVEMENT_COLUMNS), self)
        movements_table.setHorizontalHeaderLabels(_MOVEMENT_COLUMNS)
        movements_table.horizontalHeader().setStretchLastSection(True)
        movements_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, mouvement in enumerate(movements):
            movements_table.setItem(row, 0, QTableWidgetItem(mouvement.date_heure.strftime("%Y-%m-%d %H:%M")))
            movements_table.setItem(row, 1, QTableWidgetItem(mouvement.type.value))
            movements_table.setItem(row, 2, QTableWidgetItem(format_quantity(mouvement.quantite)))
            movements_table.setItem(row, 3, QTableWidgetItem(format_quantity(mouvement.stock_avant)))
            movements_table.setItem(row, 4, QTableWidgetItem(format_quantity(mouvement.stock_apres)))
            movements_table.setItem(row, 5, QTableWidgetItem(mouvement.username))
        layout.addWidget(movements_table)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)
