"""Page de consultation du journal d'audit (lecture seule).

Strictement une vue de consultation, même principe que ``MouvementsPage`` :
cette page n'appelle que ``AuditService.list_audits``/``list_entites``
(tous deux strictement en lecture seule), jamais aucune méthode d'écriture
— il n'en existe d'ailleurs aucune sur ``AuditService``. Aucun bouton de
création, modification ou suppression, ici ni ailleurs : le mécanisme
d'écriture des audits reste entièrement porté par les services métier
eux-mêmes (chacun via sa propre méthode privée ``_audit``/``_log_audit``,
inchangée par ce module).

Période par défaut : 30 derniers jours, pour éviter de charger tout
l'historique à l'ouverture (celui-ci peut devenir volumineux avec le temps,
voir le repository). C'est une simple valeur initiale des champs de date,
jamais une limite imposée : l'utilisateur peut modifier ou vider ces champs
pour accéder à l'historique complet, et aucun audit n'est jamais supprimé,
archivé ou masqué définitivement par cette valeur.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

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

from app.models.enums import ResultatAudit
from app.services.audit.audit_service import AuditService
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import AppError
from app.views.audit_detail_dialog import AuditDetailDialog
from app.views.common import parse_date

_COLUMNS = ["Date/heure", "Utilisateur", "Action", "Entité", "Référence", "Résultat", "Détails"]

_RESULTAT_LABELS = {
    ResultatAudit.SUCCES: "Succès",
    ResultatAudit.ECHEC: "Échec",
}

_DEFAULT_PERIOD_DAYS = 30


class AuditPage(QWidget):
    def __init__(
        self,
        audit_service: AuditService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._audit_service = audit_service
        self._permissions = permission_service
        # Alimente le dialogue de détail sans re-requêter la base au
        # double-clic : les lignes affichées sont déjà les objets chargés
        # par le dernier ``refresh()``.
        self._current_audits: list = []

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher (action, utilisateur, détails)…")
        toolbar.addWidget(self.search_edit)

        self.date_from_edit = QLineEdit(self)
        self.date_from_edit.setPlaceholderText("Du (AAAA-MM-JJ)")
        toolbar.addWidget(self.date_from_edit)

        self.date_to_edit = QLineEdit(self)
        self.date_to_edit.setPlaceholderText("Au (AAAA-MM-JJ)")
        toolbar.addWidget(self.date_to_edit)

        self.entite_filter_combo = QComboBox(self)
        self.entite_filter_combo.addItem("(Toutes les entités)", None)
        for entite in self._safe_list_entites():
            self.entite_filter_combo.addItem(entite, entite)
        toolbar.addWidget(self.entite_filter_combo)

        self.refresh_button = QPushButton("Actualiser", self)
        toolbar.addWidget(self.refresh_button)

        self.reset_button = QPushButton("Réinitialiser les filtres", self)
        toolbar.addWidget(self.reset_button)

        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.period_notice_label = QLabel(
            f"Période affichée par défaut : {_DEFAULT_PERIOD_DAYS} derniers jours — "
            "modifiez ou videz les champs de date pour consulter l'historique complet.",
            self,
        )
        layout.addWidget(self.period_notice_label)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.summary_label = QLabel(self)
        layout.addWidget(self.summary_label)

        self._apply_default_period()

        self.refresh_button.clicked.connect(self.refresh)
        self.reset_button.clicked.connect(self._on_reset_filters_clicked)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

        self.refresh()

    # -- filtres -----------------------------------------------------------

    def _safe_list_entites(self) -> list[str]:
        try:
            return self._audit_service.list_entites()
        except AppError:
            return []

    def _apply_default_period(self) -> None:
        """Pré-remplit la période par défaut (30 derniers jours) — utilisé à
        la construction et par « Réinitialiser les filtres »."""
        today = date.today()
        self.date_from_edit.setText((today - timedelta(days=_DEFAULT_PERIOD_DAYS)).isoformat())
        self.date_to_edit.setText(today.isoformat())

    def _parse_optional_date(self, text: str, field_label: str) -> Optional[date]:
        text = (text or "").strip()
        if not text:
            return None
        return parse_date(text, field_label)

    def _on_reset_filters_clicked(self) -> None:
        self.search_edit.clear()
        self.entite_filter_combo.setCurrentIndex(0)
        self._apply_default_period()
        self.refresh()

    # -- rafraîchissement ----------------------------------------------------

    def refresh(self) -> None:
        try:
            date_from = self._parse_optional_date(self.date_from_edit.text(), "date de début")
            date_to = self._parse_optional_date(self.date_to_edit.text(), "date de fin")
        except AppError as exc:
            QMessageBox.warning(self, "Filtre invalide", str(exc))
            return

        try:
            audits = self._audit_service.list_audits(
                term=self.search_edit.text(),
                date_from=date_from,
                date_to=date_to,
                entite=self.entite_filter_combo.currentData(),
            )
        except AppError as exc:
            self._current_audits = []
            self.table.setRowCount(0)
            self.summary_label.setText("")
            QMessageBox.warning(self, "Journal d'audit indisponible", str(exc))
            return

        self._current_audits = audits
        self.table.setRowCount(len(audits))
        for row, audit in enumerate(audits):
            self.table.setItem(row, 0, QTableWidgetItem(audit.date_heure.strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 1, QTableWidgetItem(audit.username or "—"))
            self.table.setItem(row, 2, QTableWidgetItem(audit.action))
            self.table.setItem(row, 3, QTableWidgetItem(audit.entite))
            self.table.setItem(
                row, 4, QTableWidgetItem(str(audit.entite_id) if audit.entite_id is not None else "—")
            )
            self.table.setItem(row, 5, QTableWidgetItem(_RESULTAT_LABELS.get(audit.resultat, str(audit.resultat))))
            self.table.setItem(row, 6, QTableWidgetItem(audit.details or "—"))

        self.summary_label.setText(f"{len(audits)} entrée(s) d'audit")

    # -- détail ---------------------------------------------------------------

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._current_audits):
            return
        dialog = AuditDetailDialog(self._current_audits[row], parent=self)
        dialog.exec()
