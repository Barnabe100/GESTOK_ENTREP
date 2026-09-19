"""Page de gestion des clients.

Mêmes conventions visuelles et le même comportement que ``SuppliersPage``
(tableau, recherche, boutons Ajouter/Modifier/Activer-désactiver,
confirmation avant opération sensible). Ajoute un bouton Détails ouvrant
``ClientDetailDialog`` (informations + historique des ventes du client —
lecture seule, réutilise ``SaleService.list_sales(client_id=...)`` sans
introduire de dépendance de ``ClientService`` vers la logique de vente).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.clients.client_service import ClientService
from app.services.sales.sale_service import SaleService
from app.services.settings.company_settings_service import get_effective_currency
from app.utils.exceptions import AppError
from app.views.client_detail_dialog import ClientDetailDialog
from app.views.client_form_dialog import ClientFormDialog
from app.views.common import confirm_action, run_modal_form

_COLUMNS = ["Nom", "Téléphone", "Email", "Statut", "Créé le", "Modifié le"]


class ClientsPage(QWidget):
    def __init__(
        self,
        client_service: ClientService,
        sale_service: SaleService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client_service = client_service
        self._sale_service = sale_service
        self._permissions = permission_service
        self._currency_code = get_effective_currency()

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher un client…")
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)

        self.add_button = QPushButton("Ajouter", self)
        self.add_button.setEnabled(self._permissions.has_permission("CLIENT_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        self.edit_button.setEnabled(self._permissions.has_permission("CLIENT_UPDATE"))
        toolbar.addWidget(self.edit_button)

        self.toggle_button = QPushButton("Activer / désactiver", self)
        self.toggle_button.setEnabled(
            self._permissions.has_permission("CLIENT_ACTIVATE")
            or self._permissions.has_permission("CLIENT_DEACTIVATE")
        )
        toolbar.addWidget(self.toggle_button)

        self.detail_button = QPushButton("Détails", self)
        toolbar.addWidget(self.detail_button)

        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.search_edit.textChanged.connect(self.refresh)
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.toggle_button.clicked.connect(self._on_toggle_clicked)
        self.detail_button.clicked.connect(self._on_detail_clicked)

        self.refresh()

    # -- affichage ---------------------------------------------------------

    def refresh(self) -> None:
        try:
            clients = self._client_service.list_clients(search=self.search_edit.text())
        except AppError:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(clients))
        for row, client in enumerate(clients):
            name_item = QTableWidgetItem(client.nom)
            name_item.setData(Qt.ItemDataRole.UserRole, client.id)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(client.telephone or ""))
            self.table.setItem(row, 2, QTableWidgetItem(client.email or ""))
            self.table.setItem(row, 3, QTableWidgetItem("Actif" if client.actif else "Inactif"))
            self.table.setItem(row, 4, QTableWidgetItem(client.date_creation.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 5, QTableWidgetItem(client.date_modification.strftime("%Y-%m-%d %H:%M")))

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    def _selected_client_id(self) -> Optional[int]:
        row = self._selected_row()
        if row is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        self._open_form(client_id=None, initial={})

    def _on_edit_clicked(self) -> None:
        client_id = self._selected_client_id()
        if client_id is None:
            return
        initial = self._load_edit_initial(client_id)
        if initial is None:
            return
        self._open_form(client_id=client_id, initial=initial)

    def _load_edit_initial(self, client_id: int) -> Optional[dict]:
        """Récupère les valeurs actuelles d'un client pour pré-remplir le
        formulaire de modification. Isolé de ``_on_edit_clicked`` pour rester
        testable sans dialogue modal."""
        try:
            full = self._client_service.get_client(client_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        return {
            "nom": full.nom,
            "telephone": full.telephone or "",
            "email": full.email or "",
            "adresse": full.adresse or "",
            "observations": full.observations or "",
        }

    def _open_form(self, client_id: Optional[int], initial: dict) -> None:
        state = {"values": initial}

        def factory() -> ClientFormDialog:
            return ClientFormDialog(state["values"], parent=self)

        def submit(dialog: ClientFormDialog) -> bool:
            state["values"] = dialog.values()
            return self._submit_form(client_id, state["values"])

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_form(self, client_id: Optional[int], values: dict) -> bool:
        """Effectue l'appel service et affiche le résultat. Isolé de
        ``_open_form`` pour rester testable sans dialogue modal."""
        nom = values["nom"]
        kwargs = {
            "telephone": values.get("telephone"),
            "email": values.get("email"),
            "adresse": values.get("adresse"),
            "observations": values.get("observations"),
        }
        try:
            if client_id is None:
                self._client_service.create_client(nom, **kwargs)
                QMessageBox.information(self, "Client créé", f"Le client « {nom} » a été créé.")
            else:
                self._client_service.update_client(client_id, nom, **kwargs)
                QMessageBox.information(self, "Client modifié", f"Le client « {nom} » a été modifié.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- activation / désactivation -----------------------------------------

    def _on_toggle_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            return

        client_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        name = self.table.item(row, 0).text()
        currently_active = self.table.item(row, 3).text() == "Actif"
        action_label = "désactiver" if currently_active else "activer"

        if not confirm_action(
            self, "Confirmation", f"Voulez-vous vraiment {action_label} le client « {name} » ?"
        ):
            return

        if self._toggle_status(client_id, currently_active):
            self.refresh()

    def _toggle_status(self, client_id: int, currently_active: bool) -> bool:
        """Effectue le changement de statut. Isolé de ``_on_toggle_clicked``
        pour rester testable sans boîte de confirmation modale."""
        try:
            if currently_active:
                updated = self._client_service.deactivate_client(client_id)
                QMessageBox.information(self, "Client désactivé", f"Le client « {updated.nom} » a été désactivé.")
            else:
                updated = self._client_service.activate_client(client_id)
                QMessageBox.information(self, "Client activé", f"Le client « {updated.nom} » a été activé.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- détail / historique -------------------------------------------------

    def _on_detail_clicked(self) -> None:
        client_id = self._selected_client_id()
        if client_id is None:
            return
        result = self._load_client_for_detail(client_id)
        if result is None:
            return
        client, sales = result
        dialog = ClientDetailDialog(client, sales, self._currency_code, parent=self)
        dialog.exec()

    def _load_client_for_detail(self, client_id: int):
        """Isolé de ``_on_detail_clicked`` pour rester testable sans
        dialogue modal. L'historique des ventes n'est chargé que si
        l'utilisateur courant dispose de SALE_VIEW (ex. Gestionnaire de
        stock : a CLIENT_VIEW mais pas SALE_VIEW) — reste vide sinon plutôt
        que de refuser toute la consultation du client."""
        try:
            client = self._client_service.get_client(client_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        sales = []
        if self._permissions.has_permission("SALE_VIEW"):
            try:
                sales = self._sale_service.list_sales(client_id=client_id)
            except AppError:
                sales = []
        return client, sales
