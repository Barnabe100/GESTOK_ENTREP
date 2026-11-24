"""Consultation détaillée, en lecture seule, d'un client : informations,
statut, et historique des ventes qui lui sont associées.

Une vente historique reste affichée ici même après désactivation du client
(l'historique ne dépend que de ``Vente.client_id``, jamais du statut actuel
du client — voir ``ClientService``/``SaleService``, ce dialogue lui-même
n'appelle aucun service : les données sont déjà chargées par ``ClientsPage``).

Mission 5.6, §2 : même logique de présentation/dimensionnement que
``sale_detail_dialog.py``/``location_detail_dialog.py`` — en-tête sur
plusieurs colonnes (:class:`MultiColumnForm`, partagé) au lieu d'une colonne
verticale unique, historique des ventes plafonné à 5 lignes visibles
(``apply_compact_row_height``, partagé), et hauteur initiale adaptée au
contenu réel (``apply_content_driven_height``, partagé — voir §1 de cette
même mission) plutôt qu'une hauteur fixe. Aucun champ ni colonne
ajouté/retiré ; aucune action n'existait déjà sur l'historique des ventes
(aucune ouverture de détail de vente depuis ce dialogue) — rien à préserver
sur ce point au-delà de ne pas en introduire une.
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
from app.services.clients.client_service import ClientSummary
from app.services.sales.sale_service import VenteSummary
from app.utils.money import format_money
from app.views.design_system import MultiColumnForm, apply_compact_row_height, apply_content_driven_height

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
        # Mission 5.6, §2.3 : largeur confortable pour que les 3 colonnes
        # d'informations et les 4 colonnes de l'historique restent visibles
        # sans défilement horizontal. La hauteur n'est plus fixée ici — voir
        # ``apply_content_driven_height`` en fin de constructeur.
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)

        # -- informations générales --------------------------------------------------
        header_group = QGroupBox("Informations générales", content)
        header_group_layout = QVBoxLayout(header_group)

        header_form = MultiColumnForm(header_group, column_count=3)
        header_group_layout.addWidget(header_form.widget)

        header_form.add_row(0, "Nom", QLabel(client.nom, header_group))
        header_form.add_row(1, "Téléphone", QLabel(client.telephone or "—", header_group))
        header_form.add_row(2, "Email", QLabel(client.email or "—", header_group))
        adresse_label = QLabel(client.adresse or "—", header_group)
        adresse_label.setWordWrap(True)
        header_form.add_row(0, "Adresse", adresse_label)
        observations_label = QLabel(client.observations or "—", header_group)
        observations_label.setWordWrap(True)
        header_form.add_row(1, "Observations", observations_label)
        header_form.add_row(2, "Statut", QLabel("Actif" if client.actif else "Inactif", header_group))
        header_form.add_row(
            0, "Créé le", QLabel(client.date_creation.strftime("%Y-%m-%d %H:%M"), header_group)
        )
        header_form.add_row(
            1, "Modifié le", QLabel(client.date_modification.strftime("%Y-%m-%d %H:%M"), header_group)
        )

        content_layout.addWidget(header_group)

        # -- historique des ventes -----------------------------------------------------
        sales_group = QGroupBox("Historique des ventes", content)
        sales_layout = QVBoxLayout(sales_group)
        self.sales_table = QTableWidget(len(sales), len(_SALE_COLUMNS), sales_group)
        self.sales_table.setAlternatingRowColors(True)
        self.sales_table.setHorizontalHeaderLabels(_SALE_COLUMNS)
        self.sales_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        sales_header = self.sales_table.horizontalHeader()
        sales_header.setStretchLastSection(True)
        for col, width in ((0, 140), (1, 110), (2, 110)):
            sales_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.sales_table.setColumnWidth(col, width)
        for row, sale in enumerate(sales):
            self.sales_table.setItem(row, 0, QTableWidgetItem(sale.numero))
            self.sales_table.setItem(row, 1, QTableWidgetItem(str(sale.date)))
            self.sales_table.setItem(row, 2, QTableWidgetItem(_STATUT_LABELS.get(sale.statut, str(sale.statut))))
            self.sales_table.setItem(row, 3, QTableWidgetItem(format_money(sale.total, currency_code)))
        # Mission 5.6, §2.2 : 5 lignes de données visibles par défaut (plus
        # l'en-tête), défilement vertical au-delà — toutes les ventes
        # restent chargées dans le tableau, jamais limitées en amont ; les
        # ventes d'un client ne changent jamais après construction de ce
        # dialogue (consultation seule), un seul appel suffit ici (même
        # principe que ``sale_detail_dialog.py``).
        apply_compact_row_height(self.sales_table, visible_rows=5)
        sales_layout.addWidget(self.sales_table)

        if not sales:
            sales_layout.addWidget(QLabel("Aucune vente associée à ce client.", sales_group))

        content_layout.addWidget(sales_group)

        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        # Mission 5.6, §2.3 : hauteur initiale adaptée au contenu réel —
        # aucun grand espace vide avec peu de ventes, aucun étirement
        # artificiel.
        apply_content_driven_height(self, content, 700, extra_height=self.close_button.sizeHint().height())
