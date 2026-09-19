"""Consultation détaillée, en lecture seule, d'un client : informations,
statut, et historique des ventes qui lui sont associées.

Une vente historique reste affichée ici même après désactivation du client
(l'historique ne dépend que de ``Vente.client_id``, jamais du statut actuel
du client — voir ``ClientService``/``SaleService``, ce dialogue lui-même
n'appelle aucun service : les données sont déjà chargées par ``ClientsPage``).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import StatutOperation
from app.services.clients.client_service import ClientSummary
from app.services.sales.sale_service import VenteSummary
from app.utils.money import format_money

_SALE_COLUMNS = ["Numéro", "Date", "Statut", "Total"]

_STATUT_LABELS = {
    StatutOperation.BROUILLON: "Brouillon",
    StatutOperation.VALIDEE: "Validée",
    StatutOperation.ANNULEE: "Annulée",
}


class ClientDetailDialog(QDialog):
    def __init__(
        self,
        client: ClientSummary,
        sales: list[VenteSummary],
        currency_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Client — {client.nom}")
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Nom", QLabel(client.nom, self))
        form.addRow("Téléphone", QLabel(client.telephone or "—", self))
        form.addRow("Email", QLabel(client.email or "—", self))
        form.addRow("Adresse", QLabel(client.adresse or "—", self))
        form.addRow("Observations", QLabel(client.observations or "—", self))
        form.addRow("Statut", QLabel("Actif" if client.actif else "Inactif", self))
        form.addRow("Créé le", QLabel(client.date_creation.strftime("%Y-%m-%d %H:%M"), self))
        form.addRow("Modifié le", QLabel(client.date_modification.strftime("%Y-%m-%d %H:%M"), self))

        layout.addLayout(form)

        layout.addWidget(QLabel("Historique des ventes", self))
        self.sales_table = QTableWidget(len(sales), len(_SALE_COLUMNS), self)
        self.sales_table.setHorizontalHeaderLabels(_SALE_COLUMNS)
        self.sales_table.horizontalHeader().setStretchLastSection(True)
        self.sales_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, sale in enumerate(sales):
            self.sales_table.setItem(row, 0, QTableWidgetItem(sale.numero))
            self.sales_table.setItem(row, 1, QTableWidgetItem(str(sale.date)))
            self.sales_table.setItem(row, 2, QTableWidgetItem(_STATUT_LABELS.get(sale.statut, str(sale.statut))))
            self.sales_table.setItem(row, 3, QTableWidgetItem(format_money(sale.total, currency_code)))
        layout.addWidget(self.sales_table)

        if not sales:
            layout.addWidget(QLabel("Aucune vente associée à ce client.", self))

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)
