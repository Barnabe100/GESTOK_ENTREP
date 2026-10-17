"""Formulaire de création/modification d'une location (date + client
obligatoire + lignes dynamiques).

Contrairement à une vente, le client est obligatoire (voir
``LocationService``) : pas d'équivalent « location comptant ». Le
sélecteur ne propose que les articles en mode Location transmis par
l'appelant (``LocationsPage``, qui filtre déjà via
``ArticleService.list_articles``) ; ce formulaire ne connaît rien du
service métier lui-même.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from PySide6.QtCore import QDate
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
    QVBoxLayout,
    QWidget,
)

from app.utils.exceptions import ValidationError
from app.utils.quantity import format_quantity
from app.views.common import (
    build_required_field_legend,
    date_to_qdate,
    parse_decimal,
    required_label,
)
from app.views.location_line_form_dialog import LocationLineFormDialog

_LINE_COLUMNS = ["Article", "Quantité", "Tarif / jour"]


class LocationFormDialog(QDialog):
    def __init__(
        self,
        articles: list[tuple[int, str, str]],
        clients: list[tuple[int, str]],
        initial: Optional[dict] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé, tarif journalier
        catalogue en texte) — articles en mode Location uniquement.
        ``clients`` : liste de tuples (id, nom) — clients actifs.
        ``initial['lignes']`` : liste de dicts {article_id, article_label, quantite, tarif_jour}."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles
        self._lines: list[dict] = list(initial.get("lignes", []))

        self.setWindowTitle("Location")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setDate(date_to_qdate(initial.get("date") or date.today()))
        form.addRow(required_label("Date"), self.date_edit)

        self.client_combo = QComboBox(self)
        for client_id, nom in clients:
            self.client_combo.addItem(nom, client_id)
        self._select_combo_data(self.client_combo, initial.get("client_id"))
        form.addRow(required_label("Client"), self.client_combo)

        self.commentaire_edit = QLineEdit(self)
        self.commentaire_edit.setText(initial.get("commentaire", "") or "")
        form.addRow("Commentaire", self.commentaire_edit)

        layout.addLayout(form)
        layout.addWidget(build_required_field_legend(self))

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
        for row, line in enumerate(self._lines):
            self.lines_table.setItem(row, 0, QTableWidgetItem(line["article_label"]))
            self.lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(line["quantite"])))
            self.lines_table.setItem(row, 2, QTableWidgetItem(str(line["tarif_jour"])))

    def _on_add_line_clicked(self) -> None:
        while True:
            dialog = LocationLineFormDialog(self._articles, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
            try:
                if values["article_id"] is None:
                    raise ValidationError("Veuillez sélectionner un article.")
                quantite = parse_decimal(values["quantite"], "quantité")
                tarif_jour = parse_decimal(values["tarif_jour"], "tarif journalier")
                if quantite <= 0:
                    raise ValidationError("La quantité doit être strictement positive.")
                if tarif_jour < 0:
                    raise ValidationError("Le tarif journalier ne peut pas être négatif.")
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
                    "tarif_jour": tarif_jour,
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
            "client_id": self.client_combo.currentData(),
            "commentaire": self.commentaire_edit.text(),
            "lignes": list(self._lines),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
