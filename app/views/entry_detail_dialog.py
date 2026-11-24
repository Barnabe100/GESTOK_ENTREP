"""Consultation détaillée, en lecture seule, d'une entrée de stock.

Affiche l'en-tête, les lignes, et les mouvements de stock générés — la
traçabilité complète exigée par le cahier des charges (§9) : qui a réalisé
l'opération, quand, quel article, quelle quantité, quel stock avant/après.

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

from app.models.enums import StatutOperation
from app.services.entries.entry_service import EntreeSummary, MouvementSummary
from app.utils.money import format_money
from app.utils.quantity import format_quantity
from app.views.design_system import MultiColumnForm, apply_compact_row_height, apply_content_driven_height

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
        # Mission 5.5, Évolution B : même constat que les détails de vente/
        # location (Mission 5.1) — largeur revue pour que les colonnes des
        # tableaux restent visibles sans défilement horizontal. La hauteur
        # n'est plus fixée ici : voir ``apply_content_driven_height`` en fin
        # de constructeur (Mission 5.6, §1).
        self.setMinimumWidth(850)

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

        header_form.add_row(0, "Numéro", QLabel(entry.numero, header_group))
        header_form.add_row(1, "Date", QLabel(str(entry.date), header_group))
        header_form.add_row(2, "Fournisseur", QLabel(entry.fournisseur_nom, header_group))
        header_form.add_row(0, "Créée par", QLabel(entry.username, header_group))
        statut_label = QLabel(_STATUT_LABELS.get(entry.statut, str(entry.statut)), header_group)
        header_form.add_row(1, "Statut", statut_label)
        header_form.add_row(2, "Référence document", QLabel(entry.reference_document or "—", header_group))
        header_form.add_row(
            0, "Créée le", QLabel(entry.date_creation.strftime("%Y-%m-%d %H:%M"), header_group)
        )
        if entry.statut == StatutOperation.ANNULEE:
            motif_label = QLabel(entry.annulation_motif or "—", header_group)
            motif_label.setWordWrap(True)
            header_form.add_row(1, "Motif d'annulation", motif_label)
        header_form.add_row(
            2, "Modifiée le", QLabel(entry.date_modification.strftime("%Y-%m-%d %H:%M"), header_group)
        )
        commentaire_label = QLabel(entry.commentaire or "—", header_group)
        commentaire_label.setWordWrap(True)
        header_form.add_row(2, "Commentaire", commentaire_label)

        content_layout.addWidget(header_group)

        # -- lignes ---------------------------------------------------------------
        lines_group = QGroupBox("Lignes", content)
        lines_layout = QVBoxLayout(lines_group)
        lines_table = QTableWidget(len(entry.lignes), len(_LINE_COLUMNS), lines_group)
        lines_table.setAlternatingRowColors(True)
        lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lines_header = lines_table.horizontalHeader()
        lines_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 110), (2, 140), (3, 140)):
            lines_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            lines_table.setColumnWidth(col, width)
        for row, ligne in enumerate(entry.lignes):
            lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(ligne.quantite)))
            lines_table.setItem(row, 2, QTableWidgetItem(format_money(ligne.prix_unitaire, currency_code)))
            lines_table.setItem(row, 3, QTableWidgetItem(format_money(ligne.montant, currency_code)))
        # Mission 5.5, Évolution B : 2 lignes de données visibles par défaut
        # (plus l'en-tête) — les lignes d'une entrée ne changent jamais
        # après construction de ce dialogue (consultation seule), un seul
        # appel suffit ici (même principe que ``sale_detail_dialog.py``).
        apply_compact_row_height(lines_table, visible_rows=2)
        lines_layout.addWidget(lines_table)

        total_label = QLabel(f"Total : {format_money(entry.total, currency_code)}", lines_group)
        total_label.setStyleSheet("font-weight: 600;")
        lines_layout.addWidget(total_label)

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

        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        # Mission 5.6, §1 : hauteur initiale adaptée au contenu réel — plus
        # d'étirement vertical artificiel (``addStretch`` retiré ci-dessus)
        # ni de hauteur fixe pouvant laisser un grand espace vide sous le
        # dernier tableau (désormais compact, voir ``apply_compact_row_height``).
        apply_content_driven_height(self, content, 880, extra_height=self.close_button.sizeHint().height())
