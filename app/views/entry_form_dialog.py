"""Formulaire de création/modification d'une entrée de stock (en-tête + lignes
dynamiques).

Ne connaît rien du service métier : la saisie des lignes est gérée localement
(ajout/suppression, calcul d'affichage du montant et du total) mais la
validation métier définitive (existence/statut de l'article, quantité
strictement positive, etc.) reste de la responsabilité d'``EntryService``,
appelé par :class:`EntriesPage` à la soumission — à l'identique des autres
formulaires (Articles, Fournisseurs...).

Mission 5.3 : la sélection d'article reprend l'ergonomie déjà en place dans
les écrans de caisse Ventes/Locations (``SalesPage``/``LocationsPage``) —
recherche en direct (:class:`ArticleSearchPanel`, partagé) plutôt qu'un
dialogue séparé par ligne. La quantité ET le prix d'achat unitaire
deviennent éditables directement dans le tableau (même délégué
``QuantityEditDelegate`` que les tableaux de caisse), le prix restant
librement modifiable comme avant (aucune règle métier changée — la
validation définitive reste entièrement dans ``EntryService``).
``EntryLineFormDialog`` n'est plus utilisé par ce formulaire mais n'est pas
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
from app.views.design_system import QuantityEditDelegate

_LINE_COLUMNS = ["Article", "Quantité", "Prix unitaire", "Montant"]
_QUANTITY_COLUMN = 1
_PRICE_COLUMN = 2


class EntryFormDialog(QDialog):
    def __init__(
        self,
        suppliers: list[tuple[int, str]],
        articles: list[tuple[int, str, str]],
        initial: Optional[dict] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, prix d'achat par défaut en texte).
        ``initial['lignes']`` : liste de dicts {article_id, article_label, quantite, prix_unitaire}."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles
        self._lines: list[dict] = list(initial.get("lignes", []))
        self._requested_action = "draft"

        self.setWindowTitle("Entrée de stock")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.supplier_combo = QComboBox(self)
        for supplier_id, nom in suppliers:
            self.supplier_combo.addItem(nom, supplier_id)
        self._select_combo_data(self.supplier_combo, initial.get("fournisseur_id"))
        form.addRow(required_label("Fournisseur"), self.supplier_combo)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        # Confort d'interface uniquement (§ dates futures) : le calendrier
        # ne propose pas de date future, mais la garantie réelle est
        # appliquée côté service (EntryService.create_entry/update_entry).
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setDate(date_to_qdate(initial.get("date") or date.today()))
        form.addRow(required_label("Date"), self.date_edit)

        self.reference_document_edit = QLineEdit(self)
        self.reference_document_edit.setText(initial.get("reference_document", "") or "")
        form.addRow("Référence document", self.reference_document_edit)

        self.commentaire_edit = QTextEdit(self)
        self.commentaire_edit.setPlainText(initial.get("commentaire", "") or "")
        self.commentaire_edit.setFixedHeight(50)
        form.addRow("Commentaire", self.commentaire_edit)

        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

        # Mission 5.3 : recherche en direct plutôt qu'un dialogue séparé par
        # ligne (``EntryLineFormDialog``, désormais inutilisé) — double-clic
        # sur un résultat pour ajouter directement la ligne, exactement
        # comme le panneau gauche de la caisse Ventes/Locations.
        self.article_search_panel = ArticleSearchPanel(
            [(article_id, f"{label}  —  {prix_achat}") for article_id, label, prix_achat in articles], self
        )
        self.article_search_panel.article_activated.connect(self._on_article_activated)
        layout.addWidget(self.article_search_panel)

        layout.addWidget(QLabel("Lignes", self))

        self.lines_table = QTableWidget(0, len(_LINE_COLUMNS), self)
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lines_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        # Mission 5.3 : Quantité ET Prix d'achat unitaire éditables en place
        # (même déclencheur et même délégué que les tableaux de caisse) — le
        # prix reste librement modifiable, comme avant via l'ancien
        # dialogue séparé, seule la façon de le modifier change.
        self.lines_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed
        )
        lines_header = self.lines_table.horizontalHeader()
        lines_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((_QUANTITY_COLUMN, 95), (_PRICE_COLUMN, 120)):
            lines_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.lines_table.setColumnWidth(col, width)
        self.lines_table.verticalHeader().setDefaultSectionSize(36)
        self._quantity_delegate = QuantityEditDelegate(self.lines_table)
        self.lines_table.setItemDelegateForColumn(_QUANTITY_COLUMN, self._quantity_delegate)
        self.lines_table.setItemDelegateForColumn(_PRICE_COLUMN, self._quantity_delegate)
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
        # Mission 5.3 : les colonnes Quantité/Prix unitaire sont désormais
        # éditables en place — ``blockSignals`` évite que la reconstruction
        # ci-dessous ne redéclenche ``_on_line_item_changed`` pour chaque
        # cellule repeuplée (même principe que
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

            prix_item = QTableWidgetItem(str(line["prix_unitaire"]))
            prix_item.setFlags(prix_item.flags() | Qt.ItemFlag.ItemIsEditable)
            prix_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lines_table.setItem(row, _PRICE_COLUMN, prix_item)

            try:
                montant = Decimal(str(line["quantite"])) * Decimal(str(line["prix_unitaire"]))
            except Exception:
                montant = Decimal("0")
            total += montant
            montant_item = QTableWidgetItem(str(montant))
            montant_item.setFlags(montant_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.lines_table.setItem(row, 3, montant_item)
        self.lines_table.blockSignals(False)
        self.total_label.setText(f"Total : {total}")

    def _on_article_activated(self, article_id: int) -> None:
        """Mission 5.3 : point d'entrée unique pour ajouter une ligne,
        appelé sur double-clic d'un résultat de ``article_search_panel`` —
        quantité 1 et prix d'achat par défaut de l'article, à l'identique
        de ce que préremplissait l'ancien ``EntryLineFormDialog``. Les deux
        restent ensuite librement modifiables directement dans le tableau."""
        label = next((lbl for aid, lbl, _ in self._articles if aid == article_id), "?")
        prix_defaut = next(
            (parse_decimal(str(prix), "prix d'achat unitaire") for aid, _, prix in self._articles if aid == article_id),
            Decimal("0"),
        )
        self._lines.append(
            {
                "article_id": article_id,
                "article_label": label,
                "quantite": Decimal("1"),
                "prix_unitaire": prix_defaut,
            }
        )
        self._refresh_lines_table()
        self.article_search_panel.clear_search()

    def _on_line_item_changed(self, item: QTableWidgetItem) -> None:
        """Mission 5.3 : point d'entrée unique pour toute modification de
        quantité ou de prix d'achat unitaire saisie directement dans le
        tableau — une valeur invalide est refusée avec un message clair et
        la cellule reprend sa valeur précédente, jamais de ligne laissée
        dans un état incohérent (même principe que
        ``SalesPage._on_caisse_line_item_changed``)."""
        column = item.column()
        if column not in (_QUANTITY_COLUMN, _PRICE_COLUMN):
            return
        row = item.row()
        if row >= len(self._lines):
            return
        try:
            if column == _QUANTITY_COLUMN:
                nouvelle_valeur = parse_decimal(item.text(), "quantité")
                if nouvelle_valeur <= 0:
                    raise ValidationError("La quantité doit être strictement positive.")
                self._lines[row]["quantite"] = nouvelle_valeur
            else:
                nouvelle_valeur = parse_decimal(item.text(), "prix d'achat unitaire")
                if nouvelle_valeur < 0:
                    raise ValidationError("Le prix d'achat unitaire ne peut pas être négatif.")
                self._lines[row]["prix_unitaire"] = nouvelle_valeur
        except ValidationError as exc:
            self.set_error(str(exc))
            self._refresh_lines_table()
            return
        self.set_error("")
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
            "fournisseur_id": self.supplier_combo.currentData(),
            "date": self.date_edit.date().toPython(),
            "reference_document": self.reference_document_edit.text(),
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
