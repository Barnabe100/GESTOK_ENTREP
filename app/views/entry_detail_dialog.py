"""Consultation détaillée, en lecture seule, d'une entrée de stock.

Affiche l'en-tête, les lignes, et les mouvements de stock générés — la
traçabilité complète exigée par le cahier des charges (§9) : qui a réalisé
l'opération, quand, quel article, quelle quantité, quel stock avant/après.
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

from app.models.enums import StatutOperation
from app.services.entries.entry_service import EntreeSummary, MouvementSummary
from app.utils.money import format_money
from app.utils.quantity import format_quantity
from app.views.design_system import apply_comfortable_row_height

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

        form.addRow("Numéro", QLabel(entry.numero, content))
        form.addRow("Date", QLabel(str(entry.date), content))
        form.addRow("Fournisseur", QLabel(entry.fournisseur_nom, content))
        form.addRow("Référence document", QLabel(entry.reference_document or "—", content))
        form.addRow("Créée par", QLabel(entry.username, content))
        form.addRow("Commentaire", QLabel(entry.commentaire or "—", content))
        form.addRow("Statut", QLabel(_STATUT_LABELS.get(entry.statut, str(entry.statut)), content))
        if entry.statut == StatutOperation.ANNULEE:
            motif_label = QLabel(entry.annulation_motif or "—", content)
            motif_label.setWordWrap(True)
            form.addRow("Motif d'annulation", motif_label)
        form.addRow("Créée le", QLabel(entry.date_creation.strftime("%Y-%m-%d %H:%M"), content))
        form.addRow("Modifiée le", QLabel(entry.date_modification.strftime("%Y-%m-%d %H:%M"), content))

        content_layout.addLayout(form)

        content_layout.addWidget(QLabel("Lignes", content))
        lines_table = QTableWidget(len(entry.lignes), len(_LINE_COLUMNS), content)
        lines_table.setAlternatingRowColors(True)
        lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        lines_table.horizontalHeader().setStretchLastSection(True)
        lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_comfortable_row_height(lines_table, visible_rows=4)
        for row, ligne in enumerate(entry.lignes):
            lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(ligne.quantite)))
            lines_table.setItem(row, 2, QTableWidgetItem(format_money(ligne.prix_unitaire, currency_code)))
            lines_table.setItem(row, 3, QTableWidgetItem(format_money(ligne.montant, currency_code)))
        content_layout.addWidget(lines_table)

        total_label = QLabel(f"Total : {format_money(entry.total, currency_code)}", content)
        total_label.setStyleSheet("font-weight: 600;")
        content_layout.addWidget(total_label)

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
