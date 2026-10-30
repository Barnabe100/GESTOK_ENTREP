"""Consultation détaillée, en lecture seule, d'un inventaire.

Affiche l'en-tête, les lignes (stock théorique, stock compté, écart), et les
mouvements d'ajustement générés (aucun pour une ligne dont l'écart était
nul).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import StatutInventaire
from app.services.inventory.inventory_service import InventaireSummary
from app.services.stock.movement_summary import MouvementSummary
from app.utils.quantity import format_quantity, format_quantity_signed
from app.views.design_system import apply_comfortable_row_height

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
        # Mission 4, §2.4 : même correctif que la consultation de vente —
        # voir ``apply_comfortable_row_height``.
        self.resize(680, 760)

        layout = QVBoxLayout(self)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)

        form = QFormLayout()

        form.addRow("Numéro", QLabel(inventory.numero, content))
        form.addRow("Date", QLabel(str(inventory.date), content))
        form.addRow("Créé par", QLabel(inventory.username, content))
        form.addRow("Statut", QLabel(_STATUT_LABELS.get(inventory.statut, str(inventory.statut)), content))
        form.addRow("Écart global", QLabel(format_quantity_signed(inventory.ecart_total), content))
        form.addRow("Créé le", QLabel(inventory.date_creation.strftime("%Y-%m-%d %H:%M"), content))
        form.addRow("Modifié le", QLabel(inventory.date_modification.strftime("%Y-%m-%d %H:%M"), content))

        content_layout.addLayout(form)

        content_layout.addWidget(QLabel("Lignes", content))
        lines_table = QTableWidget(len(inventory.lignes), len(_LINE_COLUMNS), content)
        lines_table.setAlternatingRowColors(True)
        lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        lines_table.horizontalHeader().setStretchLastSection(True)
        lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_comfortable_row_height(lines_table, visible_rows=4)
        for row, ligne in enumerate(inventory.lignes):
            lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(ligne.stock_theorique)))
            lines_table.setItem(row, 2, QTableWidgetItem(format_quantity(ligne.stock_physique)))
            lines_table.setItem(row, 3, QTableWidgetItem(format_quantity_signed(ligne.ecart)))
        content_layout.addWidget(lines_table)

        content_layout.addWidget(QLabel("Mouvements de stock générés", content))
        movements_table = QTableWidget(len(movements), len(_MOVEMENT_COLUMNS), content)
        movements_table.setAlternatingRowColors(True)
        movements_table.setHorizontalHeaderLabels(_MOVEMENT_COLUMNS)
        movements_table.horizontalHeader().setStretchLastSection(True)
        movements_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_comfortable_row_height(movements_table, visible_rows=4)
        for row, mouvement in enumerate(movements):
            movements_table.setItem(row, 0, QTableWidgetItem(mouvement.date_heure.strftime("%Y-%m-%d %H:%M")))
            movements_table.setItem(row, 1, QTableWidgetItem(mouvement.type.value))
            movements_table.setItem(row, 2, QTableWidgetItem(format_quantity(mouvement.quantite)))
            movements_table.setItem(row, 3, QTableWidgetItem(format_quantity(mouvement.stock_avant)))
            movements_table.setItem(row, 4, QTableWidgetItem(format_quantity(mouvement.stock_apres)))
            movements_table.setItem(row, 5, QTableWidgetItem(mouvement.username))
        content_layout.addWidget(movements_table)

        content_layout.addStretch(1)
        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)
