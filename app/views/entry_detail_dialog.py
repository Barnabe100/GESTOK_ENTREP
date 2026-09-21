"""Consultation détaillée, en lecture seule, d'une entrée de stock.

Affiche l'en-tête, les lignes, et les mouvements de stock générés — la
traçabilité complète exigée par le cahier des charges (§9) : qui a réalisé
l'opération, quand, quel article, quelle quantité, quel stock avant/après.
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
from app.services.entries.entry_service import EntreeSummary, MouvementSummary
from app.utils.money import format_money
from app.utils.quantity import format_quantity

_LINE_COLUMNS = ["Article", "Quantité", "Prix unitaire", "Montant"]
_MOVEMENT_COLUMNS = ["Date/heure", "Type", "Quantité", "Stock avant", "Stock après", "Utilisateur"]

_STATUT_LABELS = {
    StatutOperation.BROUILLON: "Brouillon",
    StatutOperation.VALIDEE: "Validée",
    StatutOperation.ANNULEE: "Annulée",
}


class EntryDetailDialog(QDialog):
    def __init__(
        self,
        entry: EntreeSummary,
        movements: list[MouvementSummary],
        currency_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Entrée — {entry.numero}")
        self.setModal(True)
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Numéro", QLabel(entry.numero, self))
        form.addRow("Date", QLabel(str(entry.date), self))
        form.addRow("Fournisseur", QLabel(entry.fournisseur_nom, self))
        form.addRow("Référence document", QLabel(entry.reference_document or "—", self))
        form.addRow("Créée par", QLabel(entry.username, self))
        form.addRow("Commentaire", QLabel(entry.commentaire or "—", self))
        form.addRow("Statut", QLabel(_STATUT_LABELS.get(entry.statut, str(entry.statut)), self))
        if entry.statut == StatutOperation.ANNULEE:
            motif_label = QLabel(entry.annulation_motif or "—", self)
            motif_label.setWordWrap(True)
            form.addRow("Motif d'annulation", motif_label)
        form.addRow("Créée le", QLabel(entry.date_creation.strftime("%Y-%m-%d %H:%M"), self))
        form.addRow("Modifiée le", QLabel(entry.date_modification.strftime("%Y-%m-%d %H:%M"), self))

        layout.addLayout(form)

        layout.addWidget(QLabel("Lignes", self))
        lines_table = QTableWidget(len(entry.lignes), len(_LINE_COLUMNS), self)
        lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        lines_table.horizontalHeader().setStretchLastSection(True)
        lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, ligne in enumerate(entry.lignes):
            lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(ligne.quantite)))
            lines_table.setItem(row, 2, QTableWidgetItem(format_money(ligne.prix_unitaire, currency_code)))
            lines_table.setItem(row, 3, QTableWidgetItem(format_money(ligne.montant, currency_code)))
        layout.addWidget(lines_table)

        total_label = QLabel(f"Total : {format_money(entry.total, currency_code)}", self)
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
