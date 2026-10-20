"""Consultation détaillée d'une location et actions de cycle de vie
(confirmation, départ, retour, annulation, caution, paiement).

Chaque action revérifie sa permission côté service
(:class:`LocationService`) : les boutons désactivés ici ne sont qu'un
confort d'interface, jamais ce qui empêche un contournement.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import StatutLocation
from app.services.auth.permission_service import PermissionService
from app.services.rentals.location_service import LocationService, LocationSummary
from app.utils.exceptions import AppError
from app.utils.money import format_money
from app.utils.quantity import format_quantity
from app.views.cancellation_reason_dialog import CancellationReasonDialog
from app.views.common import build_required_field_legend, parse_decimal, required_label
from app.views.location_caution_dialog import LocationCautionDialog
from app.views.location_payment_form_dialog import LocationPaymentFormDialog
from app.views.location_return_form_dialog import LocationReturnFormDialog

_LINE_COLUMNS = [
    "Article", "Qté prévue", "Qté réservée", "Qté en location", "Qté immobilisée", "Tarif / jour", "Facturé",
]
_RETOUR_COLUMNS = ["Date", "Ligne", "Qté bon état", "Qté immobilisée", "Montant facturé", "Enregistré par"]
_PAYMENT_COLUMNS = ["Date", "Montant", "Mode", "Référence", "Enregistré par"]

_STATUT_LABELS = {
    StatutLocation.BROUILLON: "Brouillon",
    StatutLocation.CONFIRMEE: "Confirmée",
    StatutLocation.EN_COURS: "En cours",
    StatutLocation.RETOURNEE: "Retournée",
    StatutLocation.ANNULEE: "Annulée",
}


class _DepartDateDialog(QDialog):
    """Dialogue minimal (une seule date) pour enregistrer le départ —
    jamais réutilisé ailleurs, inutile d'en faire un fichier séparé."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Enregistrer le départ")
        self.setModal(True)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setDate(QDate.currentDate())
        form.addRow(required_label("Date de départ"), self.date_edit)
        layout.addLayout(form)
        layout.addWidget(build_required_field_legend(self))
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_button = QPushButton("Annuler", self)
        save_button = QPushButton("Confirmer le départ", self)
        save_button.setDefault(True)
        button_row.addWidget(cancel_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)
        cancel_button.clicked.connect(self.reject)
        save_button.clicked.connect(self.accept)

    def date_depart(self) -> date:
        return self.date_edit.date().toPython()


class LocationDetailDialog(QDialog):
    def __init__(
        self,
        location: LocationSummary,
        currency_code: str,
        location_service: LocationService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self._location_id = location.id
        self._currency_code = currency_code
        self._location_service = location_service
        self._permissions = permission_service
        self._location = location
        # Lot 16 : accès de consultation explicite conservé quand le module
        # Location est désactivé — jamais de permission contournée, juste
        # aucune action mutante proposée (voir _update_action_buttons).
        self._read_only = read_only

        self.setWindowTitle(f"Location — {location.numero}")
        self.setModal(True)
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)

        self._header_form = QFormLayout()
        layout.addLayout(self._header_form)

        layout.addWidget(QLabel("Lignes", self))
        self.lines_table = QTableWidget(0, len(_LINE_COLUMNS), self)
        self.lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.lines_table)

        layout.addWidget(QLabel("Historique des retours", self))
        self.retours_table = QTableWidget(0, len(_RETOUR_COLUMNS), self)
        self.retours_table.setHorizontalHeaderLabels(_RETOUR_COLUMNS)
        self.retours_table.horizontalHeader().setStretchLastSection(True)
        self.retours_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.retours_table)

        self._payment_form = QFormLayout()
        layout.addLayout(self._payment_form)

        layout.addWidget(QLabel("Historique des paiements", self))
        self.payments_table = QTableWidget(0, len(_PAYMENT_COLUMNS), self)
        self.payments_table.setHorizontalHeaderLabels(_PAYMENT_COLUMNS)
        self.payments_table.horizontalHeader().setStretchLastSection(True)
        self.payments_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.payments_table)

        self._caution_form = QFormLayout()
        layout.addLayout(self._caution_form)

        action_row = QHBoxLayout()
        self.confirm_button = QPushButton("Confirmer", self)
        self.depart_button = QPushButton("Enregistrer le départ", self)
        self.return_button = QPushButton("Enregistrer un retour", self)
        self.cancel_location_button = QPushButton("Annuler la location", self)
        self.caution_button = QPushButton("Caution…", self)
        self.payment_button = QPushButton("Paiement…", self)
        for button in (
            self.confirm_button, self.depart_button, self.return_button,
            self.cancel_location_button, self.caution_button, self.payment_button,
        ):
            action_row.addWidget(button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.confirm_button.clicked.connect(self._on_confirm_clicked)
        self.depart_button.clicked.connect(self._on_depart_clicked)
        self.return_button.clicked.connect(self._on_return_clicked)
        self.cancel_location_button.clicked.connect(self._on_cancel_clicked)
        self.caution_button.clicked.connect(self._on_caution_clicked)
        self.payment_button.clicked.connect(self._on_payment_clicked)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

        self._refresh()

    # -- rafraîchissement -------------------------------------------------------------

    def _refresh(self) -> None:
        try:
            self._location = self._location_service.get_location(self._location_id)
        except AppError:
            pass
        location = self._location

        self._clear_form(self._header_form)
        self._header_form.addRow("Numéro", QLabel(location.numero, self))
        self._header_form.addRow("Date", QLabel(str(location.date), self))
        self._header_form.addRow("Client", QLabel(location.client_nom or "Client non renseigné", self))
        self._header_form.addRow("Créée par", QLabel(location.username, self))
        self._header_form.addRow("Statut", QLabel(_STATUT_LABELS.get(location.statut, str(location.statut)), self))
        if location.date_depart is not None:
            self._header_form.addRow("Date de départ", QLabel(str(location.date_depart), self))
        if location.statut == StatutLocation.ANNULEE:
            motif_label = QLabel(location.annulation_motif or "—", self)
            motif_label.setWordWrap(True)
            self._header_form.addRow("Motif d'annulation", motif_label)
        if location.commentaire:
            commentaire_label = QLabel(location.commentaire, self)
            commentaire_label.setWordWrap(True)
            self._header_form.addRow("Commentaire", commentaire_label)
        self._header_form.addRow("Créée le", QLabel(location.date_creation.strftime("%Y-%m-%d %H:%M"), self))

        self.lines_table.setRowCount(len(location.lignes))
        for row, ligne in enumerate(location.lignes):
            self.lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            self.lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(ligne.qte_prevue)))
            self.lines_table.setItem(row, 2, QTableWidgetItem(format_quantity(ligne.qte_reservee)))
            self.lines_table.setItem(row, 3, QTableWidgetItem(format_quantity(ligne.qte_en_location)))
            self.lines_table.setItem(row, 4, QTableWidgetItem(format_quantity(ligne.qte_immobilisee)))
            self.lines_table.setItem(row, 5, QTableWidgetItem(format_money(ligne.tarif_jour, self._currency_code)))
            self.lines_table.setItem(
                row, 6, QTableWidgetItem(format_money(ligne.montant_facture_total, self._currency_code))
            )

        retours = [(ligne, retour) for ligne in location.lignes for retour in ligne.retours]
        retours.sort(key=lambda pair: pair[1].date_heure)
        self.retours_table.setRowCount(len(retours))
        for row, (ligne, retour) in enumerate(retours):
            self.retours_table.setItem(row, 0, QTableWidgetItem(str(retour.date_retour)))
            self.retours_table.setItem(row, 1, QTableWidgetItem(ligne.article_reference))
            self.retours_table.setItem(row, 2, QTableWidgetItem(format_quantity(retour.quantite_bon_etat)))
            self.retours_table.setItem(row, 3, QTableWidgetItem(format_quantity(retour.quantite_immobilisee)))
            self.retours_table.setItem(row, 4, QTableWidgetItem(format_money(retour.montant_facture, self._currency_code)))
            self.retours_table.setItem(row, 5, QTableWidgetItem(retour.username))

        self._clear_form(self._payment_form)
        self._payment_form.addRow(
            "Total facturé", QLabel(format_money(location.montant_total_facture, self._currency_code), self)
        )
        self._payment_form.addRow("Payé", QLabel(format_money(location.montant_paye, self._currency_code), self))
        reste_label = QLabel(format_money(location.reste_a_payer, self._currency_code), self)
        reste_label.setStyleSheet("font-weight: 600;")
        self._payment_form.addRow("Reste à payer", reste_label)

        self.payments_table.setRowCount(len(location.paiements))
        for row, paiement in enumerate(location.paiements):
            self.payments_table.setItem(row, 0, QTableWidgetItem(paiement.date_heure.strftime("%Y-%m-%d %H:%M")))
            self.payments_table.setItem(row, 1, QTableWidgetItem(format_money(paiement.montant, self._currency_code)))
            self.payments_table.setItem(row, 2, QTableWidgetItem(paiement.mode_paiement or "—"))
            self.payments_table.setItem(row, 3, QTableWidgetItem(paiement.reference or "—"))
            self.payments_table.setItem(row, 4, QTableWidgetItem(paiement.username))

        self._clear_form(self._caution_form)
        self._caution_form.addRow(
            "Caution", QLabel(format_money(location.caution_montant, self._currency_code), self)
        )
        self._caution_form.addRow(
            "Restituée/retenue", QLabel(format_money(location.caution_rendue, self._currency_code), self)
        )

        self._update_action_buttons()

    @staticmethod
    def _clear_form(form: QFormLayout) -> None:
        while form.rowCount() > 0:
            form.removeRow(0)

    def _update_action_buttons(self) -> None:
        if self._read_only:
            # Lot 16 : aucune action mutante depuis le chemin de consultation
            # en lecture seule, quelle que soit la permission de l'utilisateur
            # — la règle réelle reste entièrement dans LocationService.
            for button in (
                self.confirm_button, self.depart_button, self.return_button,
                self.cancel_location_button, self.caution_button, self.payment_button,
            ):
                button.setEnabled(False)
            return
        statut = self._location.statut
        self.confirm_button.setEnabled(
            statut == StatutLocation.BROUILLON and self._permissions.has_permission("LOCATION_CONFIRM")
        )
        self.depart_button.setEnabled(
            statut == StatutLocation.CONFIRMEE and self._permissions.has_permission("LOCATION_DEPART")
        )
        self.return_button.setEnabled(
            statut == StatutLocation.EN_COURS and self._permissions.has_permission("LOCATION_RETURN")
        )
        self.cancel_location_button.setEnabled(
            statut in (StatutLocation.BROUILLON, StatutLocation.CONFIRMEE)
            and self._permissions.has_permission("LOCATION_CANCEL")
        )
        # Lot 17 : désactivés dès que le solde/la caution restante atteint
        # zéro — « reste_a_payer » est la propriété déjà exposée par
        # LocationSummary (jamais recalculée ici) ; la caution restante
        # n'a pas d'équivalent exposé, donc calculée directement à partir
        # des deux champs bruts déjà disponibles sur ``location``, sans
        # toucher à LocationService (le service revérifie de toute façon
        # ces deux limites à chaque appel, voir record_payment/
        # record_caution_return — ces conditions ne sont qu'un confort
        # d'affichage anticipant un refus déjà certain).
        caution_restante = self._location.caution_montant - self._location.caution_rendue
        self.caution_button.setEnabled(
            caution_restante > 0 and self._permissions.has_permission("LOCATION_CAUTION_MANAGE")
        )
        self.payment_button.setEnabled(
            statut in (StatutLocation.EN_COURS, StatutLocation.RETOURNEE)
            and self._location.reste_a_payer > 0
            and self._permissions.has_permission("LOCATION_PAYMENT_CREATE")
        )

    # -- confirmation -----------------------------------------------------------------

    def _on_confirm_clicked(self) -> None:
        if self._confirm():
            self._refresh()

    def _confirm(self) -> bool:
        """Isolé de ``_on_confirm_clicked`` pour rester testable sans boîte modale."""
        try:
            self._location_service.confirm_location(self._location_id)
            QMessageBox.information(self, "Location confirmée", "La location a été confirmée.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- départ -----------------------------------------------------------------------

    def _on_depart_clicked(self) -> None:
        dialog = _DepartDateDialog(parent=self)
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self._depart(dialog.date_depart()):
                self._refresh()
                return

    def _depart(self, date_depart: date) -> bool:
        """Isolé de ``_on_depart_clicked`` pour rester testable sans dialogue modal."""
        try:
            self._location_service.depart_location(self._location_id, date_depart)
            QMessageBox.information(self, "Départ enregistré", "Le départ de la location a été enregistré.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- retour -----------------------------------------------------------------------

    def _on_return_clicked(self) -> None:
        lignes = [
            (ligne.id, f"{ligne.article_reference} — {ligne.article_designation}", ligne.qte_en_location)
            for ligne in self._location.lignes
            if ligne.qte_en_location > 0
        ]
        if not lignes:
            QMessageBox.information(self, "Retour", "Aucune ligne n'est encore en location.")
            return
        dialog = LocationReturnFormDialog(lignes, parent=self)
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self._submit_return(dialog.values()):
                self._refresh()
                return

    def _submit_return(self, values: dict) -> bool:
        """Isolé de ``_on_return_clicked`` pour rester testable sans dialogue modal."""
        try:
            quantite_bon_etat = parse_decimal(values["quantite_bon_etat"], "quantité en bon état")
            quantite_immobilisee = parse_decimal(values["quantite_immobilisee"], "quantité immobilisée")
            self._location_service.return_location_line(
                self._location_id,
                values["location_ligne_id"],
                values["date_retour"],
                quantite_bon_etat=quantite_bon_etat,
                quantite_immobilisee=quantite_immobilisee,
                commentaire=values.get("commentaire"),
            )
            QMessageBox.information(self, "Retour enregistré", "Le retour a été enregistré avec succès.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- annulation ---------------------------------------------------------------------

    def _on_cancel_clicked(self) -> None:
        dialog = CancellationReasonDialog("cette location", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self._cancel(dialog.reason()):
            self._refresh()

    def _cancel(self, motif: str) -> bool:
        """Isolé de ``_on_cancel_clicked`` pour rester testable sans boîte modale."""
        try:
            self._location_service.cancel_location(self._location_id, motif)
            QMessageBox.information(self, "Location annulée", "La location a été annulée.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- caution --------------------------------------------------------------------------

    def _on_caution_clicked(self) -> None:
        location = self._location
        peut_modifier_montant = location.statut in (StatutLocation.BROUILLON, StatutLocation.CONFIRMEE)
        dialog = LocationCautionDialog(
            location.caution_montant, location.caution_rendue, self._currency_code,
            peut_modifier_montant, parent=self,
        )
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self._submit_caution(dialog.values(), peut_modifier_montant):
                self._refresh()
                return

    def _submit_caution(self, values: dict, peut_modifier_montant: bool) -> bool:
        """Isolé de ``_on_caution_clicked`` pour rester testable sans dialogue modal."""
        try:
            montant = parse_decimal(values["montant"], "montant")
            if peut_modifier_montant:
                self._location_service.set_caution_montant(self._location_id, montant)
                QMessageBox.information(self, "Caution définie", "Le montant de la caution a été défini.")
            else:
                self._location_service.record_caution_return(self._location_id, montant)
                QMessageBox.information(self, "Caution enregistrée", "La restitution/retenue a été enregistrée.")
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- paiements --------------------------------------------------------------------

    def _on_payment_clicked(self) -> None:
        location = self._location
        dialog = LocationPaymentFormDialog(
            location.montant_total_facture, location.montant_paye, location.reste_a_payer,
            self._currency_code, parent=self,
        )
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self._submit_payment(dialog.values()):
                self._refresh()
                return

    def _submit_payment(self, values: dict) -> bool:
        """Isolé de ``_on_payment_clicked`` pour rester testable sans dialogue modal."""
        try:
            montant = parse_decimal(values["montant"], "montant du paiement")
            self._location_service.record_payment(
                self._location_id, montant,
                mode_paiement=values.get("mode_paiement"),
                reference=values.get("reference"),
                commentaire=values.get("commentaire"),
            )
            QMessageBox.information(self, "Paiement enregistré", "Le paiement a été enregistré avec succès.")
        except AppError as exc:
            QMessageBox.warning(self, "Paiement refusé", str(exc))
            return False
        return True
