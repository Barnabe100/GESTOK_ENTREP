"""Formulaire de création/modification d'une entrée de stock (en-tête + lignes
dynamiques).

Ne connaît rien du service métier : la saisie des lignes est gérée localement
(ajout/suppression, calcul d'affichage du montant et du total) mais la
validation métier définitive (existence/statut de l'article, quantité
strictement positive, etc.) reste de la responsabilité d'``EntryService``,
appelé par :class:`EntriesPage` à la soumission — à l'identique des autres
formulaires (Articles, Fournisseurs...).
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
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.utils.exceptions import ValidationError
from app.utils.quantity import format_quantity
from app.views.common import date_to_qdate, parse_decimal
from app.views.entry_line_form_dialog import EntryLineFormDialog

_LINE_COLUMNS = ["Article", "Quantité", "Prix unitaire", "Montant"]


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

        self.setWindowTitle("Entrée de stock")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.supplier_combo = QComboBox(self)
        for supplier_id, nom in suppliers:
            self.supplier_combo.addItem(nom, supplier_id)
        self._select_combo_data(self.supplier_combo, initial.get("fournisseur_id"))
        form.addRow("Fournisseur", self.supplier_combo)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        # Confort d'interface uniquement (§ dates futures) : le calendrier
        # ne propose pas de date future, mais la garantie réelle est
        # appliquée côté service (EntryService.create_entry/update_entry).
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setDate(date_to_qdate(initial.get("date") or date.today()))
        form.addRow("Date", self.date_edit)

        self.reference_document_edit = QLineEdit(self)
        self.reference_document_edit.setText(initial.get("reference_document", "") or "")
        form.addRow("Référence document (optionnel)", self.reference_document_edit)

        self.commentaire_edit = QTextEdit(self)
        self.commentaire_edit.setPlainText(initial.get("commentaire", "") or "")
        self.commentaire_edit.setFixedHeight(50)
        form.addRow("Commentaire", self.commentaire_edit)

        layout.addLayout(form)

        layout.addWidget(QLabel("Lignes", self))

        self.lines_table = QTableWidget(0, len(_LINE_COLUMNS), self)
        self.lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lines_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.lines_table)

        lines_button_row = QHBoxLayout()
        self.add_line_button = QPushButton("Ajouter une ligne", self)
        self.remove_line_button = QPushButton("Supprimer la ligne", self)
        lines_button_row.addWidget(self.add_line_button)
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
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        self.add_line_button.clicked.connect(self._on_add_line_clicked)
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
        self.lines_table.setRowCount(len(self._lines))
        total = Decimal("0")
        for row, line in enumerate(self._lines):
            self.lines_table.setItem(row, 0, QTableWidgetItem(line["article_label"]))
            self.lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(line["quantite"])))
            self.lines_table.setItem(row, 2, QTableWidgetItem(str(line["prix_unitaire"])))
            try:
                montant = Decimal(str(line["quantite"])) * Decimal(str(line["prix_unitaire"]))
            except Exception:
                montant = Decimal("0")
            total += montant
            self.lines_table.setItem(row, 3, QTableWidgetItem(str(montant)))
        self.total_label.setText(f"Total : {total}")

    def _on_add_line_clicked(self) -> None:
        while True:
            dialog = EntryLineFormDialog(self._articles, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
            try:
                if values["article_id"] is None:
                    raise ValidationError("Veuillez sélectionner un article.")
                quantite = parse_decimal(values["quantite"], "quantité")
                prix_unitaire = parse_decimal(values["prix_unitaire"], "prix d'achat unitaire")
                if quantite <= 0:
                    raise ValidationError("La quantité doit être strictement positive.")
                if prix_unitaire < 0:
                    raise ValidationError("Le prix d'achat unitaire ne peut pas être négatif.")
            except ValidationError as exc:
                QMessageBox.warning(self, "Ligne invalide", str(exc))
                continue

            article_label = next(
                (label for article_id, label, _ in self._articles if article_id == values["article_id"]),
                "?",
            )
            self._lines.append(
                {
                    "article_id": values["article_id"],
                    "article_label": article_label,
                    "quantite": quantite,
                    "prix_unitaire": prix_unitaire,
                }
            )
            self._refresh_lines_table()
            return

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
