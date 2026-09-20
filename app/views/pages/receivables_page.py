"""Écran « Créances clients » (§5.7) : vue filtrée des ventes validées avec
leur état de paiement — réutilise intégralement ``SaleService.list_sales``
(mêmes filtres client/statut de paiement/période que l'écran Ventes),
jamais une architecture parallèle ni un nouveau modèle de lecture. Ne
prétend à aucun tableau de bord financier complet (§5.7) : seulement une
liste filtrable des ventes non intégralement soldées, plus un raccourci
vers la créance totale d'un client sélectionné.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import StatutOperation, StatutPaiement
from app.services.auth.permission_service import PermissionService
from app.services.clients.client_service import ClientService
from app.services.sales.sale_service import SaleService
from app.services.settings.company_settings_service import get_effective_currency
from app.utils.exceptions import AppError
from app.utils.money import format_money
from app.views.optional_date_edit import OptionalDateEdit

_COLUMNS = ["Client", "Référence vente", "Date", "Montant total", "Montant payé", "Reste à payer", "Statut"]

_STATUT_PAIEMENT_FILTERS = [
    ("Toutes (non annulées)", None),
    ("Non payée", StatutPaiement.NON_PAYEE),
    ("Partiellement payée", StatutPaiement.PARTIELLEMENT_PAYEE),
    ("Payée", StatutPaiement.PAYEE),
]

_STATUT_PAIEMENT_LABELS = {
    StatutPaiement.NON_PAYEE: "Non payée",
    StatutPaiement.PARTIELLEMENT_PAYEE: "Partiellement payée",
    StatutPaiement.PAYEE: "Payée",
}

_ALL_CLIENTS_LABEL = "(Tous les clients)"


class ReceivablesPage(QWidget):
    def __init__(
        self,
        sale_service: SaleService,
        client_service: ClientService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sale_service = sale_service
        self._client_service = client_service
        self._permissions = permission_service
        self._currency_code = get_effective_currency()

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher (numéro de vente)…")
        toolbar.addWidget(self.search_edit)

        self.client_filter_combo = QComboBox(self)
        toolbar.addWidget(self.client_filter_combo)
        self._reload_client_filter_combo()

        self.statut_paiement_combo = QComboBox(self)
        for label, value in _STATUT_PAIEMENT_FILTERS:
            self.statut_paiement_combo.addItem(label, value)
        toolbar.addWidget(self.statut_paiement_combo)

        toolbar.addWidget(QLabel("Du", self))
        self.date_from_edit = OptionalDateEdit(self)
        toolbar.addWidget(self.date_from_edit)
        toolbar.addWidget(QLabel("Au", self))
        self.date_to_edit = OptionalDateEdit(self)
        toolbar.addWidget(self.date_to_edit)

        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.client_total_label = QLabel("", self)
        layout.addWidget(self.client_total_label)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.search_edit.textChanged.connect(self.refresh)
        self.client_filter_combo.currentIndexChanged.connect(self.refresh)
        self.statut_paiement_combo.currentIndexChanged.connect(self.refresh)
        # OptionalDateEdit n'expose pas de signal unique : rafraîchir sur la
        # case à cocher et sur le changement de date (même principe que les
        # filtres texte/liste ci-dessus — pas de bouton « Générer » séparé).
        self.date_from_edit.checkbox.toggled.connect(self.refresh)
        self.date_from_edit.date_edit.dateChanged.connect(self.refresh)
        self.date_to_edit.checkbox.toggled.connect(self.refresh)
        self.date_to_edit.date_edit.dateChanged.connect(self.refresh)

        self.refresh()

    def _reload_client_filter_combo(self) -> None:
        self.client_filter_combo.clear()
        self.client_filter_combo.addItem(_ALL_CLIENTS_LABEL, None)
        try:
            clients = self._client_service.list_clients(include_inactive=True)
        except AppError:
            clients = []
        for client in clients:
            label = client.nom if client.actif else f"{client.nom} (inactif)"
            self.client_filter_combo.addItem(label, client.id)

    def refresh(self) -> None:
        client_id = self.client_filter_combo.currentData()
        statut_paiement = self.statut_paiement_combo.currentData()
        date_from = self.date_from_edit.date_or_none()
        date_to = self.date_to_edit.date_or_none()

        try:
            sales = self._sale_service.list_sales(
                search=self.search_edit.text(),
                statut=StatutOperation.VALIDEE,
                client_id=client_id,
                statut_paiement=statut_paiement,
                date_from=date_from,
                date_to=date_to,
            )
        except AppError:
            sales = []

        self.table.setRowCount(len(sales))
        for row, sale in enumerate(sales):
            self.table.setItem(row, 0, QTableWidgetItem(sale.client_nom or "(Vente comptant sans client)"))
            self.table.setItem(row, 1, QTableWidgetItem(sale.numero))
            self.table.setItem(row, 2, QTableWidgetItem(str(sale.date)))
            self.table.setItem(row, 3, QTableWidgetItem(format_money(sale.total, self._currency_code)))
            self.table.setItem(row, 4, QTableWidgetItem(format_money(sale.montant_paye, self._currency_code)))
            self.table.setItem(row, 5, QTableWidgetItem(format_money(sale.reste_a_payer, self._currency_code)))
            self.table.setItem(
                row, 6, QTableWidgetItem(_STATUT_PAIEMENT_LABELS.get(sale.statut_paiement, str(sale.statut_paiement)))
            )

        self._refresh_client_total(client_id)

    def _refresh_client_total(self, client_id: Optional[int]) -> None:
        if client_id is None:
            self.client_total_label.setText("")
            return
        try:
            summary = self._sale_service.get_client_receivable_summary(client_id)
        except AppError:
            self.client_total_label.setText("")
            return
        self.client_total_label.setText(
            f"Créance client — Total ventes : {format_money(summary.total_ventes, self._currency_code)}  |  "
            f"Total payé : {format_money(summary.total_paye, self._currency_code)}  |  "
            f"Reste à payer : {format_money(summary.total_reste_a_payer, self._currency_code)}"
        )
