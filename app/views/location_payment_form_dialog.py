"""Formulaire (dialogue modal) d'enregistrement d'un paiement sur une
location déjà partie (voir ``LocationService.record_payment``).

Affiche le montant total facturé, le montant déjà payé et le reste à payer
en lecture seule avant la saisie — la validation du montant (positif, ne
dépassant pas le reste) reste de la responsabilité du service, jamais
dupliquée ici. Même structure que ``PaymentFormDialog`` (Ventes), mais
jamais le même journal de paiements (voir ``LocationPaiement``, distinct
de ``Paiement``)."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.payment_mode import MODES_PAIEMENT
from app.utils.money import format_money
from app.views.common import build_required_field_legend, format_decimal_for_input, required_label

_MODE_PAIEMENT_NON_PRECISE = "(Non précisé)"


class LocationPaymentFormDialog(QDialog):
    def __init__(
        self,
        montant_total_facture: Decimal,
        montant_paye: Decimal,
        reste_a_payer: Decimal,
        currency_code: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Enregistrer un paiement")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        info_form = QFormLayout()
        info_form.addRow("Total facturé", QLabel(format_money(montant_total_facture, currency_code), self))
        info_form.addRow("Déjà payé", QLabel(format_money(montant_paye, currency_code), self))
        reste_label = QLabel(format_money(reste_a_payer, currency_code), self)
        reste_label.setStyleSheet("font-weight: 600;")
        info_form.addRow("Reste à payer", reste_label)
        layout.addLayout(info_form)

        form = QFormLayout()
        self.montant_edit = QLineEdit(self)
        self.montant_edit.setPlaceholderText(format_decimal_for_input(reste_a_payer))
        form.addRow(required_label("Montant du paiement"), self.montant_edit)

        # Évolution E : même liste fermée que Ventes (voir
        # app.models.payment_mode et le commentaire équivalent dans
        # PaymentFormDialog) — source de référence partagée entre les deux
        # modules.
        self.mode_paiement_combo = QComboBox(self)
        self.mode_paiement_combo.addItem(_MODE_PAIEMENT_NON_PRECISE, None)
        for mode in MODES_PAIEMENT:
            self.mode_paiement_combo.addItem(mode, mode)
        form.addRow("Mode de paiement", self.mode_paiement_combo)

        self.reference_edit = QLineEdit(self)
        form.addRow("Référence", self.reference_edit)

        self.commentaire_edit = QLineEdit(self)
        form.addRow("Commentaire", self.commentaire_edit)
        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Enregistrer", self)
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def values(self) -> dict:
        return {
            "montant": self.montant_edit.text(),
            "mode_paiement": self.mode_paiement_combo.currentData(),
            "reference": self.reference_edit.text().strip() or None,
            "commentaire": self.commentaire_edit.text().strip() or None,
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
