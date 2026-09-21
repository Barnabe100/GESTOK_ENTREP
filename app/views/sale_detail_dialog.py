"""Consultation détaillée, en lecture seule, d'une vente — et génération de
son reçu (export PDF A4/ticket 80 mm, impression) pour les ventes validées.

Toute la construction du document (gabarit, taille de page) vit dans
``app.services.documents.receipt_document`` ; cette vue ne fait
qu'orchestrer l'appel à ``ReceiptService``/``build_receipt_document``/
``export_document_to_pdf`` et les dialogues Qt (sélection de fichier,
imprimante), comme le fait déjà chaque export existant (CSV, logo).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
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

from app.models.enums import StatutOperation, StatutPaiement
from app.services.auth.permission_service import PermissionService
from app.services.documents.receipt_document import (
    ReceiptFormat,
    build_payment_receipt_document,
    build_receipt_document,
)
from app.services.documents.receipt_service import ReceiptService
from app.services.sales.sale_service import SaleService, VenteSummary
from app.services.stock.movement_summary import MouvementSummary
from app.utils.exceptions import AppError
from app.utils.money import format_money
from app.utils.pdf_export import build_page_layout, export_document_to_pdf
from app.utils.quantity import format_quantity
from app.views.common import parse_decimal
from app.views.payment_form_dialog import PaymentFormDialog

_LINE_COLUMNS = ["Article", "Quantité", "Prix unitaire", "Montant"]
_MOVEMENT_COLUMNS = ["Date/heure", "Type", "Quantité", "Stock avant", "Stock après", "Utilisateur"]
_PAYMENT_COLUMNS = ["Date", "Montant", "Mode", "Référence", "Enregistré par"]

_STATUT_LABELS = {
    StatutOperation.BROUILLON: "Brouillon",
    StatutOperation.VALIDEE: "Validée",
    StatutOperation.ANNULEE: "Annulée",
}

_STATUT_PAIEMENT_LABELS = {
    StatutPaiement.NON_PAYEE: "Non payée",
    StatutPaiement.PARTIELLEMENT_PAYEE: "Partiellement payée",
    StatutPaiement.PAYEE: "Payée",
}

_FORMAT_LABELS = {
    ReceiptFormat.A4: "A4",
    ReceiptFormat.TICKET_80MM: "Ticket 80 mm",
}


class SaleDetailDialog(QDialog):
    def __init__(
        self,
        sale: VenteSummary,
        movements: list[MouvementSummary],
        currency_code: str,
        receipt_service: ReceiptService,
        permission_service: PermissionService,
        sale_service: Optional[SaleService] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sale_id = sale.id
        self._sale_numero = sale.numero
        self._currency_code = currency_code
        self._receipt_service = receipt_service
        self._permissions = permission_service
        self._sale_service = sale_service
        self._sale = sale
        self._payments: list = []

        self.setWindowTitle(f"Vente — {sale.numero}")
        self.setModal(True)
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Numéro", QLabel(sale.numero, self))
        form.addRow("Date", QLabel(str(sale.date), self))
        form.addRow("Client", QLabel(sale.client_nom or "—", self))
        form.addRow("Créée par", QLabel(sale.username, self))
        form.addRow("Statut", QLabel(_STATUT_LABELS.get(sale.statut, str(sale.statut)), self))
        if sale.statut == StatutOperation.ANNULEE:
            motif_label = QLabel(sale.annulation_motif or "—", self)
            motif_label.setWordWrap(True)
            form.addRow("Motif d'annulation", motif_label)
        form.addRow("Créée le", QLabel(sale.date_creation.strftime("%Y-%m-%d %H:%M"), self))
        form.addRow("Modifiée le", QLabel(sale.date_modification.strftime("%Y-%m-%d %H:%M"), self))

        layout.addLayout(form)

        layout.addWidget(QLabel("Lignes", self))
        lines_table = QTableWidget(len(sale.lignes), len(_LINE_COLUMNS), self)
        lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        lines_table.horizontalHeader().setStretchLastSection(True)
        lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, ligne in enumerate(sale.lignes):
            lines_table.setItem(row, 0, QTableWidgetItem(f"{ligne.article_reference} — {ligne.article_designation}"))
            lines_table.setItem(row, 1, QTableWidgetItem(format_quantity(ligne.quantite)))
            lines_table.setItem(row, 2, QTableWidgetItem(format_money(ligne.prix_unitaire, currency_code)))
            lines_table.setItem(row, 3, QTableWidgetItem(format_money(ligne.sous_total, currency_code)))
        layout.addWidget(lines_table)

        total_label = QLabel(f"Total : {format_money(sale.total, currency_code)}", self)
        total_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(total_label)

        # -- paiement (ventes à crédit et paiements partiels, §5) -----------------
        payment_form = QFormLayout()
        self.montant_paye_label = QLabel("", self)
        payment_form.addRow("Payé", self.montant_paye_label)
        self.reste_a_payer_label = QLabel("", self)
        self.reste_a_payer_label.setStyleSheet("font-weight: 600;")
        payment_form.addRow("Reste à payer", self.reste_a_payer_label)
        self.statut_paiement_label = QLabel("", self)
        payment_form.addRow("Statut de paiement", self.statut_paiement_label)
        layout.addLayout(payment_form)

        layout.addWidget(QLabel("Historique des paiements", self))
        self.payments_table = QTableWidget(0, len(_PAYMENT_COLUMNS), self)
        self.payments_table.setHorizontalHeaderLabels(_PAYMENT_COLUMNS)
        self.payments_table.horizontalHeader().setStretchLastSection(True)
        self.payments_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.payments_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.payments_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.payments_table)

        payment_button_row = QHBoxLayout()
        self.record_payment_button = QPushButton("Enregistrer un paiement", self)
        payment_button_row.addWidget(self.record_payment_button)
        self.export_payment_receipt_button = QPushButton("Reçu du paiement sélectionné (PDF)", self)
        payment_button_row.addWidget(self.export_payment_receipt_button)
        payment_button_row.addStretch(1)
        layout.addLayout(payment_button_row)

        self.record_payment_button.clicked.connect(self._on_record_payment_clicked)
        self.export_payment_receipt_button.clicked.connect(self._on_export_payment_receipt_clicked)

        self._refresh_payment_section()

        layout.addWidget(QLabel("Mouvements de stock générés", self))
        movements_table = QTableWidget(len(movements), len(_MOVEMENT_COLUMNS), self)
        movements_table.setHorizontalHeaderLabels(_MOVEMENT_COLUMNS)
        movements_table.horizontalHeader().setStretchLastSection(True)
        movements_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, mouvement in enumerate(movements):
            movements_table.setItem(row, 0, QTableWidgetItem(mouvement.date_heure.strftime("%Y-%m-%d %H:%M")))
            movements_table.setItem(row, 1, QTableWidgetItem(mouvement.type.value))
            movements_table.setItem(row, 2, QTableWidgetItem(format_quantity(mouvement.quantite)))
            movements_table.setItem(row, 3, QTableWidgetItem(format_quantity(mouvement.stock_avant)))
            movements_table.setItem(row, 4, QTableWidgetItem(format_quantity(mouvement.stock_apres)))
            movements_table.setItem(row, 5, QTableWidgetItem(mouvement.username))
        layout.addWidget(movements_table)

        # -- reçu : uniquement pour une vente validée (§4 de ce lot) --------------
        receipt_row = QHBoxLayout()
        can_view_receipt = sale.statut == StatutOperation.VALIDEE and self._permissions.has_permission("SALE_VIEW")

        self.receipt_format_combo = QComboBox(self)
        for receipt_format, label in _FORMAT_LABELS.items():
            self.receipt_format_combo.addItem(label, receipt_format)
        self.receipt_format_combo.setEnabled(can_view_receipt)
        receipt_row.addWidget(self.receipt_format_combo)

        self.print_receipt_button = QPushButton("Imprimer le reçu", self)
        self.print_receipt_button.setEnabled(can_view_receipt)
        receipt_row.addWidget(self.print_receipt_button)

        self.export_a4_button = QPushButton("Exporter en PDF (A4)", self)
        self.export_a4_button.setEnabled(can_view_receipt)
        receipt_row.addWidget(self.export_a4_button)

        self.export_ticket_button = QPushButton("Exporter en PDF (Ticket 80 mm)", self)
        self.export_ticket_button.setEnabled(can_view_receipt)
        receipt_row.addWidget(self.export_ticket_button)

        receipt_row.addStretch(1)
        layout.addLayout(receipt_row)

        self.print_receipt_button.clicked.connect(self._on_print_clicked)
        self.export_a4_button.clicked.connect(self._on_export_a4_clicked)
        self.export_ticket_button.clicked.connect(self._on_export_ticket_clicked)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)

    # -- export PDF ----------------------------------------------------------------

    def _on_export_a4_clicked(self) -> None:
        self._prompt_and_export(ReceiptFormat.A4, "recu_A4")

    def _on_export_ticket_clicked(self) -> None:
        self._prompt_and_export(ReceiptFormat.TICKET_80MM, "recu_ticket_80mm")

    def _prompt_and_export(self, receipt_format: ReceiptFormat, filename_prefix: str) -> None:
        suggested = f"{filename_prefix}_{self._sale_numero}.pdf"
        file_path, _filter = QFileDialog.getSaveFileName(self, "Exporter le reçu en PDF", suggested, "PDF (*.pdf)")
        if not file_path:
            return
        self._export_receipt_to(file_path, receipt_format)

    def _export_receipt_to(self, file_path: str, receipt_format: ReceiptFormat) -> bool:
        """Isolé de ``_prompt_and_export`` pour rester testable sans
        dialogue modal de sélection de fichier."""
        try:
            data = self._receipt_service.build_sale_receipt(self._sale_id)
            rendered = build_receipt_document(data, receipt_format)
            export_document_to_pdf(rendered.document, file_path, rendered.page_size, rendered.margin_mm)
        except AppError as exc:
            QMessageBox.warning(self, "Export refusé", str(exc))
            return False
        QMessageBox.information(self, "Reçu exporté", "Le reçu a été exporté en PDF avec succès.")
        return True

    # -- impression ------------------------------------------------------------------

    def _on_print_clicked(self) -> None:
        receipt_format = self.receipt_format_combo.currentData()
        self._print_receipt(receipt_format)

    def _print_receipt(self, receipt_format: ReceiptFormat) -> bool:
        """Isolé de ``_on_print_clicked`` pour rester testable sans
        dialogue modal d'impression."""
        try:
            data = self._receipt_service.build_sale_receipt(self._sale_id)
        except AppError as exc:
            QMessageBox.warning(self, "Reçu indisponible", str(exc))
            return False

        if not QPrinterInfo.availablePrinters():
            QMessageBox.warning(
                self, "Aucune imprimante disponible",
                "Aucune imprimante n'est installée ou disponible sur ce poste. "
                "Vous pouvez exporter le reçu en PDF à la place.",
            )
            return False

        rendered = build_receipt_document(data, receipt_format)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageLayout(build_page_layout(rendered.page_size, rendered.margin_mm))

        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        rendered.document.print_(printer)
        return True

    # -- paiement (ventes à crédit et paiements partiels, §5) -------------------------

    def _refresh_payment_section(self) -> None:
        """Recharge le total payé/reste/statut et l'historique des
        paiements depuis le service — appelé à l'ouverture puis après tout
        enregistrement de paiement réussi (jamais de mise à jour manuelle
        des libellés : toujours relu depuis la source de vérité)."""
        sale = self._sale
        if self._sale_service is not None:
            try:
                sale = self._sale_service.get_sale(self._sale_id)
                self._sale = sale
                self._payments = self._sale_service.list_payments(self._sale_id)
            except AppError:
                self._payments = []
        else:
            self._payments = []

        self.montant_paye_label.setText(format_money(sale.montant_paye, self._currency_code))
        self.reste_a_payer_label.setText(format_money(sale.reste_a_payer, self._currency_code))
        self.statut_paiement_label.setText(
            _STATUT_PAIEMENT_LABELS.get(sale.statut_paiement, str(sale.statut_paiement))
        )

        self.payments_table.setRowCount(len(self._payments))
        for row, paiement in enumerate(self._payments):
            payment_id_item = QTableWidgetItem(paiement.date_heure.strftime("%Y-%m-%d %H:%M"))
            payment_id_item.setData(Qt.ItemDataRole.UserRole, paiement.id)
            self.payments_table.setItem(row, 0, payment_id_item)
            self.payments_table.setItem(row, 1, QTableWidgetItem(format_money(paiement.montant, self._currency_code)))
            self.payments_table.setItem(row, 2, QTableWidgetItem(paiement.mode_paiement or "—"))
            self.payments_table.setItem(row, 3, QTableWidgetItem(paiement.reference or "—"))
            self.payments_table.setItem(row, 4, QTableWidgetItem(paiement.username))

        can_pay = (
            self._sale_service is not None
            and sale.statut == StatutOperation.VALIDEE
            and sale.reste_a_payer > 0
            and self._permissions.has_permission("SALE_PAYMENT_CREATE")
        )
        self.record_payment_button.setEnabled(can_pay)
        self.export_payment_receipt_button.setEnabled(len(self._payments) > 0)

    def _on_record_payment_clicked(self) -> None:
        if self._sale_service is None:
            return
        dialog = PaymentFormDialog(
            self._sale.total, self._sale.montant_paye, self._sale.reste_a_payer, self._currency_code, parent=self
        )
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if self._submit_payment(dialog.values()):
                return
            dialog.exec()

    def _submit_payment(self, values: dict) -> bool:
        """Isolé de ``_on_record_payment_clicked`` pour rester testable sans
        dialogue modal."""
        try:
            montant = parse_decimal(values["montant"], "montant du paiement")
            self._sale_service.record_payment(
                self._sale_id, montant,
                mode_paiement=values.get("mode_paiement"),
                reference=values.get("reference"),
                commentaire=values.get("commentaire"),
            )
        except AppError as exc:
            QMessageBox.warning(self, "Paiement refusé", str(exc))
            return False
        QMessageBox.information(self, "Paiement enregistré", "Le paiement a été enregistré avec succès.")
        self._refresh_payment_section()
        return True

    def _on_export_payment_receipt_clicked(self) -> None:
        selected = self.payments_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "Aucune sélection", "Sélectionnez d'abord un paiement dans l'historique.")
            return
        paiement_id = self.payments_table.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        suggested = f"recu_paiement_{self._sale_numero}_{paiement_id}.pdf"
        file_path, _filter = QFileDialog.getSaveFileName(
            self, "Exporter le reçu de paiement en PDF", suggested, "PDF (*.pdf)"
        )
        if not file_path:
            return
        self._export_payment_receipt_to(file_path, paiement_id)

    def _export_payment_receipt_to(self, file_path: str, paiement_id: int) -> bool:
        """Isolé de ``_on_export_payment_receipt_clicked`` pour rester
        testable sans dialogue modal de sélection de fichier."""
        try:
            data = self._receipt_service.build_payment_receipt(self._sale_id, paiement_id)
            rendered = build_payment_receipt_document(data)
            export_document_to_pdf(rendered.document, file_path, rendered.page_size, rendered.margin_mm)
        except AppError as exc:
            QMessageBox.warning(self, "Export refusé", str(exc))
            return False
        QMessageBox.information(self, "Reçu exporté", "Le reçu de paiement a été exporté en PDF avec succès.")
        return True
