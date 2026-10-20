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

Lot « Écran de caisse plein format » : cette page est désormais un
conteneur à deux sous-vues internes (``self._view_stack``, un
``QStackedWidget``) — la liste des ventes (index 0, widgets et
comportement strictement inchangés depuis les lots précédents) et un
nouvel écran de caisse plein format (index 1, voir ``_build_caisse_view``)
qui remplace ``SaleFormDialog`` comme point d'entrée de création/
modification depuis cette page. ``SaleFormDialog`` n'est ni supprimé ni
modifié : il reste disponible et testé indépendamment, simplement plus
appelé d'ici. La caisse réutilise ``_submit_form`` à l'identique (aucune
duplication de la logique de création/validation), et n'appelle jamais
``SaleService``/``StockService`` pour une simple modification locale du
tableau de lignes (ajout, suppression, changement de quantité) — ces
opérations ne touchent qu'un état en mémoire (``self._caisse_lines``)
jusqu'à l'enregistrement.

La détection d'une saisie non enregistrée (confirmation d'abandon, voir
``_caisse_has_unsaved_changes``) compare un instantané normalisé de l'état
courant à celui capturé à l'ouverture de la caisse (``_caisse_snapshot``/
``_caisse_initial_snapshot``) — jamais une simple présence de lignes :
rouvrir un brouillon existant puis quitter sans rien modifier ne déclenche
donc aucune confirmation superflue, alors qu'une nouvelle vente ou une
modification réelle (quantité, lignes, date, client) la déclenche toujours.
"""
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

from app.models.enums import ModeGestionArticle, StatutOperation
from app.services.articles.article_service import ArticleService
from app.services.auth.permission_service import PermissionService
from app.services.clients.client_service import ClientService
from app.services.documents.receipt_service import ReceiptService
from app.services.sales.sale_service import SaleService, VenteLigneInput
from app.services.settings.company_settings_service import get_effective_currency
from app.utils.exceptions import AppError, ValidationError
from app.utils.money import format_money
from app.utils.quantity import format_quantity
from app.views.cancellation_reason_dialog import CancellationReasonDialog
from app.views.client_form_dialog import ClientFormDialog
from app.views.common import confirm_action, date_to_qdate, parse_decimal, required_label
from app.views.sale_detail_dialog import SaleDetailDialog

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
_NO_CLIENT_LABEL = "(Aucun client / Vente comptant)"

_CAISSE_LINE_COLUMNS = ["Désignation", "Quantité", "Prix unitaire", "Montant"]
_CAISSE_QUANTITY_COLUMN = 1


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

        # -- état de la caisse (saisie en cours, jamais persistée tant que
        # l'utilisateur n'a pas cliqué « Enregistrer en brouillon »/« Valider
        # la vente ») -------------------------------------------------------
        self._caisse_sale_id: Optional[int] = None
        self._caisse_lines: list[dict] = []
        self._caisse_articles_cache: list[tuple[int, str, str]] = []
        self._caisse_clients: list[tuple[int, str]] = []
        # Instantané normalisé de l'état chargé à l'ouverture de la caisse
        # (nouvelle vente vide, ou brouillon existant tel que lu en base) —
        # voir ``_caisse_snapshot``/``_caisse_has_unsaved_changes``. Comparé
        # à l'état courant pour ne demander une confirmation d'abandon que
        # face à une modification réelle, jamais à la simple réouverture
        # d'un brouillon inchangé.
        self._caisse_initial_snapshot: Optional[tuple] = None

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)

        self._view_stack = QStackedWidget(self)
        page_layout.addWidget(self._view_stack)

        self._view_stack.addWidget(self._build_list_view())
        self._view_stack.addWidget(self._build_caisse_view())

        self.refresh()

    # ======================================================================
    # Vue liste (inchangée depuis les lots précédents)
    # ======================================================================

    def _build_list_view(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)

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

        return container

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
        sale_id = self._selected_sale_id()
        is_brouillon = statut == StatutOperation.BROUILLON
        is_validee = statut == StatutOperation.VALIDEE

        self.edit_button.setEnabled(
            statut is not None and is_brouillon and self._can_manage_selected(sale_id, "SALE_UPDATE")
        )
        self.delete_button.setEnabled(
            statut is not None and is_brouillon and self._can_manage_selected(sale_id, "SALE_UPDATE")
        )
        self.validate_button.setEnabled(
            statut is not None and is_brouillon and self._can_manage_selected(sale_id, "SALE_VALIDATE")
        )
        self.cancel_button.setEnabled(
            statut is not None and is_validee and self._can_manage_selected(sale_id, "SALE_CANCEL")
        )

    def _can_manage_selected(self, sale_id: Optional[int], permission_code: str) -> bool:
        """Confort d'interface uniquement (bouton désactivé) — n'est jamais
        ce qui empêche un contournement : ``SaleService`` revérifie la
        permission ET la règle de propriété Vendeur à chaque appel direct.
        Réutilise ``SaleService.can_manage_sale`` (aucune logique dupliquée)
        pour qu'un vendeur ne voie même pas un bouton actif pour une vente
        appartenant à un autre vendeur."""
        if sale_id is None:
            return False
        try:
            return self._sale_service.can_manage_sale(sale_id, permission_code)
        except AppError:
            return False

    # -- chargement des listes pour les formulaires -------------------------

    def _load_articles_for_form(self) -> list[tuple[int, str, str]]:
        """Seuls les articles actifs en mode VENTE sont proposés à la
        caisse (Lot 19) — un article configuré pour la location serait de
        toute façon refusé par ``SaleService.create_sale``/``update_sale``
        (voir leur vérification ``mode_gestion == LOCATION``) ; ce filtre
        n'est qu'une anticipation côté interface, jamais une nouvelle règle."""
        try:
            articles = self._article_service.list_articles(include_inactive=False)
        except AppError:
            articles = []
        return [
            (a.id, f"{a.reference} — {a.designation}", str(a.prix_vente))
            for a in articles
            if a.mode_gestion == ModeGestionArticle.VENTE
        ]

    def _lookup_article_by_barcode(self, code: str) -> Optional[tuple[int, str, str]]:
        """Point d'entrée du scan (lecteur USB « keyboard wedge ») : ne
        renvoie qu'un article actif ET en mode VENTE, au même format que
        ``_load_articles_for_form`` pour rester directement exploitable.
        Un article actif mais configuré pour la location n'est jamais
        renvoyé ici — voir ``_show_scan_rejection_message`` pour le message
        distinct présenté à l'utilisateur dans ce cas précis."""
        try:
            article = self._article_service.find_by_barcode(code)
        except AppError:
            return None
        if article is None or article.mode_gestion != ModeGestionArticle.VENTE:
            return None
        return article.id, f"{article.reference} — {article.designation}", str(article.prix_vente)

    def _load_clients_for_form(self) -> list[tuple[int, str]]:
        """Seuls les clients actifs sont proposés pour une nouvelle
        sélection (§8) — un client désactivé reste visible dans l'historique
        mais ne doit plus être choisi pour une nouvelle vente."""
        try:
            clients = self._client_service.list_clients(include_inactive=False)
        except AppError:
            clients = []
        return [(c.id, c.nom) for c in clients]

    def _load_edit_initial(self, sale_id: int) -> Optional[dict]:
        """Récupère les valeurs actuelles d'une vente pour pré-remplir la
        caisse en modification. Isolé de ``_on_edit_clicked`` pour rester
        testable sans écran modal."""
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

    def _create_client_from_sale_form(self) -> Optional[tuple[int, str]]:
        """Création de client « à la volée » (§5 du lot Clients) : ouvre
        ``ClientFormDialog`` par-dessus la caisse déjà ouverte, sans jamais
        la fermer ni réinitialiser son état — la date et les lignes déjà
        saisies restent intactes pendant toute l'opération. La création est
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

    def _submit_form(self, sale_id: Optional[int], values: dict, action: str = "draft") -> bool:
        """Convertit la saisie, appelle le service et affiche le résultat.
        Isolé pour rester testable sans écran modal — unique point d'appel
        de ``SaleService.create_sale``/``update_sale``/``validate_sale``
        pour cette page, utilisé par la caisse.

        ``action`` ('draft' ou 'validate') : si 'validate',
        ``SaleService.validate_sale`` est appelé dans la foulée, sans
        paiement initial (la caisse ne collecte aucun paiement — la vente
        validée reste à crédit, solde non payé ; le paiement s'enregistre
        ensuite via le détail de la vente, sans changement de ce lot). Si
        la création/modification réussit mais que la validation échoue
        (stock insuffisant, article inactif...), la vente reste en
        brouillon, retrouvable dans la liste — jamais recréée en double."""
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
                document = self._sale_service.create_sale(sale_date, lines, client_id=client_id)
                created_now = True
            else:
                document = self._sale_service.update_sale(sale_id, sale_date, lines, client_id=client_id)
                created_now = False
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False

        if action != "validate":
            if created_now:
                QMessageBox.information(
                    self, "Vente créée", f"La vente « {document.numero} » a été créée en brouillon."
                )
            else:
                QMessageBox.information(
                    self, "Vente modifiée", f"La vente « {document.numero} » a été modifiée."
                )
            return True

        try:
            validated = self._sale_service.validate_sale(document.id)
        except AppError as exc:
            QMessageBox.warning(
                self, "Vente enregistrée, validation refusée",
                f"La vente « {document.numero} » a été enregistrée en brouillon, mais n'a pas pu être "
                f"validée : {exc}\n\nVous pouvez la retrouver dans la liste pour la corriger ou la valider.",
            )
            return True

        QMessageBox.information(
            self, "Vente validée", f"La vente « {validated.numero} » a été créée et validée."
        )
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
            sale, movements, self._currency_code, self._receipt_service, self._permissions,
            sale_service=self._sale_service, parent=self,
        )
        dialog.exec()
        self.refresh()

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
        # Pré-vérification (règle de propriété Vendeur) : évite de demander
        # un motif de saisie pour un refus déjà certain. Confort uniquement —
        # SaleService.cancel_sale revérifie de toute façon la même règle.
        if not self._can_manage_selected(sale_id, "SALE_CANCEL"):
            QMessageBox.warning(
                self, "Action refusée",
                "Vous ne pouvez pas annuler la vente d'un autre vendeur.",
            )
            return
        dialog = CancellationReasonDialog("cette vente validée", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self._cancel_selected(sale_id, dialog.reason()):
            self.refresh()

    def _cancel_selected(self, sale_id: int, motif: str) -> bool:
        """Isolé de ``_on_cancel_clicked`` pour rester testable sans boîte modale."""
        try:
            cancelled = self._sale_service.cancel_sale(sale_id, motif)
            QMessageBox.information(
                self, "Vente annulée", f"La vente « {cancelled.numero} » a été annulée."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # ======================================================================
    # Caisse plein format (Lot « Écran de caisse »)
    # ======================================================================

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
        self.caisse_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.caisse_date_edit.setMaximumDate(QDate.currentDate())
        header_form.addRow(required_label("Date"), self.caisse_date_edit)

        client_row = QHBoxLayout()
        self.caisse_client_combo = QComboBox(panel)
        client_row.addWidget(self.caisse_client_combo)
        self.caisse_new_client_button = QPushButton("Nouveau client…", panel)
        client_row.addWidget(self.caisse_new_client_button)
        header_form.addRow("Client", client_row)

        layout.addLayout(header_form)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Rechercher un article", panel))
        self.caisse_search_edit = QLineEdit(panel)
        self.caisse_search_edit.setPlaceholderText("Désignation ou référence…")
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
        self.caisse_total_label = QLabel("", panel)
        self.caisse_total_label.setStyleSheet("font-weight: 600; font-size: 16px;")
        recap_form.addRow("Total", self.caisse_total_label)
        self.caisse_paye_label = QLabel("", panel)
        recap_form.addRow("Payé", self.caisse_paye_label)
        self.caisse_reste_label = QLabel("", panel)
        self.caisse_reste_label.setStyleSheet("font-weight: 600;")
        recap_form.addRow("Reste à payer", self.caisse_reste_label)
        layout.addLayout(recap_form)

        layout.addStretch(1)

        self.caisse_save_draft_button = QPushButton("Enregistrer en brouillon", panel)
        layout.addWidget(self.caisse_save_draft_button)

        self.caisse_validate_button = QPushButton("Valider la vente", panel)
        self.caisse_validate_button.setDefault(True)
        self.caisse_validate_button.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.caisse_validate_button)

        self.caisse_back_button = QPushButton("Retour à la liste", panel)
        layout.addWidget(self.caisse_back_button)

        self.caisse_save_draft_button.clicked.connect(self._on_caisse_save_draft_clicked)
        self.caisse_validate_button.clicked.connect(self._on_caisse_validate_clicked)
        self.caisse_back_button.clicked.connect(self._on_caisse_back_clicked)

        self._update_caisse_totals()

        return panel

    # -- ouverture de la caisse (remplace l'ancien formulaire modal) --------

    def _on_add_clicked(self) -> None:
        self._open_caisse(sale_id=None, initial={"date": date.today()})

    def _on_edit_clicked(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            return
        initial = self._load_edit_initial(sale_id)
        if initial is None:
            return
        self._open_caisse(sale_id=sale_id, initial=initial)

    def _open_caisse(self, sale_id: Optional[int], initial: dict) -> None:
        self._caisse_sale_id = sale_id
        self._caisse_lines = [dict(line) for line in initial.get("lignes", [])]
        self._caisse_articles_cache = self._load_articles_for_form()
        self._caisse_clients = self._load_clients_for_form()

        self.caisse_date_edit.setDate(date_to_qdate(initial.get("date") or date.today()))
        self._refresh_caisse_client_combo(selected_id=initial.get("client_id"))
        self.caisse_search_edit.clear()
        # Appel explicite (Lot 19) plutôt qu'une dépendance au signal de
        # ``clear()`` ci-dessus : ``QLineEdit.clear()`` n'émet
        # ``textChanged`` que si le texte change réellement — si le champ
        # était déjà vide (cas le plus fréquent, réouverture de la caisse),
        # la liste ne serait jamais peuplée sans cet appel direct. La liste
        # des articles vendables doit être visible dès l'ouverture, sans
        # attendre une saisie.
        self._refresh_caisse_search_results()
        self.caisse_scan_edit.clear()
        self.caisse_error_label.setText("")
        self.caisse_save_draft_button.setEnabled(True)
        self.caisse_validate_button.setEnabled(True)

        self._refresh_caisse_lines_table()
        # Capturé en tout dernier, une fois tous les widgets de la caisse
        # posés à leur valeur de départ (nouvelle vente vide, ou brouillon
        # tel que chargé) — voir ``_caisse_snapshot``.
        self._caisse_initial_snapshot = self._caisse_snapshot()
        self._view_stack.setCurrentIndex(1)

    def _close_caisse(self) -> None:
        self._caisse_sale_id = None
        self._caisse_lines = []
        self._caisse_initial_snapshot = None
        self._view_stack.setCurrentIndex(0)
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
        self._update_caisse_totals()

    def _on_caisse_new_client_clicked(self) -> None:
        """Création de client « à la volée » depuis la caisse : la saisie en
        cours (date, lignes) n'est jamais réinitialisée — ``ClientFormDialog``
        s'ouvre par-dessus sans toucher à ``self._caisse_lines``."""
        result = self._create_client_from_sale_form()
        if result is None:
            return
        client_id, client_nom = result
        self._caisse_clients.append((client_id, client_nom))
        self._refresh_caisse_client_combo(selected_id=client_id)

    # -- recherche d'articles -------------------------------------------------

    def _on_caisse_search_text_changed(self, text: str) -> None:
        self._refresh_caisse_search_results()

    def _refresh_caisse_search_results(self) -> None:
        """Repeuple la liste à partir du texte courant du champ de
        recherche — appelée au changement de texte, mais aussi directement
        à l'ouverture de la caisse (Lot 19) pour que la liste des articles
        vendables soit visible immédiatement, sans attendre une saisie.
        Texte vide -> tous les articles vendables (``_caisse_articles_cache``,
        déjà filtré sur le mode VENTE) ; texte non vide -> filtrage
        insensible à la casse sur le libellé référence+désignation déjà
        concaténé ; aucune correspondance avec un texte saisi -> un message
        explicite, jamais interprété comme un article sélectionnable."""
        self.caisse_search_results.clear()
        normalized = self.caisse_search_edit.text().strip().lower()
        candidates = self._caisse_articles_cache
        if normalized:
            candidates = [
                (article_id, label, prix_vente)
                for article_id, label, prix_vente in candidates
                if normalized in label.lower()
            ]
        if not candidates and normalized:
            empty_item = QListWidgetItem("Aucun article ne correspond à la recherche.", self.caisse_search_results)
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            return
        for article_id, label, prix_vente in candidates:
            display = f"{label}  —  {format_money(Decimal(str(prix_vente)), self._currency_code)}"
            item = QListWidgetItem(display, self.caisse_search_results)
            item.setData(Qt.ItemDataRole.UserRole, (article_id, label, prix_vente))

    def _on_caisse_search_result_activated(self, item: QListWidgetItem) -> None:
        # Garde-fou (Lot 19) : le message « aucun résultat » est affiché
        # dans ce même QListWidget mais ne porte aucune donnée — un
        # double-clic dessus ne doit jamais tenter d'ajouter une ligne.
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        article_id, label, prix_vente = data
        self._add_caisse_line(article_id, label, Decimal("1"), Decimal(str(prix_vente)))
        self.caisse_search_edit.clear()

    # -- scan code-barres (lecteur USB « keyboard wedge ») -------------------

    def _on_caisse_scan_entered(self) -> None:
        """Article actif trouvé -> ajout immédiat d'une ligne (quantité 1,
        prix de vente actuel), sans dialogue — comportement identique au
        scan déjà existant dans ``SaleFormDialog``. Introuvable -> message
        clair, aucune ligne ajoutée, aucun impact sur le stock (une ligne
        de brouillon n'a d'existence qu'en mémoire)."""
        code = self.caisse_scan_edit.text().strip()
        self.caisse_scan_edit.clear()
        if not code:
            return
        result = self._lookup_article_by_barcode(code)
        if result is None:
            self._show_scan_rejection_message(code)
            return
        article_id, label, prix_vente = result
        self._add_caisse_line(article_id, label, Decimal("1"), Decimal(str(prix_vente)))

    def _show_scan_rejection_message(self, code: str) -> None:
        """Isolé de ``_on_caisse_scan_entered`` (Lot 19) : distingue un
        code-barres réellement inconnu (ou inactif) d'un article existant
        mais configuré pour la location — une seconde lecture via
        ``find_by_barcode`` (déjà utilisé par ``_lookup_article_by_barcode``,
        jamais de nouvel appel mutant ni de règle métier supplémentaire)
        permet de distinguer les deux cas pour l'utilisateur."""
        try:
            article = self._article_service.find_by_barcode(code)
        except AppError:
            article = None
        if article is not None and article.mode_gestion == ModeGestionArticle.LOCATION:
            QMessageBox.warning(
                self, "Article non vendable",
                f"L'article « {article.reference} — {article.designation} » est configuré pour "
                "la location : il ne peut pas être ajouté à une vente.",
            )
            return
        QMessageBox.warning(
            self, "Article introuvable",
            f"Aucun article actif ne correspond au code-barres « {code} ».",
        )

    # -- gestion centralisée des lignes --------------------------------------

    def _add_caisse_line(self, article_id: int, article_label: str, quantite: Decimal, prix_unitaire: Decimal) -> None:
        """Point d'entrée unique pour ajouter une ligne à la vente en cours
        de saisie, quelle que soit son origine (recherche ou scan) —
        centralise aussi le recalcul du total. N'appelle jamais de service
        métier : une ligne de brouillon n'a d'existence qu'en mémoire
        jusqu'à l'enregistrement."""
        self.caisse_error_label.setText("")
        self._caisse_lines.append(
            {
                "article_id": article_id,
                "article_label": article_label,
                "quantite": quantite,
                "prix_unitaire": prix_unitaire,
            }
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
        """Seule la colonne « Quantité » est éditable (voir
        ``_refresh_caisse_lines_table``) : point d'entrée unique pour toute
        modification de quantité, quelle qu'en soit l'origine (double-clic
        ou touche d'édition). Une valeur invalide est refusée avec un
        message clair et la cellule reprend sa valeur précédente — jamais de
        ligne laissée dans un état incohérent, jamais d'appel service pour
        ce simple ajustement local."""
        if item.column() != _CAISSE_QUANTITY_COLUMN:
            return
        row = item.row()
        if row >= len(self._caisse_lines):
            return
        try:
            nouvelle_quantite = parse_decimal(item.text(), "quantité")
            if nouvelle_quantite <= 0:
                raise ValidationError("La quantité doit être strictement positive.")
        except ValidationError as exc:
            self.caisse_error_label.setText(str(exc))
            self._refresh_caisse_lines_table()
            return
        self.caisse_error_label.setText("")
        self._caisse_lines[row]["quantite"] = nouvelle_quantite
        self._refresh_caisse_lines_table()

    def _refresh_caisse_lines_table(self) -> None:
        self.caisse_lines_table.blockSignals(True)
        self.caisse_lines_table.setRowCount(len(self._caisse_lines))
        for row, line in enumerate(self._caisse_lines):
            designation_item = QTableWidgetItem(line["article_label"])
            designation_item.setFlags(designation_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.caisse_lines_table.setItem(row, 0, designation_item)

            quantite_item = QTableWidgetItem(format_quantity(line["quantite"]))
            quantite_item.setFlags(quantite_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.caisse_lines_table.setItem(row, _CAISSE_QUANTITY_COLUMN, quantite_item)

            prix_item = QTableWidgetItem(format_money(line["prix_unitaire"], self._currency_code))
            prix_item.setFlags(prix_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.caisse_lines_table.setItem(row, 2, prix_item)

            montant = line["quantite"] * line["prix_unitaire"]
            montant_item = QTableWidgetItem(format_money(montant, self._currency_code))
            montant_item.setFlags(montant_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.caisse_lines_table.setItem(row, 3, montant_item)
        self.caisse_lines_table.blockSignals(False)
        self._update_caisse_totals()

    def _caisse_total(self) -> Decimal:
        total = Decimal("0")
        for line in self._caisse_lines:
            total += line["quantite"] * line["prix_unitaire"]
        return total

    def _update_caisse_totals(self) -> None:
        """Centralise le recalcul du panneau droit — appelé après tout ajout,
        suppression ou modification de ligne, et après tout changement de
        client. Une vente en cours de création est toujours en BROUILLON
        (jamais de paiement possible sur un brouillon, voir
        ``SaleService``) : payé reste à 0, reste à payer égal au total."""
        total = self._caisse_total()
        self.caisse_total_label.setText(format_money(total, self._currency_code))
        self.caisse_lines_count_label.setText(str(len(self._caisse_lines)))
        self.caisse_paye_label.setText(format_money(Decimal("0"), self._currency_code))
        self.caisse_reste_label.setText(format_money(total, self._currency_code))
        client_id = self.caisse_client_combo.currentData() if hasattr(self, "caisse_client_combo") else None
        if client_id is None:
            self.caisse_client_recap_label.setText("(Aucun client / Vente comptant)")
        else:
            self.caisse_client_recap_label.setText(self.caisse_client_combo.currentText())

    # -- enregistrement / validation / retour --------------------------------

    def _caisse_values(self) -> dict:
        return {
            "date": self.caisse_date_edit.date().toPython(),
            "client_id": self.caisse_client_combo.currentData(),
            "lignes": list(self._caisse_lines),
        }

    def _caisse_snapshot(self) -> tuple:
        """Instantané normalisé et comparable de l'état courant de la
        caisse (date, client, lignes réduites à leurs seules données
        métier — jamais le libellé affiché, purement dérivé). Comparé à
        ``self._caisse_initial_snapshot`` par ``_caisse_has_unsaved_changes``
        : une égalité de tuples (``Decimal``/``date``/``int`` sont tous
        comparables par valeur) suffit à détecter fiablement l'absence de
        changement réel, y compris si une modification a été annulée en
        revenant exactement à l'état initial (ex. ajout puis suppression
        de la même ligne)."""
        values = self._caisse_values()
        lignes = tuple(
            (line["article_id"], line["quantite"], line["prix_unitaire"]) for line in values["lignes"]
        )
        return (values["date"], values["client_id"], lignes)

    def _on_caisse_save_draft_clicked(self) -> None:
        if self._submit_caisse("draft"):
            self._close_caisse()

    def _on_caisse_validate_clicked(self) -> None:
        if self._submit_caisse("validate"):
            self._close_caisse()

    def _submit_caisse(self, action: str) -> bool:
        """Isolé de ``_on_caisse_save_draft_clicked``/``_on_caisse_validate_clicked``
        pour rester testable sans écran modal. Désactive les deux boutons
        d'action pendant l'appel (protection contre une double soumission en
        plus — jamais à la place — du contrôle de statut déjà fait par
        ``SaleService``), puis les réactive si l'opération échoue pour
        permettre une nouvelle tentative sans perdre la saisie."""
        self.caisse_save_draft_button.setEnabled(False)
        self.caisse_validate_button.setEnabled(False)
        try:
            return self._submit_form(self._caisse_sale_id, self._caisse_values(), action)
        finally:
            self.caisse_save_draft_button.setEnabled(True)
            self.caisse_validate_button.setEnabled(True)

    def _on_caisse_back_clicked(self) -> None:
        if not self._confirm_discard_caisse_if_needed():
            return
        self._close_caisse()

    def _caisse_has_unsaved_changes(self) -> bool:
        """Compare l'état courant à l'instantané capturé à l'ouverture de la
        caisse (voir ``_open_caisse``/``_caisse_snapshot``) — jamais un
        simple « contient au moins une ligne », qui déclencherait une
        confirmation même pour un brouillon existant rouvert puis quitté
        sans aucune modification. ``_caisse_initial_snapshot`` est ``None``
        hors caisse (voir ``_close_caisse``), d'où le premier contrôle."""
        if self._view_stack.currentIndex() != 1 or self._caisse_initial_snapshot is None:
            return False
        return self._caisse_snapshot() != self._caisse_initial_snapshot

    def _confirm_discard_caisse_if_needed(self) -> bool:
        """Partagé entre le bouton « Retour à la liste » et
        ``confirm_can_leave`` (appelé par ``MainWindow`` avant tout
        changement de module) : ``True`` si la caisse peut être quittée sans
        confirmation supplémentaire (rien à perdre), ou si l'utilisateur a
        explicitement confirmé l'abandon de la saisie en cours."""
        if not self._caisse_has_unsaved_changes():
            return True
        return confirm_action(
            self, "Modifications non enregistrées",
            "Cette vente contient des articles non enregistrés. "
            "Voulez-vous vraiment quitter la caisse sans les enregistrer ?",
        )

    def confirm_can_leave(self) -> bool:
        """Hook optionnel reconnu par ``MainWindow`` (voir
        ``_on_navigation_changed``) : appelé avant tout changement de
        module de la navigation principale. Retourne ``False`` pour annuler
        le changement si l'utilisateur renonce à abandonner une saisie non
        enregistrée dans la caisse."""
        return self._confirm_discard_caisse_if_needed()
