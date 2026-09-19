"""Formulaire de création/modification d'une vente (date + client optionnel
+ lignes dynamiques).

Le client est optionnel — une vente comptant (sans client) reste
parfaitement valide, voir ``SaleService``. Le sélecteur ne propose que les
clients actifs transmis par l'appelant (``SalesPage``, qui filtre déjà via
``ClientService.list_clients(include_inactive=False)``) ; ce formulaire ne
connaît rien du service métier lui-même.

Création de client « à la volée » (§5 du lot Clients) : le bouton « Nouveau
client… » délègue entièrement la création à ``on_create_client`` (callback
fourni par ``SalesPage``, qui appelle ``ClientService.create_client`` et gère
la validation) — ce dialogue reste ouvert pendant l'opération, avec la date
et les lignes déjà saisies intactes ; seul le résultat (id, nom) est ajouté
au sélecteur et sélectionné.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QComboBox,
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
from app.views.common import parse_decimal
from app.views.sale_line_form_dialog import SaleLineFormDialog

_LINE_COLUMNS = ["Article", "Quantité", "Prix unitaire", "Montant"]
_NO_CLIENT_LABEL = "(Aucun client / Vente comptant)"


class SaleFormDialog(QDialog):
    def __init__(
        self,
        articles: list[tuple[int, str, str]],
        clients: list[tuple[int, str]],
        initial: Optional[dict] = None,
        on_create_client: Optional[Callable[[], Optional[tuple[int, str]]]] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, prix de vente actuel en texte).
        ``clients`` : liste de tuples (id, nom) — clients actifs sélectionnables.
        ``initial['lignes']`` : liste de dicts {article_id, article_label, quantite, prix_unitaire}.
        ``initial['client_id']`` : identifiant du client présélectionné, ou None (vente comptant)."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles
        self._clients: list[tuple[int, str]] = list(clients)
        self._on_create_client = on_create_client
        self._lines: list[dict] = list(initial.get("lignes", []))

        self.setWindowTitle("Vente")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.date_edit = QLineEdit(self)
        self.date_edit.setPlaceholderText("AAAA-MM-JJ")
        self.date_edit.setText(initial.get("date", "") or "")
        form.addRow("Date", self.date_edit)

        client_row = QHBoxLayout()
        self.client_combo = QComboBox(self)
        client_row.addWidget(self.client_combo)
        self.new_client_button = QPushButton("Nouveau client…", self)
        self.new_client_button.setEnabled(on_create_client is not None)
        client_row.addWidget(self.new_client_button)
        form.addRow("Client", client_row)
        self._refresh_client_combo(selected_id=initial.get("client_id"))

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
        self.new_client_button.clicked.connect(self._on_new_client_clicked)

        self._refresh_lines_table()

    # -- gestion du client ------------------------------------------------------

    def _refresh_client_combo(self, selected_id: Optional[int] = None) -> None:
        self.client_combo.blockSignals(True)
        self.client_combo.clear()
        self.client_combo.addItem(_NO_CLIENT_LABEL, None)
        for client_id, nom in self._clients:
            self.client_combo.addItem(nom, client_id)
        self.client_combo.blockSignals(False)
        if selected_id is not None:
            index = self.client_combo.findData(selected_id)
            if index != -1:
                self.client_combo.setCurrentIndex(index)

    def _on_new_client_clicked(self) -> None:
        if self._on_create_client is None:
            return
        result = self._on_create_client()
        if result is None:
            return
        client_id, client_nom = result
        self._clients.append((client_id, client_nom))
        self._refresh_client_combo(selected_id=client_id)

    # -- gestion des lignes ---------------------------------------------------

    def _refresh_lines_table(self) -> None:
        self.lines_table.setRowCount(len(self._lines))
        total = Decimal("0")
        for row, line in enumerate(self._lines):
            self.lines_table.setItem(row, 0, QTableWidgetItem(line["article_label"]))
            self.lines_table.setItem(row, 1, QTableWidgetItem(str(line["quantite"])))
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
            dialog = SaleLineFormDialog(self._articles, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
            try:
                if values["article_id"] is None:
                    raise ValidationError("Veuillez sélectionner un article.")
                quantite = parse_decimal(values["quantite"], "quantité")
                prix_unitaire = parse_decimal(values["prix_unitaire"], "prix de vente unitaire")
                if quantite <= 0:
                    raise ValidationError("La quantité doit être strictement positive.")
                if prix_unitaire < 0:
                    raise ValidationError("Le prix de vente unitaire ne peut pas être négatif.")
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
            "date": self.date_edit.text(),
            "client_id": self.client_combo.currentData(),
            "lignes": list(self._lines),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
