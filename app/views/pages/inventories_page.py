"""Page de gestion des inventaires.

Toute action (création, modification, validation) passe par
:class:`InventoryService`, qui revérifie la permission côté service. Un
inventaire en brouillon ne modifie jamais le stock ; seule la validation le
fait — voir ``InventoryService.validate_inventory``. La modification n'est
proposée que pour le statut BROUILLON, à la fois dans l'activation des
boutons et dans la logique métier elle-même (défense en profondeur).

Volontairement AUCUN bouton d'annulation : il n'existe aucune permission
``INVENTORY_CANCEL`` en V1 (décision métier explicite de cette phase) — un
inventaire validé est définitif ; une correction ultérieure passe par un
nouvel inventaire.
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

from app.models.enums import StatutInventaire
from app.services.articles.article_service import ArticleService
from app.services.auth.permission_service import PermissionService
from app.services.inventory.inventory_service import InventaireLigneInput, InventoryService
from app.utils.exceptions import AppError, ValidationError
from app.views.common import confirm_action, parse_date, run_modal_form
from app.views.inventory_detail_dialog import InventoryDetailDialog
from app.views.inventory_form_dialog import InventoryFormDialog

_COLUMNS = ["Numéro", "Date", "Créé par", "Lignes", "Écart global", "Statut"]

_STATUT_LABELS = {
    StatutInventaire.BROUILLON: "Brouillon",
    StatutInventaire.VALIDE: "Validé",
}

_STATUS_FILTERS = [
    ("Tous", None),
    ("Brouillon", StatutInventaire.BROUILLON),
    ("Validé", StatutInventaire.VALIDE),
]


class InventoriesPage(QWidget):
    def __init__(
        self,
        inventory_service: InventoryService,
        article_service: ArticleService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._inventory_service = inventory_service
        self._article_service = article_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher (numéro)…")
        toolbar.addWidget(self.search_edit)

        self.status_filter_combo = QComboBox(self)
        for label, value in _STATUS_FILTERS:
            self.status_filter_combo.addItem(label, value)
        toolbar.addWidget(self.status_filter_combo)

        toolbar.addStretch(1)

        self.add_button = QPushButton("Nouvel inventaire", self)
        self.add_button.setEnabled(self._permissions.has_permission("INVENTORY_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        toolbar.addWidget(self.edit_button)

        self.detail_button = QPushButton("Détails", self)
        toolbar.addWidget(self.detail_button)

        self.validate_button = QPushButton("Valider", self)
        toolbar.addWidget(self.validate_button)

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
        self.table.itemSelectionChanged.connect(self._update_action_buttons)

        self.refresh()

    # -- affichage ---------------------------------------------------------

    def refresh(self) -> None:
        statut = self.status_filter_combo.currentData()
        try:
            inventories = self._inventory_service.list_inventories(search=self.search_edit.text(), statut=statut)
        except AppError:
            self.table.setRowCount(0)
            self._update_action_buttons()
            return

        self.table.setRowCount(len(inventories))
        for row, inventory in enumerate(inventories):
            numero_item = QTableWidgetItem(inventory.numero)
            numero_item.setData(Qt.ItemDataRole.UserRole, inventory.id)
            numero_item.setData(Qt.ItemDataRole.UserRole + 1, inventory.statut)
            self.table.setItem(row, 0, numero_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(inventory.date)))
            self.table.setItem(row, 2, QTableWidgetItem(inventory.username))
            self.table.setItem(row, 3, QTableWidgetItem(str(len(inventory.lignes))))
            self.table.setItem(row, 4, QTableWidgetItem(f"{inventory.ecart_total:+}"))
            self.table.setItem(row, 5, QTableWidgetItem(_STATUT_LABELS.get(inventory.statut, str(inventory.statut))))

        self._update_action_buttons()

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    def _selected_inventory_id(self) -> Optional[int]:
        row = self._selected_row()
        if row is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _selected_statut(self) -> Optional[StatutInventaire]:
        row = self._selected_row()
        if row is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)

    def _update_action_buttons(self) -> None:
        statut = self._selected_statut()
        is_brouillon = statut == StatutInventaire.BROUILLON

        self.edit_button.setEnabled(
            statut is not None and is_brouillon and self._permissions.has_permission("INVENTORY_UPDATE")
        )
        self.validate_button.setEnabled(
            statut is not None and is_brouillon and self._permissions.has_permission("INVENTORY_VALIDATE")
        )

    # -- chargement des listes pour les formulaires -------------------------

    def _load_articles_for_form(self) -> list[tuple[int, str, str]]:
        try:
            articles = self._article_service.list_articles(include_inactive=False)
        except AppError:
            articles = []
        return [(a.id, f"{a.reference} — {a.designation}", str(a.stock_actuel)) for a in articles]

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        articles = self._load_articles_for_form()
        initial = {"date": str(date.today())}
        self._open_form(inventory_id=None, articles=articles, initial=initial)

    def _on_edit_clicked(self) -> None:
        inventory_id = self._selected_inventory_id()
        if inventory_id is None:
            return
        initial = self._load_edit_initial(inventory_id)
        if initial is None:
            return
        articles = self._load_articles_for_form()
        self._open_form(inventory_id=inventory_id, articles=articles, initial=initial)

    def _load_edit_initial(self, inventory_id: int) -> Optional[dict]:
        """Récupère les valeurs actuelles d'un inventaire pour pré-remplir le
        formulaire de modification. Isolé de ``_on_edit_clicked`` pour rester
        testable sans dialogue modal."""
        try:
            inventory = self._inventory_service.get_inventory(inventory_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        return {
            "date": str(inventory.date),
            "lignes": [
                {
                    "article_id": ligne.article_id,
                    "article_label": f"{ligne.article_reference} — {ligne.article_designation}",
                    "stock_theorique": ligne.stock_theorique,
                    "stock_physique": ligne.stock_physique,
                }
                for ligne in inventory.lignes
            ],
        }

    def _open_form(self, inventory_id: Optional[int], articles: list[tuple[int, str, str]], initial: dict) -> None:
        state = {"values": initial}

        def factory() -> InventoryFormDialog:
            return InventoryFormDialog(articles, state["values"], parent=self)

        def submit(dialog: InventoryFormDialog) -> bool:
            state["values"] = dialog.values()
            return self._submit_form(inventory_id, state["values"])

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_form(self, inventory_id: Optional[int], values: dict) -> bool:
        """Convertit la saisie, appelle le service et affiche le résultat.
        Isolé de ``_open_form`` pour rester testable sans dialogue modal."""
        try:
            inventory_date = parse_date(values["date"], "date")
            lines = [
                InventaireLigneInput(article_id=line["article_id"], stock_physique=line["stock_physique"])
                for line in values["lignes"]
            ]

            if inventory_id is None:
                created = self._inventory_service.create_inventory(inventory_date, lines)
                QMessageBox.information(
                    self, "Inventaire créé", f"L'inventaire « {created.numero} » a été créé en brouillon."
                )
            else:
                updated = self._inventory_service.update_inventory(inventory_id, inventory_date, lines)
                QMessageBox.information(
                    self, "Inventaire modifié", f"L'inventaire « {updated.numero} » a été modifié."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- consultation détaillée ----------------------------------------------

    def _on_detail_clicked(self) -> None:
        inventory_id = self._selected_inventory_id()
        if inventory_id is None:
            return
        result = self._load_inventory_for_detail(inventory_id)
        if result is None:
            return
        inventory, movements = result
        dialog = InventoryDetailDialog(inventory, movements, parent=self)
        dialog.exec()

    def _load_inventory_for_detail(self, inventory_id: int):
        """Isolé de ``_on_detail_clicked`` pour rester testable sans dialogue modal."""
        try:
            inventory = self._inventory_service.get_inventory(inventory_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        movements = []
        if self._permissions.has_permission("STOCK_MOVEMENT_VIEW"):
            try:
                movements = self._inventory_service.get_inventory_movements(inventory_id)
            except AppError:
                movements = []
        return inventory, movements

    # -- validation -----------------------------------------------------------

    def _on_validate_clicked(self) -> None:
        inventory_id = self._selected_inventory_id()
        if inventory_id is None:
            return
        try:
            inventory = self._inventory_service.get_inventory(inventory_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return

        if not confirm_action(self, "Confirmation", self._build_validation_confirmation_message(inventory)):
            return
        if self._validate_selected(inventory_id):
            self.refresh()

    @staticmethod
    def _build_validation_confirmation_message(inventory) -> str:
        """Affiche clairement, avant validation, le stock théorique, le
        stock compté, l'écart et l'impact attendu sur le stock (§13 du
        cahier des charges de cette phase)."""
        lines_text = "\n".join(
            f"{ligne.article_reference} : théorique {ligne.stock_theorique}, "
            f"compté {ligne.stock_physique}, écart {ligne.ecart:+}"
            for ligne in inventory.lignes
        )
        return (
            f"Voulez-vous vraiment valider l'inventaire « {inventory.numero} » ?\n\n"
            f"{lines_text}\n\n"
            "Cette action applique définitivement ces écarts au stock (mouvements "
            "d'ajustement) et n'est pas réversible — aucune annulation n'est possible."
        )

    def _validate_selected(self, inventory_id: int) -> bool:
        """Isolé de ``_on_validate_clicked`` pour rester testable sans boîte modale."""
        try:
            validated = self._inventory_service.validate_inventory(inventory_id)
            QMessageBox.information(
                self, "Inventaire validé", f"L'inventaire « {validated.numero} » a été validé."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True
