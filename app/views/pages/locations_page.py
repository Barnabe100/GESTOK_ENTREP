"""Page de gestion des locations.

Toute action (création, modification, suppression de brouillon) passe par
:class:`LocationService`, qui revérifie la permission côté service. Le
cycle de vie complet (confirmation, départ, retour, annulation, caution,
paiement) est concentré dans ``LocationDetailDialog`` plutôt que sur cette
page-liste — contrairement à ``SalesPage`` (valider/annuler en toolbar),
une location a trop d'étapes et de contexte par ligne (retours partiels)
pour rester lisible en boutons de liste ; seules création/modification/
suppression de brouillon et consultation restent ici.

Seuls les articles en mode Location (voir ``Article.mode_gestion``) sont
proposés dans le formulaire — jamais un article géré en mode Vente, qui
serait rejeté par ``LocationService`` de toute façon."""
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

from app.models.enums import ModeGestionArticle, StatutLocation
from app.services.articles.article_service import ArticleService
from app.services.auth.permission_service import PermissionService
from app.services.clients.client_service import ClientService
from app.services.rentals.location_service import LocationLigneInput, LocationService
from app.services.settings.company_settings_service import get_effective_currency
from app.utils.exceptions import AppError
from app.utils.money import format_money
from app.views.client_form_dialog import ClientFormDialog
from app.views.common import confirm_action, run_modal_form
from app.views.location_detail_dialog import LocationDetailDialog
from app.views.location_form_dialog import LocationFormDialog

_COLUMNS = ["Numéro", "Date", "Client", "Créée par", "Total facturé", "Statut"]

_STATUT_LABELS = {
    StatutLocation.BROUILLON: "Brouillon",
    StatutLocation.CONFIRMEE: "Confirmée",
    StatutLocation.EN_COURS: "En cours",
    StatutLocation.RETOURNEE: "Retournée",
    StatutLocation.ANNULEE: "Annulée",
}

_STATUS_FILTERS = [
    ("Toutes", None),
    ("Brouillon", StatutLocation.BROUILLON),
    ("Confirmée", StatutLocation.CONFIRMEE),
    ("En cours", StatutLocation.EN_COURS),
    ("Retournée", StatutLocation.RETOURNEE),
    ("Annulée", StatutLocation.ANNULEE),
]

_ALL_CLIENTS_LABEL = "(Tous les clients)"


class LocationsPage(QWidget):
    def __init__(
        self,
        location_service: LocationService,
        article_service: ArticleService,
        client_service: ClientService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._location_service = location_service
        self._article_service = article_service
        self._client_service = client_service
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

        self.add_button = QPushButton("Nouvelle location", self)
        self.add_button.setEnabled(self._permissions.has_permission("LOCATION_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        self.edit_button.setEnabled(self._permissions.has_permission("LOCATION_UPDATE"))
        toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Supprimer", self)
        self.delete_button.setEnabled(self._permissions.has_permission("LOCATION_UPDATE"))
        toolbar.addWidget(self.delete_button)

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
        self.status_filter_combo.currentIndexChanged.connect(self.refresh)
        self.client_filter_combo.currentIndexChanged.connect(self.refresh)
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        self.detail_button.clicked.connect(self._on_detail_clicked)
        self.table.itemSelectionChanged.connect(self._update_action_buttons)

        self.refresh()

    # -- affichage ---------------------------------------------------------

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
        statut = self.status_filter_combo.currentData()
        client_id = self.client_filter_combo.currentData()
        try:
            locations = self._location_service.list_locations(
                search=self.search_edit.text(), statut=statut, client_id=client_id
            )
        except AppError:
            self.table.setRowCount(0)
            self._update_action_buttons()
            return

        self.table.setRowCount(len(locations))
        for row, location in enumerate(locations):
            numero_item = QTableWidgetItem(location.numero)
            numero_item.setData(Qt.ItemDataRole.UserRole, location.id)
            numero_item.setData(Qt.ItemDataRole.UserRole + 1, location.statut)
            self.table.setItem(row, 0, numero_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(location.date)))
            self.table.setItem(row, 2, QTableWidgetItem(location.client_nom or "Client non renseigné"))
            self.table.setItem(row, 3, QTableWidgetItem(location.username))
            self.table.setItem(
                row, 4, QTableWidgetItem(format_money(location.montant_total_facture, self._currency_code))
            )
            self.table.setItem(row, 5, QTableWidgetItem(_STATUT_LABELS.get(location.statut, str(location.statut))))

        self._update_action_buttons()

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    def _selected_location_id(self) -> Optional[int]:
        row = self._selected_row()
        if row is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _selected_statut(self) -> Optional[StatutLocation]:
        row = self._selected_row()
        if row is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)

    def _update_action_buttons(self) -> None:
        statut = self._selected_statut()
        is_brouillon = statut == StatutLocation.BROUILLON
        has_selection = statut is not None

        self.edit_button.setEnabled(
            has_selection and is_brouillon and self._permissions.has_permission("LOCATION_UPDATE")
        )
        self.delete_button.setEnabled(
            has_selection and is_brouillon and self._permissions.has_permission("LOCATION_UPDATE")
        )

    # -- chargement des listes pour les formulaires -------------------------

    def _load_articles_for_form(self, include_article_id: Optional[int] = None) -> list[tuple[int, str, str]]:
        """Seuls les articles en mode Location sont proposés (§ intégration
        avec les articles) — ``LocationService`` les refuserait de toute
        façon, mais le formulaire ne doit même pas les présenter."""
        try:
            articles = self._article_service.list_articles(include_inactive=False)
        except AppError:
            articles = []
        result = [
            (a.id, f"{a.reference} — {a.designation}", str(a.tarif_location_jour or "0"))
            for a in articles
            if a.mode_gestion == ModeGestionArticle.LOCATION
        ]
        known_ids = {a[0] for a in result}
        if include_article_id is not None and include_article_id not in known_ids:
            try:
                current = self._article_service.get_article(include_article_id)
                result.append(
                    (current.id, f"{current.reference} — {current.designation} (hors catalogue Location)",
                     str(current.tarif_location_jour or "0"))
                )
            except AppError:
                pass
        return result

    def _load_clients_for_form(self) -> list[tuple[int, str]]:
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
        self._open_form(location_id=None, articles=articles, clients=clients, initial=initial)

    def _on_edit_clicked(self) -> None:
        location_id = self._selected_location_id()
        if location_id is None:
            return
        initial = self._load_edit_initial(location_id)
        if initial is None:
            return
        articles = self._load_articles_for_form()
        clients = self._load_clients_for_form()
        self._open_form(location_id=location_id, articles=articles, clients=clients, initial=initial)

    def _load_edit_initial(self, location_id: int) -> Optional[dict]:
        """Isolé de ``_on_edit_clicked`` pour rester testable sans dialogue modal."""
        try:
            location = self._location_service.get_location(location_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        return {
            "date": location.date,
            "client_id": location.client_id,
            "commentaire": location.commentaire,
            "lignes": [
                {
                    "article_id": ligne.article_id,
                    "article_label": f"{ligne.article_reference} — {ligne.article_designation}",
                    "quantite": ligne.qte_prevue,
                    "tarif_jour": ligne.tarif_jour,
                }
                for ligne in location.lignes
            ],
        }

    def _open_form(
        self,
        location_id: Optional[int],
        articles: list[tuple[int, str, str]],
        clients: list[tuple[int, str]],
        initial: dict,
    ) -> None:
        state = {"values": initial}

        def factory() -> LocationFormDialog:
            return LocationFormDialog(
                articles, clients, state["values"],
                on_create_client=self._create_client_from_location_form,
                parent=self,
            )

        def submit(dialog: LocationFormDialog) -> bool:
            state["values"] = dialog.values()
            return self._submit_form(location_id, state["values"], dialog.requested_action())

        run_modal_form(factory, submit)
        self._reload_client_filter_combo()
        self.refresh()

    def _create_client_from_location_form(self) -> Optional[tuple[int, str]]:
        """Callback transmis à ``LocationFormDialog`` pour la création de
        client « à la volée » : ouvre ``ClientFormDialog`` par-dessus le
        formulaire de location déjà ouvert, sans jamais le fermer ni
        réinitialiser son état — la date et les lignes déjà saisies restent
        intactes pendant toute l'opération. Patron identique à
        ``SalesPage._create_client_from_sale_form``."""
        dialog = ClientFormDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return self._create_client_from_values(dialog.values())

    def _create_client_from_values(self, values: dict) -> Optional[tuple[int, str]]:
        """Isolé de ``_create_client_from_location_form`` pour rester
        testable sans dialogue modal."""
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

    def _submit_form(self, location_id: Optional[int], values: dict, action: str = "draft") -> bool:
        """Convertit la saisie, appelle le service et affiche le résultat.
        Isolé de ``_open_form`` pour rester testable sans dialogue modal.

        ``action`` ('draft' ou 'validate', voir ``LocationFormDialog.requested_action``) :
        si 'validate', seul ``LocationService.confirm_location`` est appelé
        dans la foulée (BROUILLON -> CONFIRMEE, sans effet stock) — jamais
        ``depart_location``, qui exige une date de départ absente de ce
        formulaire et reste une étape distincte, pilotée depuis
        ``LocationDetailDialog``. Si la création/modification réussit mais
        que la confirmation échoue, la location reste en brouillon,
        retrouvable dans la liste — le dialogue n'est jamais rouvert dans ce
        cas, pour ne jamais recréer la location en double."""
        try:
            location_date = values["date"]
            client_id = values["client_id"]
            lines = [
                LocationLigneInput(
                    article_id=line["article_id"], quantite=line["quantite"], tarif_jour=line["tarif_jour"],
                )
                for line in values["lignes"]
            ]
            commentaire = values.get("commentaire")

            if location_id is None:
                document = self._location_service.create_location(
                    location_date, client_id, lines, commentaire=commentaire
                )
                created_now = True
            else:
                document = self._location_service.update_location(
                    location_id, location_date, client_id, lines, commentaire=commentaire
                )
                created_now = False
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False

        if action != "validate":
            if created_now:
                QMessageBox.information(
                    self, "Location créée", f"La location « {document.numero} » a été créée en brouillon."
                )
            else:
                QMessageBox.information(
                    self, "Location modifiée", f"La location « {document.numero} » a été modifiée."
                )
            return True

        try:
            confirmed = self._location_service.confirm_location(document.id)
        except AppError as exc:
            QMessageBox.warning(
                self, "Location enregistrée, validation refusée",
                f"La location « {document.numero} » a été enregistrée en brouillon, mais n'a pas pu être "
                f"confirmée : {exc}\n\nVous pouvez la retrouver dans la liste pour la corriger ou la confirmer.",
            )
            return True

        QMessageBox.information(
            self, "Location validée", f"La location « {confirmed.numero} » a été confirmée."
        )
        return True

    # -- suppression d'un brouillon ------------------------------------------

    def _on_delete_clicked(self) -> None:
        location_id = self._selected_location_id()
        if location_id is None:
            return
        if not confirm_action(
            self, "Confirmation", "Voulez-vous vraiment supprimer cette location en brouillon ? "
            "Cette action est irréversible."
        ):
            return
        if self._delete_selected(location_id):
            self.refresh()

    def _delete_selected(self, location_id: int) -> bool:
        """Isolé de ``_on_delete_clicked`` pour rester testable sans boîte modale."""
        try:
            self._location_service.delete_location(location_id)
            QMessageBox.information(self, "Location supprimée", "La location en brouillon a été supprimée.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- consultation détaillée ----------------------------------------------

    def _on_detail_clicked(self) -> None:
        location_id = self._selected_location_id()
        if location_id is None:
            return
        location = self._load_location_for_detail(location_id)
        if location is None:
            return
        dialog = LocationDetailDialog(
            location, self._currency_code, self._location_service, self._permissions, parent=self
        )
        dialog.exec()
        self.refresh()

    def _load_location_for_detail(self, location_id: int):
        """Isolé de ``_on_detail_clicked`` pour rester testable sans dialogue modal."""
        try:
            return self._location_service.get_location(location_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
