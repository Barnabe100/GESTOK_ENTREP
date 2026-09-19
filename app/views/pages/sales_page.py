"""Page de gestion des ventes.

Toute action (création, modification, suppression de brouillon, validation,
annulation) passe par :class:`SaleService`, qui revérifie la permission côté
service. Une vente en brouillon ne modifie jamais le stock ; seule la
validation le fait — voir ``SaleService.validate_sale``. Modification,
suppression et annulation ne sont proposées que pour les statuts compatibles
(BROUILLON / BROUILLON / VALIDEE respectivement), à la fois dans
l'activation des boutons et dans la logique métier elle-même (défense en
profondeur).

Le client associé à une vente (optionnel — voir ``SaleService``) ne pilote
aucune logique de stock : il n'est qu'une donnée d'en-tête, au même titre
que la date ou le numéro.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import StatutOperation
from app.services.articles.article_service import ArticleService
from app.services.auth.permission_service import PermissionService
from app.services.clients.client_service import ClientService
from app.services.documents.receipt_service import ReceiptService
from app.services.sales.sale_service import SaleService, VenteLigneInput
from app.services.settings.company_settings_service import get_effective_currency
from app.utils.exceptions import AppError, ValidationError
from app.utils.money import format_money
from app.views.client_form_dialog import ClientFormDialog
from app.views.common import confirm_action, run_modal_form
from app.views.sale_detail_dialog import SaleDetailDialog
from app.views.sale_form_dialog import SaleFormDialog

_COLUMNS = ["Numéro", "Date", "Client", "Créée par", "Total", "Statut"]

_STATUT_LABELS = {
    StatutOperation.BROUILLON: "Brouillon",
    StatutOperation.VALIDEE: "Validée",
    StatutOperation.ANNULEE: "Annulée",
}

_STATUS_FILTERS = [
    ("Tous", None),
    ("Brouillon", StatutOperation.BROUILLON),
    ("Validée", StatutOperation.VALIDEE),
    ("Annulée", StatutOperation.ANNULEE),
]

_ALL_CLIENTS_LABEL = "(Tous les clients)"


class SalesPage(QWidget):
    def __init__(
        self,
        sale_service: SaleService,
        article_service: ArticleService,
        client_service: ClientService,
        receipt_service: ReceiptService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sale_service = sale_service
        self._article_service = article_service
        self._client_service = client_service
        self._receipt_service = receipt_service
        self._permissions = permission_service
        self._currency_code = get_effective_currency()

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher (numéro)…")
        toolbar.addWidget(self.search_edit)

        self.status_filter_combo = QComboBox(self)
        for label, value in _STATUS_FILTERS:
            self.status_filter_combo.addItem(label, value)
        toolbar.addWidget(self.status_filter_combo)

        self.client_filter_combo = QComboBox(self)
        toolbar.addWidget(self.client_filter_combo)
        self._reload_client_filter_combo()

        toolbar.addStretch(1)

        self.add_button = QPushButton("Nouvelle vente", self)
        self.add_button.setEnabled(self._permissions.has_permission("SALE_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Supprimer", self)
        toolbar.addWidget(self.delete_button)

        self.detail_button = QPushButton("Détails", self)
        toolbar.addWidget(self.detail_button)

        self.validate_button = QPushButton("Valider", self)
        toolbar.addWidget(self.validate_button)

        self.cancel_button = QPushButton("Annuler", self)
        toolbar.addWidget(self.cancel_button)

        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.search_edit.textChanged.connect(self.refresh)
        self.status_filter_combo.currentIndexChanged.connect(self.refresh)
        self.client_filter_combo.currentIndexChanged.connect(self.refresh)
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        self.detail_button.clicked.connect(self._on_detail_clicked)
        self.validate_button.clicked.connect(self._on_validate_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.table.itemSelectionChanged.connect(self._update_action_buttons)

        self.refresh()

    # -- affichage ---------------------------------------------------------

    def _reload_client_filter_combo(self) -> None:
        """Liste tous les clients (actifs et inactifs : filtrer l'historique
        d'un client désormais désactivé doit rester possible, §8)."""
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
        statut = self.status_filter_combo.currentData()
        client_id = self.client_filter_combo.currentData()
        try:
            sales = self._sale_service.list_sales(
                search=self.search_edit.text(), statut=statut, client_id=client_id
            )
        except AppError:
            self.table.setRowCount(0)
            self._update_action_buttons()
            return

        self.table.setRowCount(len(sales))
        for row, sale in enumerate(sales):
            numero_item = QTableWidgetItem(sale.numero)
            numero_item.setData(Qt.ItemDataRole.UserRole, sale.id)
            numero_item.setData(Qt.ItemDataRole.UserRole + 1, sale.statut)
            self.table.setItem(row, 0, numero_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(sale.date)))
            self.table.setItem(row, 2, QTableWidgetItem(sale.client_nom or "—"))
            self.table.setItem(row, 3, QTableWidgetItem(sale.username))
            self.table.setItem(row, 4, QTableWidgetItem(format_money(sale.total, self._currency_code)))
            self.table.setItem(row, 5, QTableWidgetItem(_STATUT_LABELS.get(sale.statut, str(sale.statut))))

        self._update_action_buttons()

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    def _selected_sale_id(self) -> Optional[int]:
        row = self._selected_row()
        if row is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _selected_statut(self) -> Optional[StatutOperation]:
        row = self._selected_row()
        if row is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)

    def _update_action_buttons(self) -> None:
        statut = self._selected_statut()
        is_brouillon = statut == StatutOperation.BROUILLON
        is_validee = statut == StatutOperation.VALIDEE

        self.edit_button.setEnabled(
            statut is not None and is_brouillon and self._permissions.has_permission("SALE_UPDATE")
        )
        self.delete_button.setEnabled(
            statut is not None and is_brouillon and self._permissions.has_permission("SALE_UPDATE")
        )
        self.validate_button.setEnabled(
            statut is not None and is_brouillon and self._permissions.has_permission("SALE_VALIDATE")
        )
        self.cancel_button.setEnabled(
            statut is not None and is_validee and self._permissions.has_permission("SALE_CANCEL")
        )

    # -- chargement des listes pour les formulaires -------------------------

    def _load_articles_for_form(self) -> list[tuple[int, str, str]]:
        try:
            articles = self._article_service.list_articles(include_inactive=False)
        except AppError:
            articles = []
        return [(a.id, f"{a.reference} — {a.designation}", str(a.prix_vente)) for a in articles]

    def _load_clients_for_form(self) -> list[tuple[int, str]]:
        """Seuls les clients actifs sont proposés pour une nouvelle
        sélection (§8) — un client désactivé reste visible dans l'historique
        mais ne doit plus être choisi pour une nouvelle vente."""
        try:
            clients = self._client_service.list_clients(include_inactive=False)
        except AppError:
            clients = []
        return [(c.id, c.nom) for c in clients]

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        articles = self._load_articles_for_form()
        clients = self._load_clients_for_form()
        initial = {"date": date.today()}
        self._open_form(sale_id=None, articles=articles, clients=clients, initial=initial)

    def _on_edit_clicked(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            return
        initial = self._load_edit_initial(sale_id)
        if initial is None:
            return
        articles = self._load_articles_for_form()
        clients = self._load_clients_for_form()
        self._open_form(sale_id=sale_id, articles=articles, clients=clients, initial=initial)

    def _load_edit_initial(self, sale_id: int) -> Optional[dict]:
        """Récupère les valeurs actuelles d'une vente pour pré-remplir le
        formulaire de modification. Isolé de ``_on_edit_clicked`` pour rester
        testable sans dialogue modal."""
        try:
            sale = self._sale_service.get_sale(sale_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        return {
            "date": sale.date,
            "client_id": sale.client_id,
            "lignes": [
                {
                    "article_id": ligne.article_id,
                    "article_label": f"{ligne.article_reference} — {ligne.article_designation}",
                    "quantite": ligne.quantite,
                    "prix_unitaire": ligne.prix_unitaire,
                }
                for ligne in sale.lignes
            ],
        }

    def _open_form(
        self,
        sale_id: Optional[int],
        articles: list[tuple[int, str, str]],
        clients: list[tuple[int, str]],
        initial: dict,
    ) -> None:
        state = {"values": initial}

        def factory() -> SaleFormDialog:
            return SaleFormDialog(
                articles, clients, state["values"], on_create_client=self._create_client_from_sale_form, parent=self
            )

        def submit(dialog: SaleFormDialog) -> bool:
            state["values"] = dialog.values()
            return self._submit_form(sale_id, state["values"])

        run_modal_form(factory, submit)
        self._reload_client_filter_combo()
        self.refresh()

    def _create_client_from_sale_form(self) -> Optional[tuple[int, str]]:
        """Callback transmis à ``SaleFormDialog`` pour la création de client
        « à la volée » (§5 du lot Clients) : ouvre ``ClientFormDialog``
        par-dessus le formulaire de vente déjà ouvert, sans jamais le fermer
        ni réinitialiser son état — la date et les lignes déjà saisies
        restent intactes pendant toute l'opération. La création est
        immédiate et définitive (comme toute création de client), même si
        la vente en cours de saisie est ensuite annulée sans être
        enregistrée."""
        dialog = ClientFormDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return self._create_client_from_values(dialog.values())

    def _create_client_from_values(self, values: dict) -> Optional[tuple[int, str]]:
        """Isolé de ``_create_client_from_sale_form`` pour rester testable
        sans dialogue modal."""
        try:
            created = self._client_service.create_client(
                values["nom"],
                telephone=values.get("telephone"),
                email=values.get("email"),
                adresse=values.get("adresse"),
                observations=values.get("observations"),
            )
        except AppError as exc:
            QMessageBox.warning(self, "Création refusée", str(exc))
            return None
        QMessageBox.information(self, "Client créé", f"Le client « {created.nom} » a été créé.")
        return created.id, created.nom

    def _submit_form(self, sale_id: Optional[int], values: dict) -> bool:
        """Convertit la saisie, appelle le service et affiche le résultat.
        Isolé de ``_open_form`` pour rester testable sans dialogue modal."""
        try:
            sale_date = values["date"]
            client_id = values.get("client_id")
            lines = [
                VenteLigneInput(
                    article_id=line["article_id"],
                    quantite=line["quantite"],
                    prix_unitaire=line["prix_unitaire"],
                )
                for line in values["lignes"]
            ]

            if sale_id is None:
                created = self._sale_service.create_sale(sale_date, lines, client_id=client_id)
                QMessageBox.information(
                    self, "Vente créée", f"La vente « {created.numero} » a été créée en brouillon."
                )
            else:
                updated = self._sale_service.update_sale(sale_id, sale_date, lines, client_id=client_id)
                QMessageBox.information(
                    self, "Vente modifiée", f"La vente « {updated.numero} » a été modifiée."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- suppression d'un brouillon ------------------------------------------

    def _on_delete_clicked(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            return
        if not confirm_action(
            self, "Confirmation", "Voulez-vous vraiment supprimer cette vente en brouillon ? "
            "Cette action est irréversible."
        ):
            return
        if self._delete_selected(sale_id):
            self.refresh()

    def _delete_selected(self, sale_id: int) -> bool:
        """Isolé de ``_on_delete_clicked`` pour rester testable sans boîte modale."""
        try:
            self._sale_service.delete_sale(sale_id)
            QMessageBox.information(self, "Vente supprimée", "La vente en brouillon a été supprimée.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- consultation détaillée ----------------------------------------------

    def _on_detail_clicked(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            return
        result = self._load_sale_for_detail(sale_id)
        if result is None:
            return
        sale, movements = result
        dialog = SaleDetailDialog(
            sale, movements, self._currency_code, self._receipt_service, self._permissions, parent=self
        )
        dialog.exec()

    def _load_sale_for_detail(self, sale_id: int):
        """Isolé de ``_on_detail_clicked`` pour rester testable sans dialogue modal."""
        try:
            sale = self._sale_service.get_sale(sale_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        movements = []
        if self._permissions.has_permission("STOCK_MOVEMENT_VIEW"):
            try:
                movements = self._sale_service.get_sale_movements(sale_id)
            except AppError:
                movements = []
        return sale, movements

    # -- validation / annulation ---------------------------------------------

    def _on_validate_clicked(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            return
        if not confirm_action(
            self, "Confirmation", "Voulez-vous vraiment valider cette vente ? "
            "Cette action met à jour le stock et n'est pas réversible autrement que par annulation."
        ):
            return
        if self._validate_selected(sale_id):
            self.refresh()

    def _validate_selected(self, sale_id: int) -> bool:
        """Isolé de ``_on_validate_clicked`` pour rester testable sans boîte modale."""
        try:
            validated = self._sale_service.validate_sale(sale_id)
            QMessageBox.information(
                self, "Vente validée", f"La vente « {validated.numero} » a été validée."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    def _on_cancel_clicked(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            return
        if not confirm_action(
            self, "Confirmation", "Voulez-vous vraiment annuler cette vente validée ?"
        ):
            return
        if self._cancel_selected(sale_id):
            self.refresh()

    def _cancel_selected(self, sale_id: int) -> bool:
        """Isolé de ``_on_cancel_clicked`` pour rester testable sans boîte modale."""
        try:
            cancelled = self._sale_service.cancel_sale(sale_id)
            QMessageBox.information(
                self, "Vente annulée", f"La vente « {cancelled.numero} » a été annulée."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True
