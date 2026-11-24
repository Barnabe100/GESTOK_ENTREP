"""Consultation détaillée, en lecture seule, d'un inventaire.

Affiche l'en-tête, les lignes (stock théorique, stock compté, écart), et les
mouvements d'ajustement générés (aucun pour une ligne dont l'écart était
nul).

Mission 5.5, Évolution B : harmonisation avec ``sale_detail_dialog.py``/
``location_detail_dialog.py`` — en-tête sur plusieurs colonnes
(:class:`MultiColumnForm`, partagé) au lieu d'une colonne verticale unique,
et tableaux plafonnés à 2 lignes visibles (``apply_compact_row_height``,
partagé) au lieu d'un plancher de 4. Aucun champ ni colonne ajouté/retiré.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
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
from app.views.design_system import MultiColumnForm, apply_compact_row_height

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
        self.setMinimumWidth(850)
        self.resize(880, 700)

        layout = QVBoxLayout(self)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)

        # -- en-tête ---------------------------------------------------------------
        header_group = QGroupBox("Informations générales", content)
        header_group_layout = QVBoxLayout(header_group)

        header_form = MultiColumnForm(header_group, column_count=3)
        header_group_layout.addWidget(header_form.widget)

        header_form.add_row(0, "Numéro", QLabel(inventory.numero, header_group))
        header_form.add_row(1, "Date", QLabel(str(inventory.date), header_group))
        header_form.add_row(2, "Créé par", QLabel(inventory.username, header_group))
        header_form.add_row(
            0, "Statut", QLabel(_STATUT_LABELS.get(inventory.statut, str(inventory.statut)), header_group)
        )
        header_form.add_row(1, "Écart global", QLabel(format_quantity_signed(inventory.ecart_total), header_group))
        header_form.add_row(
            2, "Créé le", QLabel(inventory.date_creation.strftime("%Y-%m-%d %H:%M"), header_group)
        )
        header_form.add_row(
            0, "Modifié le", QLabel(inventory.date_modification.strftime("%Y-%m-%d %H:%M"), header_group)
        )

        content_layout.addWidget(header_group)

        # -- lignes ---------------------------------------------------------------
        lines_group = QGroupBox("Lignes", content)
        lines_layout = QVBoxLayout(lines_group)
        lines_table = QTableWidget(len(inventory.lignes), len(_LINE_COLUMNS), lines_group)
        lines_table.setAlternatingRowColors(True)
        lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lines_header = lines_table.horizontalHeader()
        lines_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 130), (2, 130), (3, 110)):
            lines_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            lines_table.setColumnWidth(col, width)
        for row, ligne in enumerate(inventory.lignes):
            lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(ligne.stock_theorique)))
            lines_table.setItem(row, 2, QTableWidgetItem(format_quantity(ligne.stock_physique)))
            lines_table.setItem(row, 3, QTableWidgetItem(format_quantity_signed(ligne.ecart)))
        # Mission 5.5, Évolution B : 2 lignes de données visibles par défaut
        # (plus l'en-tête) — les lignes d'un inventaire ne changent jamais
        # après construction de ce dialogue (consultation seule), un seul
        # appel suffit ici (même principe que ``sale_detail_dialog.py``).
        apply_compact_row_height(lines_table, visible_rows=2)
        lines_layout.addWidget(lines_table)

        content_layout.addWidget(lines_group)

        # -- mouvements de stock générés -------------------------------------------
        movements_group = QGroupBox("Mouvements de stock générés", content)
        movements_layout = QVBoxLayout(movements_group)
        movements_table = QTableWidget(len(movements), len(_MOVEMENT_COLUMNS), movements_group)
        movements_table.setAlternatingRowColors(True)
        movements_table.setHorizontalHeaderLabels(_MOVEMENT_COLUMNS)
        movements_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        movements_header = movements_table.horizontalHeader()
        movements_header.setStretchLastSection(True)
        for col, width in ((0, 150), (1, 110), (2, 100), (3, 115), (4, 115)):
            movements_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            movements_table.setColumnWidth(col, width)
        for row, mouvement in enumerate(movements):
            movements_table.setItem(row, 0, QTableWidgetItem(mouvement.date_heure.strftime("%Y-%m-%d %H:%M")))
            movements_table.setItem(row, 1, QTableWidgetItem(mouvement.type.value))
            movements_table.setItem(row, 2, QTableWidgetItem(format_quantity(mouvement.quantite)))
            movements_table.setItem(row, 3, QTableWidgetItem(format_quantity(mouvement.stock_avant)))
            movements_table.setItem(row, 4, QTableWidgetItem(format_quantity(mouvement.stock_apres)))
            movements_table.setItem(row, 5, QTableWidgetItem(mouvement.username))
        apply_compact_row_height(movements_table, visible_rows=2)
        movements_layout.addWidget(movements_table)

        content_layout.addWidget(movements_group)

        content_layout.addStretch(1)
        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)
