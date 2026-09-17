"""Consultation détaillée, en lecture seule, d'un inventaire.

Affiche l'en-tête, les lignes (stock théorique, stock compté, écart), et les
mouvements d'ajustement générés (aucun pour une ligne dont l'écart était
nul).
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

from app.models.enums import StatutInventaire
from app.services.inventory.inventory_service import InventaireSummary
from app.services.stock.movement_summary import MouvementSummary

_LINE_COLUMNS = ["Article", "Stock théorique", "Stock compté", "Écart"]
_MOVEMENT_COLUMNS = ["Date/heure", "Type", "Quantité", "Stock avant", "Stock après", "Utilisateur"]

_STATUT_LABELS = {
    StatutInventaire.BROUILLON: "Brouillon",
    StatutInventaire.VALIDE: "Validé",
}


class InventoryDetailDialog(QDialog):
    def __init__(
        self,
        inventory: InventaireSummary,
        movements: list[MouvementSummary],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Inventaire — {inventory.numero}")
        self.setModal(True)
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Numéro", QLabel(inventory.numero, self))
        form.addRow("Date", QLabel(str(inventory.date), self))
        form.addRow("Créé par", QLabel(inventory.username, self))
        form.addRow("Statut", QLabel(_STATUT_LABELS.get(inventory.statut, str(inventory.statut)), self))
        form.addRow("Écart global", QLabel(f"{inventory.ecart_total:+}", self))
        form.addRow("Créé le", QLabel(inventory.date_creation.strftime("%Y-%m-%d %H:%M"), self))
        form.addRow("Modifié le", QLabel(inventory.date_modification.strftime("%Y-%m-%d %H:%M"), self))

        layout.addLayout(form)

        layout.addWidget(QLabel("Lignes", self))
        lines_table = QTableWidget(len(inventory.lignes), len(_LINE_COLUMNS), self)
        lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        lines_table.horizontalHeader().setStretchLastSection(True)
        lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, ligne in enumerate(inventory.lignes):
            lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            lines_table.setItem(row, 1, QTableWidgetItem(str(ligne.stock_theorique)))
            lines_table.setItem(row, 2, QTableWidgetItem(str(ligne.stock_physique)))
            lines_table.setItem(row, 3, QTableWidgetItem(f"{ligne.ecart:+}"))
        layout.addWidget(lines_table)

        layout.addWidget(QLabel("Mouvements de stock générés", self))
        movements_table = QTableWidget(len(movements), len(_MOVEMENT_COLUMNS), self)
        movements_table.setHorizontalHeaderLabels(_MOVEMENT_COLUMNS)
        movements_table.horizontalHeader().setStretchLastSection(True)
        movements_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, mouvement in enumerate(movements):
            movements_table.setItem(row, 0, QTableWidgetItem(mouvement.date_heure.strftime("%Y-%m-%d %H:%M")))
            movements_table.setItem(row, 1, QTableWidgetItem(mouvement.type.value))
            movements_table.setItem(row, 2, QTableWidgetItem(str(mouvement.quantite)))
            movements_table.setItem(row, 3, QTableWidgetItem(str(mouvement.stock_avant)))
            movements_table.setItem(row, 4, QTableWidgetItem(str(mouvement.stock_apres)))
            movements_table.setItem(row, 5, QTableWidgetItem(mouvement.username))
        layout.addWidget(movements_table)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)
