"""Page de gestion des sorties de stock.

Toute action (création, modification, validation, annulation) passe par
:class:`ExitService`, qui revérifie la permission côté service. Une sortie
en brouillon ne modifie jamais le stock ; seule la validation le fait — voir
``ExitService.validate_exit``. Modification et annulation ne sont proposées
que pour les statuts compatibles (BROUILLON / VALIDEE respectivement), à la
fois dans l'activation des boutons et dans la logique métier elle-même
(défense en profondeur).
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
from app.services.exit_reasons.exit_reason_service import ExitReasonService
from app.services.exits.exit_service import ExitService, SortieLigneInput
from app.utils.exceptions import AppError, ValidationError
from app.utils.money import format_money
from app.views.common import confirm_action, parse_date, run_modal_form
from app.views.exit_detail_dialog import ExitDetailDialog
from app.views.exit_form_dialog import ExitFormDialog

_COLUMNS = ["Numéro", "Date", "Motif", "Bénéficiaire", "Total", "Statut", "Créée par"]

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


class ExitsPage(QWidget):
    def __init__(
        self,
        exit_service: ExitService,
        exit_reason_service: ExitReasonService,
        article_service: ArticleService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._exit_service = exit_service
        self._exit_reason_service = exit_reason_service
        self._article_service = article_service
        self._permissions = permission_service
        self._currency_code = get_settings().default_currency

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher (numéro, référence, bénéficiaire, motif)…")
        toolbar.addWidget(self.search_edit)

        self.status_filter_combo = QComboBox(self)
        for label, value in _STATUS_FILTERS:
            self.status_filter_combo.addItem(label, value)
        toolbar.addWidget(self.status_filter_combo)

        toolbar.addStretch(1)

        self.add_button = QPushButton("Ajouter", self)
        self.add_button.setEnabled(self._permissions.has_permission("STOCK_EXIT_CREATE"))
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
            exits = self._exit_service.list_exits(search=self.search_edit.text(), statut=statut)
        except AppError:
            self.table.setRowCount(0)
            self._update_action_buttons()
            return

        self.table.setRowCount(len(exits))
        for row, exit_ in enumerate(exits):
            numero_item = QTableWidgetItem(exit_.numero)
            numero_item.setData(Qt.ItemDataRole.UserRole, exit_.id)
            numero_item.setData(Qt.ItemDataRole.UserRole + 1, exit_.statut)
            self.table.setItem(row, 0, numero_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(exit_.date)))
            self.table.setItem(row, 2, QTableWidgetItem(exit_.motif_libelle))
            self.table.setItem(row, 3, QTableWidgetItem(exit_.beneficiaire or "—"))
            self.table.setItem(row, 4, QTableWidgetItem(format_money(exit_.total, self._currency_code)))
            self.table.setItem(row, 5, QTableWidgetItem(_STATUT_LABELS.get(exit_.statut, str(exit_.statut))))
            self.table.setItem(row, 6, QTableWidgetItem(exit_.username))

        self._update_action_buttons()

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    def _selected_exit_id(self) -> Optional[int]:
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
            statut is not None and is_brouillon and self._permissions.has_permission("STOCK_EXIT_UPDATE")
        )
        self.validate_button.setEnabled(
            statut is not None and is_brouillon and self._permissions.has_permission("STOCK_EXIT_VALIDATE")
        )
        self.cancel_button.setEnabled(
            statut is not None and is_validee and self._permissions.has_permission("STOCK_EXIT_CANCEL")
        )

    # -- chargement des listes pour les formulaires -------------------------

    def _load_motifs_for_form(self) -> list[tuple[int, str]]:
        try:
            motifs = self._exit_reason_service.list_exit_reasons(include_inactive=False)
        except AppError:
            motifs = []
        return [(m.id, m.libelle) for m in motifs]

    def _load_articles_for_form(self) -> list[tuple[int, str, str]]:
        try:
            articles = self._article_service.list_articles(include_inactive=False)
        except AppError:
            articles = []
        return [(a.id, f"{a.reference} — {a.designation}", str(a.cout_moyen_pondere)) for a in articles]

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        motifs = self._load_motifs_for_form()
        articles = self._load_articles_for_form()
        initial = {"date": str(date.today())}
        self._open_form(exit_id=None, motifs=motifs, articles=articles, initial=initial)

    def _on_edit_clicked(self) -> None:
        exit_id = self._selected_exit_id()
        if exit_id is None:
            return
        initial = self._load_edit_initial(exit_id)
        if initial is None:
            return
        motifs = self._load_motifs_for_form()
        articles = self._load_articles_for_form()
        self._open_form(exit_id=exit_id, motifs=motifs, articles=articles, initial=initial)

    def _load_edit_initial(self, exit_id: int) -> Optional[dict]:
        """Récupère les valeurs actuelles d'une sortie pour pré-remplir le
        formulaire de modification. Isolé de ``_on_edit_clicked`` pour rester
        testable sans dialogue modal."""
        try:
            exit_ = self._exit_service.get_exit(exit_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        return {
            "motif_id": exit_.motif_id,
            "date": str(exit_.date),
            "beneficiaire": exit_.beneficiaire,
            "reference": exit_.reference,
            "commentaire": exit_.commentaire,
            "lignes": [
                {
                    "article_id": ligne.article_id,
                    "article_label": f"{ligne.article_reference} — {ligne.article_designation}",
                    "quantite": ligne.quantite,
                    "cout_unitaire": ligne.cout_unitaire,
                }
                for ligne in exit_.lignes
            ],
        }

    def _open_form(
        self,
        exit_id: Optional[int],
        motifs: list[tuple[int, str]],
        articles: list[tuple[int, str, str]],
        initial: dict,
    ) -> None:
        state = {"values": initial}

        def factory() -> ExitFormDialog:
            return ExitFormDialog(motifs, articles, state["values"], parent=self)

        def submit(dialog: ExitFormDialog) -> bool:
            state["values"] = dialog.values()
            return self._submit_form(exit_id, state["values"])

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_form(self, exit_id: Optional[int], values: dict) -> bool:
        """Convertit la saisie, appelle le service et affiche le résultat.
        Isolé de ``_open_form`` pour rester testable sans dialogue modal."""
        try:
            motif_id = values["motif_id"]
            if motif_id is None:
                raise ValidationError("Veuillez sélectionner un motif.")
            exit_date = parse_date(values["date"], "date")
            lines = [
                SortieLigneInput(article_id=line["article_id"], quantite=line["quantite"])
                for line in values["lignes"]
            ]

            if exit_id is None:
                created = self._exit_service.create_exit(
                    motif_id,
                    exit_date,
                    lines,
                    beneficiaire=values["beneficiaire"],
                    reference=values["reference"],
                    commentaire=values["commentaire"],
                )
                QMessageBox.information(
                    self, "Sortie créée", f"La sortie « {created.numero} » a été créée en brouillon."
                )
            else:
                updated = self._exit_service.update_exit(
                    exit_id,
                    motif_id,
                    exit_date,
                    lines,
                    beneficiaire=values["beneficiaire"],
                    reference=values["reference"],
                    commentaire=values["commentaire"],
                )
                QMessageBox.information(
                    self, "Sortie modifiée", f"La sortie « {updated.numero} » a été modifiée."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- consultation détaillée ----------------------------------------------

    def _on_detail_clicked(self) -> None:
        exit_id = self._selected_exit_id()
        if exit_id is None:
            return
        result = self._load_exit_for_detail(exit_id)
        if result is None:
            return
        exit_, movements = result
        dialog = ExitDetailDialog(exit_, movements, self._currency_code, parent=self)
        dialog.exec()

    def _load_exit_for_detail(self, exit_id: int):
        """Isolé de ``_on_detail_clicked`` pour rester testable sans dialogue modal."""
        try:
            exit_ = self._exit_service.get_exit(exit_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        movements = []
        if self._permissions.has_permission("STOCK_MOVEMENT_VIEW"):
            try:
                movements = self._exit_service.get_exit_movements(exit_id)
            except AppError:
                movements = []
        return exit_, movements

    # -- validation / annulation ---------------------------------------------

    def _on_validate_clicked(self) -> None:
        exit_id = self._selected_exit_id()
        if exit_id is None:
            return
        if not confirm_action(
            self, "Confirmation", "Voulez-vous vraiment valider cette sortie ? "
            "Cette action met à jour le stock et n'est pas réversible autrement que par annulation."
        ):
            return
        if self._validate_selected(exit_id):
            self.refresh()

    def _validate_selected(self, exit_id: int) -> bool:
        """Isolé de ``_on_validate_clicked`` pour rester testable sans boîte modale."""
        try:
            validated = self._exit_service.validate_exit(exit_id)
            QMessageBox.information(
                self, "Sortie validée", f"La sortie « {validated.numero} » a été validée."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    def _on_cancel_clicked(self) -> None:
        exit_id = self._selected_exit_id()
        if exit_id is None:
            return
        if not confirm_action(
            self, "Confirmation", "Voulez-vous vraiment annuler cette sortie validée ?"
        ):
            return
        if self._cancel_selected(exit_id):
            self.refresh()

    def _cancel_selected(self, exit_id: int) -> bool:
        """Isolé de ``_on_cancel_clicked`` pour rester testable sans boîte modale."""
        try:
            cancelled = self._exit_service.cancel_exit(exit_id)
            QMessageBox.information(
                self, "Sortie annulée", f"La sortie « {cancelled.numero} » a été annulée."
            )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True
