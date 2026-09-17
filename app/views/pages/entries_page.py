"""Page de gestion des entrées de stock.

Toute action (création, modification, validation, annulation) passe par
:class:`EntryService`, qui revérifie la permission côté service. Une entrée
en brouillon ne modifie jamais le stock ; seule la validation le fait — voir
``EntryService.validate_entry``. Modification et annulation ne sont
proposées que pour les statuts compatibles (BROUILLON / VALIDEE
respectivement), à la fois dans l'activation des boutons et dans la logique
métier elle-même (défense en profondeur).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import get_settings
from app.models.enums import StatutOperation
from app.services.articles.article_service import ArticleService
from app.services.auth.permission_service import PermissionService
from app.services.entries.entry_service import EntreeLigneInput, EntryService
from app.services.suppliers.supplier_service import SupplierService
from app.utils.exceptions import AppError, ValidationError
from app.utils.money import format_money
from app.views.common import confirm_action, parse_date, parse_decimal, run_modal_form
from app.views.entry_detail_dialog import EntryDetailDialog
from app.views.entry_form_dialog import EntryFormDialog

_COLUMNS = ["Numéro", "Date", "Fournisseur", "Référence document", "Total", "Statut", "Créée par"]

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


class EntriesPage(QWidget):
    def __init__(
        self,
        entry_service: EntryService,
        supplier_service: SupplierService,
        article_service: ArticleService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._entry_service = entry_service
        self._supplier_service = supplier_service
        self._article_service = article_service
        self._permissions = permission_service
        self._currency_code = get_settings().default_currency

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher (numéro, référence, fournisseur)…")
        toolbar.addWidget(self.search_edit)

        self.status_filter_combo = QComboBox(self)
        for label, value in _STATUS_FILTERS:
            self.status_filter_combo.addItem(label, value)
        toolbar.addWidget(self.status_filter_combo)

        toolbar.addStretch(1)

        self.add_button = QPushButton("Ajouter", self)
        self.add_button.setEnabled(self._permissions.has_permission("STOCK_ENTRY_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        toolbar.addWidget(self.edit_button)

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
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.detail_button.clicked.connect(self._on_detail_clicked)
        self.validate_button.clicked.connect(self._on_validate_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.table.itemSelectionChanged.connect(self._update_action_buttons)

        self.refresh()

    # -- affichage ---------------------------------------------------------

    def refresh(self) -> None:
        statut = self.status_filter_combo.currentData()
        try:
            entries = self._entry_service.list_entries(search=self.search_edit.text(), statut=statut)
        except AppError:
            self.table.setRowCount(0)
            self._update_action_buttons()
            return

        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            numero_item = QTableWidgetItem(entry.numero)
            numero_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            numero_item.setData(Qt.ItemDataRole.UserRole + 1, entry.statut)
            self.table.setItem(row, 0, numero_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(entry.date)))
            self.table.setItem(row, 2, QTableWidgetItem(entry.fournisseur_nom))
            self.table.setItem(row, 3, QTableWidgetItem(entry.reference_document or "—"))
            self.table.setItem(row, 4, QTableWidgetItem(format_money(entry.total, self._currency_code)))
            self.table.setItem(row, 5, QTableWidgetItem(_STATUT_LABELS.get(entry.statut, str(entry.statut))))
            self.table.setItem(row, 6, QTableWidgetItem(entry.username))

        self._update_action_buttons()

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    def _selected_entry_id(self) -> Optional[int]:
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
            statut is not None and is_brouillon and self._permissions.has_permission("STOCK_ENTRY_UPDATE")
        )
        self.validate_button.setEnabled(
            statut is not None and is_brouillon and self._permissions.has_permission("STOCK_ENTRY_VALIDATE")
        )
        self.cancel_button.setEnabled(
            statut is not None and is_validee and self._permissions.has_permission("STOCK_ENTRY_CANCEL")
        )

    # -- chargement des listes pour les formulaires -------------------------

    def _load_suppliers_for_form(self) -> list[tuple[int, str]]:
        try:
            suppliers = self._supplier_service.list_suppliers(include_inactive=False)
        except AppError:
            suppliers = []
        return [(s.id, s.nom) for s in suppliers]

    def _load_articles_for_form(self) -> list[tuple[int, str, str]]:
        try:
            articles = self._article_service.list_articles(include_inactive=False)
        except AppError:
            articles = []
        return [(a.id, f"{a.reference} — {a.designation}", str(a.prix_achat)) for a in articles]

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        suppliers = self._load_suppliers_for_form()
        articles = self._load_articles_for_form()
        initial = {"date": str(date.today())}
        self._open_form(entry_id=None, suppliers=suppliers, articles=articles, initial=initial)

    def _on_edit_clicked(self) -> None:
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        initial = self._load_edit_initial(entry_id)
        if initial is None:
            return
        suppliers = self._load_suppliers_for_form()
        articles = self._load_articles_for_form()
        self._open_form(entry_id=entry_id, suppliers=suppliers, articles=articles, initial=initial)

    def _load_edit_initial(self, entry_id: int) -> Optional[dict]:
        """Récupère les valeurs actuelles d'une entrée pour pré-remplir le
        formulaire de modification. Isolé de ``_on_edit_clicked`` pour rester
        testable sans dialogue modal."""
        try:
            entry = self._entry_service.get_entry(entry_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        return {
            "fournisseur_id": entry.fournisseur_id,
            "date": str(entry.date),
            "reference_document": entry.reference_document,
            "commentaire": entry.commentaire,
            "lignes": [
                {
                    "article_id": ligne.article_id,
                    "article_label": f"{ligne.article_reference} — {ligne.article_designation}",
                    "quantite": ligne.quantite,
                    "prix_unitaire": ligne.prix_unitaire,
                }
                for ligne in entry.lignes
            ],
        }

    def _open_form(
        self,
        entry_id: Optional[int],
        suppliers: list[tuple[int, str]],
        articles: list[tuple[int, str, str]],
        initial: dict,
    ) -> None:
        state = {"values": initial}

        def factory() -> EntryFormDialog:
            return EntryFormDialog(suppliers, articles, state["values"], parent=self)

        def submit(dialog: EntryFormDialog) -> bool:
            state["values"] = dialog.values()
            return self._submit_form(entry_id, state["values"])

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_form(self, entry_id: Optional[int], values: dict) -> bool:
        """Convertit la saisie, appelle le service et affiche le résultat.
        Isolé de ``_open_form`` pour rester testable sans dialogue modal."""
        try:
            fournisseur_id = values["fournisseur_id"]
            if fournisseur_id is None:
                raise ValidationError("Veuillez sélectionner un fournisseur.")
            entry_date = parse_date(values["date"], "date")
            lines = [
                EntreeLigneInput(
                    article_id=line["article_id"],
                    quantite=line["quantite"],
                    prix_unitaire=line["prix_unitaire"],
                )
                for line in values["lignes"]
            ]

            if entry_id is None:
                created = self._entry_service.create_entry(
                    fournisseur_id,
                    entry_date,
                    lines,
                    reference_document=values["reference_document"],
                    commentaire=values["commentaire"],
                )
                QMessageBox.information(
                    self, "Entrée créée", f"L'entrée « {created.numero} » a été créée en brouillon."
                )
            else:
                updated = self._entry_service.update_entry(
                    entry_id,
                    fournisseur_id,
                    entry_date,
                    lines,
                    reference_document=values["reference_document"],
                    commentaire=values["commentaire"],
                )
                QMessageBox.information(
                    self, "Entrée modifiée", f"L'entrée « {updated.numero} » a été modifiée."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- consultation détaillée ----------------------------------------------

    def _on_detail_clicked(self) -> None:
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        result = self._load_entry_for_detail(entry_id)
        if result is None:
            return
        entry, movements = result
        dialog = EntryDetailDialog(entry, movements, self._currency_code, parent=self)
        dialog.exec()

    def _load_entry_for_detail(self, entry_id: int):
        """Isolé de ``_on_detail_clicked`` pour rester testable sans dialogue modal."""
        try:
            entry = self._entry_service.get_entry(entry_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        movements = []
        if self._permissions.has_permission("STOCK_MOVEMENT_VIEW"):
            try:
                movements = self._entry_service.get_entry_movements(entry_id)
            except AppError:
                movements = []
        return entry, movements

    # -- validation / annulation ---------------------------------------------

    def _on_validate_clicked(self) -> None:
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        if not confirm_action(
            self, "Confirmation", "Voulez-vous vraiment valider cette entrée ? "
            "Cette action met à jour le stock et n'est pas réversible autrement que par annulation."
        ):
            return
        if self._validate_selected(entry_id):
            self.refresh()

    def _validate_selected(self, entry_id: int) -> bool:
        """Isolé de ``_on_validate_clicked`` pour rester testable sans boîte modale."""
        try:
            validated = self._entry_service.validate_entry(entry_id)
            QMessageBox.information(
                self, "Entrée validée", f"L'entrée « {validated.numero} » a été validée."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    def _on_cancel_clicked(self) -> None:
        entry_id = self._selected_entry_id()
        if entry_id is None:
            return
        if not confirm_action(
            self, "Confirmation", "Voulez-vous vraiment annuler cette entrée validée ?"
        ):
            return
        if self._cancel_selected(entry_id):
            self.refresh()

    def _cancel_selected(self, entry_id: int) -> bool:
        """Isolé de ``_on_cancel_clicked`` pour rester testable sans boîte modale."""
        try:
            cancelled = self._entry_service.cancel_entry(entry_id)
            QMessageBox.information(
                self, "Entrée annulée", f"L'entrée « {cancelled.numero} » a été annulée."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True
