"""Formulaire de création/modification d'un inventaire (date + lignes
dynamiques).

Le stock actuel n'est jamais un champ modifiable ici : chaque ligne affiche
le stock théorique système (lecture seule) à côté du stock compté (seule
saisie), et l'écart est recalculé à l'affichage pour donner un retour
immédiat — la valeur qui fait foi reste celle capturée par le service au
moment de l'ajout de la ligne.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
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
    QVBoxLayout,
    QWidget,
)

from app.utils.exceptions import ValidationError
from app.utils.quantity import format_quantity, format_quantity_signed
from app.views.common import date_to_qdate, parse_decimal
from app.views.inventory_line_form_dialog import InventoryLineFormDialog

_LINE_COLUMNS = ["Article", "Stock théorique", "Stock compté", "Écart"]


class InventoryFormDialog(QDialog):
    def __init__(
        self,
        articles: list[tuple[int, str, str]],
        initial: Optional[dict] = None,
        on_lookup_barcode: Optional[Callable[[str], Optional[tuple[int, str, str]]]] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, stock théorique actuel en texte).
        ``initial['lignes']`` : liste de dicts {article_id, article_label, stock_theorique, stock_physique}.
        ``on_lookup_barcode`` : callback de scan (voir ``SaleFormDialog``,
        même contrat) — ici, l'article trouvé pré-sélectionne le formulaire
        d'ajout de ligne habituel plutôt que d'ajouter directement une ligne,
        le stock compté restant une saisie manuelle obligatoire."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles
        self._on_lookup_barcode = on_lookup_barcode
        self._lines: list[dict] = list(initial.get("lignes", []))

        self.setWindowTitle("Inventaire")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        # Confort d'interface uniquement (§ dates futures) : le calendrier
        # ne propose pas de date future, mais la garantie réelle est
        # appliquée côté service (InventoryService.create_inventory/update_inventory).
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setDate(date_to_qdate(initial.get("date") or date.today()))
        form.addRow("Date", self.date_edit)

        layout.addLayout(form)

        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Scanner / code-barres", self))
        self.scan_edit = QLineEdit(self)
        self.scan_edit.setPlaceholderText("Scanner un article ou saisir son code-barres puis Entrée…")
        self.scan_edit.setEnabled(on_lookup_barcode is not None)
        scan_row.addWidget(self.scan_edit)
        layout.addLayout(scan_row)

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
        self.add_line_button.clicked.connect(lambda: self._on_add_line_clicked())
        self.remove_line_button.clicked.connect(self._on_remove_line_clicked)
        self.scan_edit.returnPressed.connect(self._on_scan_entered)

        self._refresh_lines_table()

    # -- scan code-barres (lecteur USB « keyboard wedge ») ---------------------

    def _on_scan_entered(self) -> None:
        """Article actif trouvé -> ouvre le formulaire d'ajout de ligne
        habituel avec cet article pré-sélectionné (le stock compté reste une
        saisie manuelle, jamais devinée). Introuvable -> message clair,
        aucune ligne ajoutée."""
        code = self.scan_edit.text().strip()
        self.scan_edit.clear()
        if not code or self._on_lookup_barcode is None:
            return

        result = self._on_lookup_barcode(code)
        if result is None:
            QMessageBox.warning(
                self, "Article introuvable",
                f"Aucun article actif ne correspond au code-barres « {code} ».",
            )
            return

        article_id, _label, _stock_theorique = result
        self._on_add_line_clicked(initial={"article_id": article_id})

    # -- gestion des lignes ---------------------------------------------------

    def _refresh_lines_table(self) -> None:
        self.lines_table.setRowCount(len(self._lines))
        for row, line in enumerate(self._lines):
            self.lines_table.setItem(row, 0, QTableWidgetItem(line["article_label"]))
            self.lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(line["stock_theorique"])))
            self.lines_table.setItem(row, 2, QTableWidgetItem(format_quantity(line["stock_physique"])))
            try:
                ecart = Decimal(str(line["stock_physique"])) - Decimal(str(line["stock_theorique"]))
                ecart_text = format_quantity_signed(ecart)
            except Exception:
                ecart_text = "—"
            self.lines_table.setItem(row, 3, QTableWidgetItem(ecart_text))

    def _on_add_line_clicked(self, initial: Optional[dict] = None) -> None:
        while True:
            dialog = InventoryLineFormDialog(self._articles, initial, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
            try:
                if values["article_id"] is None:
                    raise ValidationError("Veuillez sélectionner un article.")
                stock_physique = parse_decimal(values["stock_physique"], "stock compté")
                if stock_physique < 0:
                    raise ValidationError("Le stock compté ne peut pas être négatif.")
            except ValidationError as exc:
                QMessageBox.warning(self, "Ligne invalide", str(exc))
                continue

            article_label = "?"
            stock_theorique = Decimal("0")
            for article_id, label, theorique in self._articles:
                if article_id == values["article_id"]:
                    article_label = label
                    stock_theorique = Decimal(str(theorique))
                    break

            self._lines.append(
                {
                    "article_id": values["article_id"],
                    "article_label": article_label,
                    "stock_theorique": stock_theorique,
                    "stock_physique": stock_physique,
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
            "date": self.date_edit.date().toPython(),
            "lignes": list(self._lines),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
