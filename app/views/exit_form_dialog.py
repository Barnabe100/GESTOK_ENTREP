"""Formulaire de création/modification d'une sortie de stock (en-tête + lignes
dynamiques).

Ne connaît rien du service métier : la saisie des lignes est gérée localement
(ajout/suppression, calcul d'affichage du montant et du total, sur la base du
CMUP courant affiché à titre indicatif) mais la validation métier définitive
(existence/statut de l'article et du motif, quantité, disponibilité du stock)
reste de la responsabilité d'``ExitService``, appelé par :class:`ExitsPage` à
la soumission.

Mission 5.3 : la sélection d'article reprend l'ergonomie déjà en place dans
les écrans de caisse Ventes/Locations (recherche en direct, voir
:class:`ArticleSearchPanel`, partagé avec ``entry_form_dialog.py``) plutôt
qu'un dialogue séparé par ligne. Seule la quantité devient éditable
directement dans le tableau (même délégué ``QuantityEditDelegate`` que les
tableaux de caisse) — le coût (CMUP) reste strictement en lecture seule,
jamais modifiable ici : aucune règle de valorisation/CMUP n'est changée.
``ExitLineFormDialog`` n'est plus utilisé par ce formulaire mais n'est pas
supprimé, à l'identique de ``SaleLineFormDialog``/``LocationLineFormDialog``
après le lot « Écran de caisse ».
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.utils.exceptions import ValidationError
from app.utils.quantity import format_quantity
from app.views.article_search_panel import ArticleSearchPanel
from app.views.common import (
    build_required_field_legend,
    date_to_qdate,
    parse_decimal,
    required_label,
)
from app.views.design_system import QuantityEditDelegate, apply_compact_row_height

_LINE_COLUMNS = ["Article", "Quantité", "Coût (CMUP)", "Montant"]
_QUANTITY_COLUMN = 1


class ExitFormDialog(QDialog):
    def __init__(
        self,
        motifs: list[tuple[int, str]],
        articles: list[tuple[int, str, str]],
        initial: Optional[dict] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, CMUP courant en texte).
        ``initial['lignes']`` : liste de dicts {article_id, article_label, quantite, cout_unitaire}."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles
        self._lines: list[dict] = list(initial.get("lignes", []))
        self._requested_action = "draft"

        self.setWindowTitle("Sortie de stock")
        self.setModal(True)
        # Mission 5.4, Évolution A.1 : un peu plus large qu'avant (560px)
        # pour lire confortablement référence + désignation + CMUP dans la
        # liste de résultats de ``article_search_panel`` ci-dessous, sans
        # jamais nécessiter de défilement horizontal.
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.motif_combo = QComboBox(self)
        for motif_id, libelle in motifs:
            self.motif_combo.addItem(libelle, motif_id)
        self._select_combo_data(self.motif_combo, initial.get("motif_id"))
        form.addRow(required_label("Motif"), self.motif_combo)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        # Confort d'interface uniquement (§ dates futures) : le calendrier
        # ne propose pas de date future, mais la garantie réelle est
        # appliquée côté service (ExitService.create_exit/update_exit).
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setDate(date_to_qdate(initial.get("date") or date.today()))
        form.addRow(required_label("Date"), self.date_edit)

        self.beneficiaire_edit = QLineEdit(self)
        self.beneficiaire_edit.setText(initial.get("beneficiaire", "") or "")
        form.addRow("Bénéficiaire / service", self.beneficiaire_edit)

        self.reference_edit = QLineEdit(self)
        self.reference_edit.setText(initial.get("reference", "") or "")
        form.addRow("Référence document", self.reference_edit)

        self.commentaire_edit = QTextEdit(self)
        self.commentaire_edit.setPlainText(initial.get("commentaire", "") or "")
        self.commentaire_edit.setFixedHeight(50)
        form.addRow("Commentaire", self.commentaire_edit)

        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

        # Mission 5.3 : recherche en direct plutôt qu'un dialogue séparé par
        # ligne (``ExitLineFormDialog``, désormais inutilisé) — double-clic
        # sur un résultat pour ajouter directement la ligne, exactement
        # comme le panneau gauche de la caisse Ventes/Locations.
        self.article_search_panel = ArticleSearchPanel(
            [(article_id, f"{label}  —  CMUP {cmup}") for article_id, label, cmup in articles], self
        )
        self.article_search_panel.article_activated.connect(self._on_article_activated)
        layout.addWidget(self.article_search_panel)

        # Mission 5.4, Évolution A.2 : compteur dynamique, actualisé par
        # ``_refresh_lines_table`` — reflète toujours le nombre réel de
        # lignes du tableau, jamais le nombre d'articles du catalogue.
        self.lines_label = QLabel("Lignes (0)", self)
        layout.addWidget(self.lines_label)

        self.lines_table = QTableWidget(0, len(_LINE_COLUMNS), self)
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lines_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        # Mission 5.3 : seule la Quantité devient éditable en place (même
        # déclencheur/délégué que les tableaux de caisse) — le Coût (CMUP)
        # reste en lecture seule, aucune règle de valorisation/CMUP changée.
        self.lines_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed
        )
        lines_header = self.lines_table.horizontalHeader()
        lines_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lines_header.setSectionResizeMode(_QUANTITY_COLUMN, QHeaderView.ResizeMode.Interactive)
        self.lines_table.setColumnWidth(_QUANTITY_COLUMN, 95)
        lines_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.lines_table.setColumnWidth(2, 120)
        self._quantity_delegate = QuantityEditDelegate(self.lines_table)
        self.lines_table.setItemDelegateForColumn(_QUANTITY_COLUMN, self._quantity_delegate)
        self.lines_table.itemChanged.connect(self._on_line_item_changed)
        layout.addWidget(self.lines_table)

        lines_button_row = QHBoxLayout()
        self.remove_line_button = QPushButton("Supprimer la ligne", self)
        self.remove_line_button.setProperty("variant", "danger")
        lines_button_row.addWidget(self.remove_line_button)
        lines_button_row.addStretch(1)
        layout.addLayout(lines_button_row)

        self.total_label = QLabel("Total : 0", self)
        self.total_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.total_label)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Enregistrer en brouillon", self)
        self.save_button.setProperty("variant", "primary")
        self.validate_button = QPushButton("Valider", self)
        self.validate_button.setProperty("variant", "success")
        self.validate_button.setDefault(True)
        self.validate_button.setStyleSheet("font-weight: 600;")
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.validate_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._on_save_clicked)
        self.validate_button.clicked.connect(self._on_validate_clicked)
        self.remove_line_button.clicked.connect(self._on_remove_line_clicked)

        self._refresh_lines_table()

    @staticmethod
    def _select_combo_data(combo: QComboBox, data) -> None:
        if data is None:
            return
        index = combo.findData(data)
        if index >= 0:
            combo.setCurrentIndex(index)

    # -- gestion des lignes ---------------------------------------------------

    def _refresh_lines_table(self) -> None:
        # Mission 5.3 : la Quantité est désormais éditable en place —
        # ``blockSignals`` évite que la reconstruction ci-dessous ne
        # redéclenche ``_on_line_item_changed`` pour chaque cellule
        # repeuplée (même principe que
        # ``SalesPage._refresh_caisse_lines_table``).
        self.lines_table.blockSignals(True)
        self.lines_table.setRowCount(len(self._lines))
        total = Decimal("0")
        for row, line in enumerate(self._lines):
            article_item = QTableWidgetItem(line["article_label"])
            article_item.setFlags(article_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.lines_table.setItem(row, 0, article_item)

            quantite_item = QTableWidgetItem(format_quantity(line["quantite"]))
            quantite_item.setFlags(quantite_item.flags() | Qt.ItemFlag.ItemIsEditable)
            quantite_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lines_table.setItem(row, _QUANTITY_COLUMN, quantite_item)

            # Coût (CMUP) : jamais modifiable ici, aucune règle de
            # valorisation/CMUP changée — strictement informatif, à
            # l'identique d'avant ce correctif.
            cout_item = QTableWidgetItem(str(line["cout_unitaire"]))
            cout_item.setFlags(cout_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.lines_table.setItem(row, 2, cout_item)

            try:
                montant = Decimal(str(line["quantite"])) * Decimal(str(line["cout_unitaire"]))
            except Exception:
                montant = Decimal("0")
            total += montant
            montant_item = QTableWidgetItem(str(montant))
            montant_item.setFlags(montant_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.lines_table.setItem(row, 3, montant_item)
        self.lines_table.blockSignals(False)
        # Mission 5.5, Évolution A : 2 lignes de données visibles par défaut
        # (plus l'en-tête), défilement vertical au-delà — même utilitaire
        # que les tableaux de consultation (Mission 5.4), rappelé ici à
        # chaque changement du nombre de lignes.
        apply_compact_row_height(self.lines_table, visible_rows=2)
        self.total_label.setText(f"Total : {total}")
        # Mission 5.4, Évolution A.2 : reflète toujours le nombre réel de
        # lignes du tableau — recalculé ici, seul point de passage commun à
        # l'ajout (``_on_article_activated``) et à la suppression
        # (``_on_remove_line_clicked``).
        self.lines_label.setText(f"Lignes ({len(self._lines)})")

    def _on_article_activated(self, article_id: int) -> None:
        """Mission 5.3 : point d'entrée unique pour ajouter une ligne,
        appelé sur double-clic d'un résultat de ``article_search_panel`` —
        quantité 1 et CMUP courant de l'article, à l'identique de ce que
        préremplissait l'ancien ``ExitLineFormDialog``. Le CMUP reste
        ensuite en lecture seule (voir ``_refresh_lines_table``) ; seule la
        quantité est librement modifiable directement dans le tableau."""
        article_label = "?"
        cout_unitaire = Decimal("0")
        for aid, label, cmup in self._articles:
            if aid == article_id:
                article_label = label
                cout_unitaire = Decimal(str(cmup))
                break
        self._lines.append(
            {
                "article_id": article_id,
                "article_label": article_label,
                "quantite": Decimal("1"),
                "cout_unitaire": cout_unitaire,
            }
        )
        self._refresh_lines_table()
        self.article_search_panel.clear_search()

    def _on_line_item_changed(self, item: QTableWidgetItem) -> None:
        """Mission 5.3 : point d'entrée unique pour toute modification de
        quantité saisie directement dans le tableau — une valeur invalide
        est refusée avec un message clair et la cellule reprend sa valeur
        précédente, jamais de ligne laissée dans un état incohérent (même
        principe que ``SalesPage._on_caisse_line_item_changed``)."""
        if item.column() != _QUANTITY_COLUMN:
            return
        row = item.row()
        if row >= len(self._lines):
            return
        try:
            nouvelle_quantite = parse_decimal(item.text(), "quantité")
            if nouvelle_quantite <= 0:
                raise ValidationError("La quantité doit être strictement positive.")
        except ValidationError as exc:
            self.set_error(str(exc))
            self._refresh_lines_table()
            return
        self.set_error("")
        self._lines[row]["quantite"] = nouvelle_quantite
        self._refresh_lines_table()

    def _on_remove_line_clicked(self) -> None:
        selected = self.lines_table.selectionModel().selectedRows()
        if not selected:
            return
        row = selected[0].row()
        del self._lines[row]
        self._refresh_lines_table()

    def values(self) -> dict:
        return {
            "motif_id": self.motif_combo.currentData(),
            "date": self.date_edit.date().toPython(),
            "beneficiaire": self.beneficiaire_edit.text(),
            "reference": self.reference_edit.text(),
            "commentaire": self.commentaire_edit.toPlainText(),
            "lignes": list(self._lines),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)

    # -- distinction brouillon / validation directe ---------------------------

    def _on_save_clicked(self) -> None:
        self._requested_action = "draft"
        self.accept()

    def _on_validate_clicked(self) -> None:
        self._requested_action = "validate"
        self.save_button.setEnabled(False)
        self.validate_button.setEnabled(False)
        self.accept()

    def requested_action(self) -> str:
        """'draft' ou 'validate' selon le bouton actionné — ``accept()`` étant
        commun aux deux, c'est le seul moyen pour l'appelant de distinguer les
        deux intentions une fois le dialogue fermé."""
        return self._requested_action
