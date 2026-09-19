"""Page de consultation du journal des mouvements de stock.

Strictement une vue de consultation : cette page n'appelle que
``MovementService.list_movements`` (lui-même strictement en lecture seule),
jamais ``StockService`` ni aucun service de document. Les mouvements ne sont
jamais modifiables ni supprimables — ni ici, ni ailleurs dans l'application
— voir ``app.models.movement.MouvementStock`` : c'est le journal d'audit du
stock lui-même, alimenté uniquement par ``StockService`` au fil des
validations d'Entrées/Sorties/Ventes/Inventaires. Cette page ne propose donc
aucun bouton d'action, uniquement des filtres de consultation.

Filtres regroupés derrière un bouton « Actualiser » explicite (plutôt qu'un
rafraîchissement à chaque frappe). Les deux dates de période sont des
``OptionalDateEdit`` (case à cocher + ``QDateEdit``) : décochées, aucune
borne n'est transmise au service (tout l'historique) — même convention que
la page Rapports (voir ``ReportsPage``).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import TypeMouvement
from app.services.auth.permission_service import PermissionService
from app.services.stock.movement_service import MovementService
from app.utils.exceptions import AppError
from app.views.optional_date_edit import OptionalDateEdit

_COLUMNS = [
    "Date/heure", "Article", "Type", "Quantité", "Stock avant", "Stock après",
    "Référence opération", "Utilisateur", "Commentaire",
]

_TYPE_LABELS: dict[TypeMouvement, str] = {
    TypeMouvement.ENTREE: "Entrée",
    TypeMouvement.SORTIE: "Sortie",
    TypeMouvement.VENTE: "Vente",
    TypeMouvement.AJUSTEMENT: "Ajustement",
    TypeMouvement.ANNULATION: "Annulation",
}


class MouvementsPage(QWidget):
    def __init__(
        self,
        movement_service: MovementService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._movement_service = movement_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher (article, utilisateur, commentaire)…")
        toolbar.addWidget(self.search_edit)

        toolbar.addWidget(QLabel("Du", self))
        self.date_from_edit = OptionalDateEdit(self)
        toolbar.addWidget(self.date_from_edit)

        toolbar.addWidget(QLabel("Au", self))
        self.date_to_edit = OptionalDateEdit(self)
        toolbar.addWidget(self.date_to_edit)

        self.type_filter_combo = QComboBox(self)
        self.type_filter_combo.addItem("(Tous les types)", None)
        for type_mouvement in TypeMouvement:
            self.type_filter_combo.addItem(_TYPE_LABELS.get(type_mouvement, type_mouvement.value), type_mouvement)
        toolbar.addWidget(self.type_filter_combo)

        self.refresh_button = QPushButton("Actualiser", self)
        toolbar.addWidget(self.refresh_button)

        self.reset_button = QPushButton("Réinitialiser les filtres", self)
        toolbar.addWidget(self.reset_button)

        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.summary_label = QLabel(self)
        layout.addWidget(self.summary_label)

        self.refresh_button.clicked.connect(self.refresh)
        self.reset_button.clicked.connect(self._on_reset_filters_clicked)

        self.refresh()

    # -- filtres -----------------------------------------------------------

    def _on_reset_filters_clicked(self) -> None:
        self.search_edit.clear()
        self.date_from_edit.set_date_or_none(None)
        self.date_to_edit.set_date_or_none(None)
        self.type_filter_combo.setCurrentIndex(0)
        self.refresh()

    # -- rafraîchissement ----------------------------------------------------

    def refresh(self) -> None:
        date_from = self.date_from_edit.date_or_none()
        date_to = self.date_to_edit.date_or_none()

        try:
            movements = self._movement_service.list_movements(
                term=self.search_edit.text(),
                date_from=date_from,
                date_to=date_to,
                type_mouvement=self.type_filter_combo.currentData(),
            )
        except AppError as exc:
            self.table.setRowCount(0)
            self.summary_label.setText("")
            QMessageBox.warning(self, "Mouvements indisponibles", str(exc))
            return

        self.table.setRowCount(len(movements))
        for row, mouvement in enumerate(movements):
            self.table.setItem(row, 0, QTableWidgetItem(mouvement.date_heure.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 1, QTableWidgetItem(mouvement.article_reference))
            self.table.setItem(row, 2, QTableWidgetItem(_TYPE_LABELS.get(mouvement.type, mouvement.type.value)))
            self.table.setItem(row, 3, QTableWidgetItem(str(mouvement.quantite)))
            self.table.setItem(row, 4, QTableWidgetItem(str(mouvement.stock_avant)))
            self.table.setItem(row, 5, QTableWidgetItem(str(mouvement.stock_apres)))
            self.table.setItem(row, 6, QTableWidgetItem(mouvement.reference_operation or "—"))
            self.table.setItem(row, 7, QTableWidgetItem(mouvement.username))
            self.table.setItem(row, 8, QTableWidgetItem(mouvement.commentaire or "—"))

        self.summary_label.setText(f"{len(movements)} mouvement(s)")
