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
serait rejeté par ``LocationService`` de toute façon.

Phase amélioration UX (point 2) : cette page est, comme ``SalesPage``, un
conteneur à deux sous-vues internes (``self._view_stack``, un
``QStackedWidget``) — la liste des locations (index 0, inchangée) et un
écran de saisie plein format (index 1, voir ``_build_caisse_view``) qui
remplace ``LocationFormDialog`` comme point d'entrée de création/
modification depuis cette page. ``LocationFormDialog``/``LocationLineFormDialog``
ne sont ni supprimés ni modifiés : ils restent disponibles et testés
indépendamment, simplement plus appelés d'ici — même principe que
``SalesPage``/``SaleFormDialog``.

Différence volontaire avec ``SalesPage`` : le montant réellement facturé
d'une location n'est connu qu'au retour (``LocationRetour.montant_facture``,
calculé sur la durée réelle écoulée — voir ``LocationService``) ; cette
page n'affiche donc jamais de « total » à la création ou à la
modification, seulement une estimation par ligne (tarif journalier ×
quantité), explicitement libellée comme telle. Aucune règle métier de
tarification, de caution, de départ ou de retour n'est ajoutée ici : ces
étapes restent exclusivement pilotées depuis ``LocationDetailDialog``."""
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
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import ModeGestionArticle, StatutLocation
from app.services.articles.article_service import ArticleService
from app.services.auth.permission_service import PermissionService
from app.services.clients.client_service import ClientService
from app.services.documents.receipt_service import ReceiptService
from app.services.rentals.location_service import LocationLigneInput, LocationService
from app.services.settings.company_settings_service import get_effective_currency
from app.utils.exceptions import AppError, ValidationError
from app.utils.money import format_money
from app.utils.quantity import format_quantity
from app.views.client_form_dialog import ClientFormDialog
from app.views.common import confirm_action, date_to_qdate, format_decimal_for_input, parse_decimal, required_label
from app.views.location_detail_dialog import LocationDetailDialog

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
_NO_CLIENT_LABEL = "(Aucun client)"

_CAISSE_LINE_COLUMNS = ["Article", "Quantité", "Tarif / jour", "Estimation (tarif × quantité)"]
_CAISSE_QUANTITY_COLUMN = 1
_CAISSE_TARIF_COLUMN = 2


class LocationsPage(QWidget):
    def __init__(
        self,
        location_service: LocationService,
        article_service: ArticleService,
        client_service: ClientService,
        permission_service: PermissionService,
        receipt_service: Optional[ReceiptService] = None,
        parent: QWidget | None = None,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._location_service = location_service
        self._article_service = article_service
        self._client_service = client_service
        self._permissions = permission_service
        # Lot 22 (§F) : facultatif pour ne jamais casser un appelant déjà
        # existant qui ne fournirait pas ce service — ``LocationDetailDialog``
        # se comporte alors sans les documents de location (mêmes boutons
        # désactivés que sans permission, jamais une erreur).
        self._receipt_service = receipt_service
        self._currency_code = get_effective_currency()
        # Lot 16 : chemin de consultation explicite conservé quand le module
        # Location est désactivé (voir MainWindow) — création/modification/
        # suppression désactivées quelle que soit la permission ; seule la
        # consultation (liste, filtres, détail) reste disponible.
        self._read_only = read_only

        layout = QVBoxLayout(self)

        self._view_stack = QStackedWidget(self)
        layout.addWidget(self._view_stack)

        list_view = QWidget(self)
        list_layout = QVBoxLayout(list_view)

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
        self.add_button.setProperty("variant", "primary")
        self.add_button.setEnabled(not self._read_only and self._permissions.has_permission("LOCATION_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        self.edit_button.setProperty("variant", "indigo")
        self.edit_button.setEnabled(not self._read_only and self._permissions.has_permission("LOCATION_UPDATE"))
        toolbar.addWidget(self.edit_button)

        self.delete_button = QPushButton("Supprimer", self)
        self.delete_button.setProperty("variant", "danger")
        self.delete_button.setEnabled(not self._read_only and self._permissions.has_permission("LOCATION_UPDATE"))
        toolbar.addWidget(self.delete_button)

        self.detail_button = QPushButton("Détails", self)
        toolbar.addWidget(self.detail_button)

        list_layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        list_layout.addWidget(self.table)

        self.search_edit.textChanged.connect(self.refresh)
        self.status_filter_combo.currentIndexChanged.connect(self.refresh)
        self.client_filter_combo.currentIndexChanged.connect(self.refresh)
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        self.detail_button.clicked.connect(self._on_detail_clicked)
        self.table.itemSelectionChanged.connect(self._update_action_buttons)

        # État de la saisie en cours dans la caisse (voir ``_open_caisse``/
        # ``_close_caisse``) — ``None`` hors caisse, utilisé par
        # ``_caisse_has_unsaved_changes``/``confirm_can_leave``. Initialisé
        # avant ``_build_caisse_view`` : ``_build_caisse_right_panel``
        # appelle ``_update_caisse_recap`` dès sa construction.
        self._caisse_location_id: Optional[int] = None
        self._caisse_lines: list[dict] = []
        self._caisse_articles_cache: list[tuple[int, str, str]] = []
        self._caisse_clients: list[tuple[int, str]] = []
        self._caisse_initial_snapshot: Optional[tuple] = None

        self._view_stack.addWidget(list_view)
        self._view_stack.addWidget(self._build_caisse_view())

        self.refresh()

    # -- écran de saisie plein format (remplace l'ancien formulaire modal) --

    def _build_caisse_view(self) -> QWidget:
        container = QWidget(self)
        outer_layout = QVBoxLayout(container)

        splitter = QSplitter(Qt.Orientation.Horizontal, container)
        outer_layout.addWidget(splitter)

        splitter.addWidget(self._build_caisse_left_panel(splitter))
        splitter.addWidget(self._build_caisse_right_panel(splitter))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        return container

    def _build_caisse_left_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)

        header_form = QFormLayout()

        self.caisse_date_edit = QDateEdit(panel)
        self.caisse_date_edit.setCalendarPopup(True)
        self.caisse_date_edit.setDisplayFormat("dd/MM/yyyy")
        self.caisse_date_edit.setMaximumDate(QDate.currentDate())
        header_form.addRow(required_label("Date"), self.caisse_date_edit)

        client_row = QHBoxLayout()
        self.caisse_client_combo = QComboBox(panel)
        client_row.addWidget(self.caisse_client_combo)
        self.caisse_new_client_button = QPushButton("Nouveau client…", panel)
        client_row.addWidget(self.caisse_new_client_button)
        header_form.addRow("Client", client_row)

        self.caisse_commentaire_edit = QLineEdit(panel)
        header_form.addRow("Commentaire", self.caisse_commentaire_edit)

        layout.addLayout(header_form)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Rechercher un article", panel))
        self.caisse_search_edit = QLineEdit(panel)
        self.caisse_search_edit.setPlaceholderText("Référence ou désignation…")
        search_row.addWidget(self.caisse_search_edit)
        layout.addLayout(search_row)

        self.caisse_search_results = QListWidget(panel)
        self.caisse_search_results.setMaximumHeight(120)
        layout.addWidget(self.caisse_search_results)

        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Scanner / code-barres", panel))
        self.caisse_scan_edit = QLineEdit(panel)
        self.caisse_scan_edit.setPlaceholderText("Scanner un article ou saisir son code-barres puis Entrée…")
        scan_row.addWidget(self.caisse_scan_edit)
        layout.addLayout(scan_row)

        layout.addWidget(QLabel("Lignes", panel))

        self.caisse_lines_table = QTableWidget(0, len(_CAISSE_LINE_COLUMNS), panel)
        self.caisse_lines_table.setAlternatingRowColors(True)
        self.caisse_lines_table.setHorizontalHeaderLabels(_CAISSE_LINE_COLUMNS)
        self.caisse_lines_table.horizontalHeader().setStretchLastSection(True)
        self.caisse_lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.caisse_lines_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.caisse_lines_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed
        )
        layout.addWidget(self.caisse_lines_table)

        remove_row = QHBoxLayout()
        self.caisse_remove_line_button = QPushButton("Supprimer la ligne", panel)
        self.caisse_remove_line_button.setProperty("variant", "danger")
        remove_row.addWidget(self.caisse_remove_line_button)
        remove_row.addStretch(1)
        layout.addLayout(remove_row)

        self.caisse_error_label = QLabel("", panel)
        self.caisse_error_label.setStyleSheet("color: #DC2626;")
        self.caisse_error_label.setWordWrap(True)
        layout.addWidget(self.caisse_error_label)

        self.caisse_new_client_button.clicked.connect(self._on_caisse_new_client_clicked)
        self.caisse_search_edit.textChanged.connect(self._on_caisse_search_text_changed)
        self.caisse_search_results.itemDoubleClicked.connect(self._on_caisse_search_result_activated)
        self.caisse_scan_edit.returnPressed.connect(self._on_caisse_scan_entered)
        self.caisse_lines_table.itemChanged.connect(self._on_caisse_line_item_changed)
        self.caisse_remove_line_button.clicked.connect(self._on_caisse_remove_line_clicked)

        return panel

    def _build_caisse_right_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)

        recap_form = QFormLayout()
        self.caisse_client_recap_label = QLabel("—", panel)
        recap_form.addRow("Client", self.caisse_client_recap_label)
        self.caisse_lines_count_label = QLabel("0", panel)
        recap_form.addRow("Nombre de lignes", self.caisse_lines_count_label)
        self.caisse_estimate_label = QLabel("", panel)
        self.caisse_estimate_label.setStyleSheet("font-weight: 600; font-size: 16px;")
        recap_form.addRow("Estimation (tarif × quantité)", self.caisse_estimate_label)
        layout.addLayout(recap_form)

        estimate_caveat = QLabel(
            "Cette estimation ne tient pas compte de la durée réelle de "
            "location : le montant réellement facturé n'est calculé qu'au "
            "retour de la location.",
            panel,
        )
        estimate_caveat.setWordWrap(True)
        estimate_caveat.setStyleSheet("color: #6B7280; font-style: italic;")
        layout.addWidget(estimate_caveat)

        layout.addStretch(1)

        self.caisse_save_draft_button = QPushButton("Enregistrer en brouillon", panel)
        self.caisse_save_draft_button.setProperty("variant", "primary")
        layout.addWidget(self.caisse_save_draft_button)

        self.caisse_validate_button = QPushButton("Valider", panel)
        self.caisse_validate_button.setProperty("variant", "success")
        self.caisse_validate_button.setDefault(True)
        self.caisse_validate_button.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.caisse_validate_button)

        self.caisse_back_button = QPushButton("Retour à la liste", panel)
        layout.addWidget(self.caisse_back_button)

        self.caisse_save_draft_button.clicked.connect(self._on_caisse_save_draft_clicked)
        self.caisse_validate_button.clicked.connect(self._on_caisse_validate_clicked)
        self.caisse_back_button.clicked.connect(self._on_caisse_back_clicked)

        self._update_caisse_recap()

        return panel

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
            not self._read_only
            and has_selection and is_brouillon and self._permissions.has_permission("LOCATION_UPDATE")
        )
        self.delete_button.setEnabled(
            not self._read_only
            and has_selection and is_brouillon and self._permissions.has_permission("LOCATION_UPDATE")
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
            (
                a.id, f"{a.reference} — {a.designation}",
                format_decimal_for_input(a.tarif_location_jour) if a.tarif_location_jour is not None else "0",
            )
            for a in articles
            if a.mode_gestion == ModeGestionArticle.LOCATION
        ]
        known_ids = {a[0] for a in result}
        if include_article_id is not None and include_article_id not in known_ids:
            try:
                current = self._article_service.get_article(include_article_id)
                tarif_text = (
                    format_decimal_for_input(current.tarif_location_jour)
                    if current.tarif_location_jour is not None else "0"
                )
                result.append(
                    (current.id, f"{current.reference} — {current.designation} (hors catalogue Location)",
                     tarif_text)
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
        self._open_caisse(location_id=None, initial={"date": date.today()})

    def _on_edit_clicked(self) -> None:
        location_id = self._selected_location_id()
        if location_id is None:
            return
        initial = self._load_edit_initial(location_id)
        if initial is None:
            return
        self._open_caisse(location_id=location_id, initial=initial)

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

    def _open_caisse(self, location_id: Optional[int], initial: dict) -> None:
        self._caisse_location_id = location_id
        self._caisse_lines = [dict(line) for line in initial.get("lignes", [])]
        self._caisse_articles_cache = self._load_articles_for_form()
        self._caisse_clients = self._load_clients_for_form()

        self.caisse_date_edit.setDate(date_to_qdate(initial.get("date") or date.today()))
        self._refresh_caisse_client_combo(selected_id=initial.get("client_id"))
        self.caisse_commentaire_edit.setText(initial.get("commentaire", "") or "")
        self.caisse_search_edit.clear()
        # Appel explicite (même principe que SalesPage._open_caisse) : la
        # liste des articles louables doit être visible dès l'ouverture,
        # sans attendre une saisie dans le champ de recherche.
        self._refresh_caisse_search_results()
        self.caisse_scan_edit.clear()
        self.caisse_error_label.setText("")
        self.caisse_save_draft_button.setEnabled(True)
        self.caisse_validate_button.setEnabled(True)

        self._refresh_caisse_lines_table()
        self._caisse_initial_snapshot = self._caisse_snapshot()
        self._view_stack.setCurrentIndex(1)

    def _close_caisse(self) -> None:
        self._caisse_location_id = None
        self._caisse_lines = []
        self._caisse_initial_snapshot = None
        self._view_stack.setCurrentIndex(0)
        self._reload_client_filter_combo()
        self.refresh()

    # -- client (sélection + création rapide) --------------------------------

    def _refresh_caisse_client_combo(self, selected_id: Optional[int] = None) -> None:
        self.caisse_client_combo.blockSignals(True)
        self.caisse_client_combo.clear()
        self.caisse_client_combo.addItem(_NO_CLIENT_LABEL, None)
        for client_id, nom in self._caisse_clients:
            self.caisse_client_combo.addItem(nom, client_id)
        self.caisse_client_combo.blockSignals(False)
        if selected_id is not None:
            index = self.caisse_client_combo.findData(selected_id)
            if index != -1:
                self.caisse_client_combo.setCurrentIndex(index)
        self._update_caisse_recap()

    def _on_caisse_new_client_clicked(self) -> None:
        """Création de client « à la volée » depuis la caisse : la saisie en
        cours (date, lignes) n'est jamais réinitialisée — ``ClientFormDialog``
        s'ouvre par-dessus sans toucher à ``self._caisse_lines``. Patron
        identique à ``SalesPage._on_caisse_new_client_clicked``."""
        dialog = ClientFormDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = self._create_client_from_values(dialog.values())
        if result is None:
            return
        client_id, client_nom = result
        self._caisse_clients.append((client_id, client_nom))
        self._refresh_caisse_client_combo(selected_id=client_id)

    # -- recherche d'articles -------------------------------------------------

    def _on_caisse_search_text_changed(self, _text: str) -> None:
        self._refresh_caisse_search_results()

    def _refresh_caisse_search_results(self) -> None:
        """Repeuple la liste à partir du texte courant du champ de
        recherche — même principe que ``SalesPage._refresh_caisse_search_results`` :
        texte vide -> tous les articles louables (``_caisse_articles_cache``,
        déjà filtré sur le mode Location), texte non vide -> filtrage
        insensible à la casse sur le libellé référence+désignation déjà
        concaténé."""
        self.caisse_search_results.clear()
        normalized = self.caisse_search_edit.text().strip().lower()
        candidates = self._caisse_articles_cache
        if normalized:
            candidates = [
                (article_id, label, tarif_jour)
                for article_id, label, tarif_jour in candidates
                if normalized in label.lower()
            ]
        if not candidates and normalized:
            empty_item = QListWidgetItem("Aucun article ne correspond à la recherche.", self.caisse_search_results)
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            return
        for article_id, label, tarif_jour in candidates:
            display = f"{label}  —  {format_money(Decimal(str(tarif_jour)), self._currency_code)} / jour"
            item = QListWidgetItem(display, self.caisse_search_results)
            item.setData(Qt.ItemDataRole.UserRole, (article_id, label, tarif_jour))

    def _on_caisse_search_result_activated(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        article_id, label, tarif_jour = data
        self._add_caisse_line(article_id, label, Decimal("1"), Decimal(str(tarif_jour)))
        self.caisse_search_edit.clear()

    # -- scan code-barres (lecteur USB « keyboard wedge ») -------------------

    def _on_caisse_scan_entered(self) -> None:
        """Même principe que ``SalesPage._on_caisse_scan_entered`` : article
        actif en mode Location trouvé -> ajout immédiat (quantité 1, tarif
        catalogue), sans dialogue. Introuvable ou en mode Vente -> message
        clair, aucune ligne ajoutée."""
        code = self.caisse_scan_edit.text().strip()
        self.caisse_scan_edit.clear()
        if not code:
            return
        result = self._lookup_article_by_barcode(code)
        if result is None:
            self._show_scan_rejection_message(code)
            return
        article_id, label, tarif_jour = result
        self._add_caisse_line(article_id, label, Decimal("1"), Decimal(str(tarif_jour)))

    def _lookup_article_by_barcode(self, code: str) -> Optional[tuple[int, str, str]]:
        """Ne renvoie qu'un article actif ET en mode Location — même
        principe que ``SalesPage._lookup_article_by_barcode`` (filtré sur
        VENTE)."""
        try:
            article = self._article_service.find_by_barcode(code)
        except AppError:
            return None
        if article is None or article.mode_gestion != ModeGestionArticle.LOCATION:
            return None
        tarif_text = (
            format_decimal_for_input(article.tarif_location_jour)
            if article.tarif_location_jour is not None else "0"
        )
        return article.id, f"{article.reference} — {article.designation}", tarif_text

    def _show_scan_rejection_message(self, code: str) -> None:
        try:
            article = self._article_service.find_by_barcode(code)
        except AppError:
            article = None
        if article is not None and article.mode_gestion == ModeGestionArticle.VENTE:
            QMessageBox.warning(
                self, "Article non louable",
                f"L'article « {article.reference} — {article.designation} » est configuré pour "
                "la vente : il ne peut pas être ajouté à une location.",
            )
            return
        QMessageBox.warning(
            self, "Article introuvable",
            f"Aucun article actif ne correspond au code-barres « {code} ».",
        )

    # -- gestion centralisée des lignes --------------------------------------

    def _add_caisse_line(self, article_id: int, article_label: str, quantite: Decimal, tarif_jour: Decimal) -> None:
        """Point d'entrée unique pour ajouter une ligne à la location en
        cours de saisie, quelle que soit son origine (recherche ou scan) —
        n'appelle jamais de service métier : une ligne de brouillon n'a
        d'existence qu'en mémoire jusqu'à l'enregistrement."""
        self.caisse_error_label.setText("")
        self._caisse_lines.append(
            {"article_id": article_id, "article_label": article_label, "quantite": quantite, "tarif_jour": tarif_jour}
        )
        self._refresh_caisse_lines_table()

    def _on_caisse_remove_line_clicked(self) -> None:
        selected = self.caisse_lines_table.selectionModel().selectedRows()
        if not selected:
            return
        row = selected[0].row()
        del self._caisse_lines[row]
        self._refresh_caisse_lines_table()

    def _on_caisse_line_item_changed(self, item: QTableWidgetItem) -> None:
        """Quantité ET tarif journalier sont tous deux éditables en place
        (contrairement à ``SalesPage``, où seul le prix de vente n'est pas
        modifiable après ajout) : le tarif catalogue n'est qu'un préremplissage,
        c'est le tarif réellement appliqué qui doit être conservé — même
        règle que l'ancien ``LocationLineFormDialog``, jamais recalculé
        automatiquement si le tarif catalogue change ensuite."""
        row = item.row()
        if row >= len(self._caisse_lines):
            return
        column = item.column()
        if column == _CAISSE_QUANTITY_COLUMN:
            field, label = "quantite", "quantité"
        elif column == _CAISSE_TARIF_COLUMN:
            field, label = "tarif_jour", "tarif journalier"
        else:
            return
        try:
            value = parse_decimal(item.text(), label)
            if field == "quantite" and value <= 0:
                raise ValidationError("La quantité doit être strictement positive.")
            if field == "tarif_jour" and value < 0:
                raise ValidationError("Le tarif journalier ne peut pas être négatif.")
        except ValidationError as exc:
            self.caisse_error_label.setText(str(exc))
            self._refresh_caisse_lines_table()
            return
        self.caisse_error_label.setText("")
        self._caisse_lines[row][field] = value
        self._refresh_caisse_lines_table()

    def _refresh_caisse_lines_table(self) -> None:
        self.caisse_lines_table.blockSignals(True)
        self.caisse_lines_table.setRowCount(len(self._caisse_lines))
        for row, line in enumerate(self._caisse_lines):
            article_item = QTableWidgetItem(line["article_label"])
            article_item.setFlags(article_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.caisse_lines_table.setItem(row, 0, article_item)

            quantite_item = QTableWidgetItem(format_quantity(line["quantite"]))
            quantite_item.setFlags(quantite_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.caisse_lines_table.setItem(row, _CAISSE_QUANTITY_COLUMN, quantite_item)

            tarif_item = QTableWidgetItem(format_decimal_for_input(line["tarif_jour"]))
            tarif_item.setFlags(tarif_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.caisse_lines_table.setItem(row, _CAISSE_TARIF_COLUMN, tarif_item)

            estimation = line["quantite"] * line["tarif_jour"]
            estimation_item = QTableWidgetItem(format_money(estimation, self._currency_code))
            estimation_item.setFlags(estimation_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.caisse_lines_table.setItem(row, 3, estimation_item)
        self.caisse_lines_table.blockSignals(False)
        self._update_caisse_recap()

    def _caisse_estimate_total(self) -> Decimal:
        """Somme des estimations par ligne (tarif journalier × quantité) —
        jamais le montant réellement facturé, qui n'existe qu'au retour
        (voir le docstring de module) : cette valeur n'est montrée qu'avec
        la mention explicite « Estimation », jamais sous le libellé
        « Total » utilisé par ``SalesPage``."""
        total = Decimal("0")
        for line in self._caisse_lines:
            total += line["quantite"] * line["tarif_jour"]
        return total

    def _update_caisse_recap(self) -> None:
        total = self._caisse_estimate_total()
        self.caisse_estimate_label.setText(format_money(total, self._currency_code))
        self.caisse_lines_count_label.setText(str(len(self._caisse_lines)))
        client_id = self.caisse_client_combo.currentData() if hasattr(self, "caisse_client_combo") else None
        if client_id is None:
            self.caisse_client_recap_label.setText(_NO_CLIENT_LABEL)
        else:
            self.caisse_client_recap_label.setText(self.caisse_client_combo.currentText())

    # -- enregistrement / validation ------------------------------------------

    def _caisse_values(self) -> dict:
        return {
            "date": self.caisse_date_edit.date().toPython(),
            "client_id": self.caisse_client_combo.currentData(),
            "commentaire": self.caisse_commentaire_edit.text(),
            "lignes": list(self._caisse_lines),
        }

    def _caisse_snapshot(self) -> tuple:
        """Instantané normalisé et comparable de l'état courant de la
        caisse — même principe que ``SalesPage._caisse_snapshot``."""
        values = self._caisse_values()
        lignes = tuple(
            (line["article_id"], line["quantite"], line["tarif_jour"]) for line in values["lignes"]
        )
        return (values["date"], values["client_id"], values["commentaire"], lignes)

    def _on_caisse_save_draft_clicked(self) -> None:
        if self._submit_caisse("draft"):
            self._close_caisse()

    def _on_caisse_validate_clicked(self) -> None:
        if self._submit_caisse("validate"):
            self._close_caisse()

    def _submit_caisse(self, action: str) -> bool:
        """Isolé de ``_on_caisse_save_draft_clicked``/``_on_caisse_validate_clicked``
        pour rester testable sans écran modal — même principe que
        ``SalesPage._submit_caisse`` : désactive les deux boutons d'action
        pendant l'appel (protection contre une double soumission), puis les
        réactive si l'opération échoue pour permettre une nouvelle tentative
        sans perdre la saisie."""
        self.caisse_save_draft_button.setEnabled(False)
        self.caisse_validate_button.setEnabled(False)
        try:
            return self._submit_form(self._caisse_location_id, self._caisse_values(), action)
        finally:
            self.caisse_save_draft_button.setEnabled(True)
            self.caisse_validate_button.setEnabled(True)

    def _on_caisse_back_clicked(self) -> None:
        if not self._confirm_discard_caisse_if_needed():
            return
        self._close_caisse()

    # -- confirmation d'abandon d'une saisie non enregistrée -----------------

    def _caisse_has_unsaved_changes(self) -> bool:
        if self._view_stack.currentIndex() != 1 or self._caisse_initial_snapshot is None:
            return False
        return self._caisse_snapshot() != self._caisse_initial_snapshot

    def _confirm_discard_caisse_if_needed(self) -> bool:
        if not self._caisse_has_unsaved_changes():
            return True
        return confirm_action(
            self, "Modifications non enregistrées",
            "Cette location contient des modifications non enregistrées. "
            "Voulez-vous vraiment quitter sans les enregistrer ?",
        )

    def confirm_can_leave(self) -> bool:
        """Hook optionnel reconnu par ``MainWindow`` (voir
        ``_on_navigation_changed``) — même principe que
        ``SalesPage.confirm_can_leave``."""
        return self._confirm_discard_caisse_if_needed()

    def _create_client_from_values(self, values: dict) -> Optional[tuple[int, str]]:
        """Isolé de ``_on_caisse_new_client_clicked`` pour rester testable
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

    def _submit_form(self, location_id: Optional[int], values: dict, action: str = "draft") -> bool:
        """Convertit la saisie, appelle le service et affiche le résultat.
        Isolé de ``_open_caisse``/``_submit_caisse`` pour rester testable
        sans écran modal.

        ``action`` ('draft' ou 'validate') :
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
            location, self._currency_code, self._location_service, self._permissions,
            receipt_service=self._receipt_service, parent=self, read_only=self._read_only,
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
