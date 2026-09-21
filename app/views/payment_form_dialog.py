"""Formulaire (dialogue modal) d'enregistrement d'un paiement sur une vente
déjà validée (§5.5 : « Enregistrer un paiement »).

Affiche le total, le montant déjà payé et le reste à payer en lecture seule
avant la saisie — la validation du montant (positif, ne dépassant pas le
reste) reste de la responsabilité de ``SaleService.record_payment``, jamais
dupliquée ici.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.money import format_money
from app.views.common import build_required_field_legend, required_label


class PaymentFormDialog(QDialog):
    def __init__(
        self,
        total: Decimal,
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
        info_form.addRow("Total de la vente", QLabel(format_money(total, currency_code), self))
        info_form.addRow("Déjà payé", QLabel(format_money(montant_paye, currency_code), self))
        reste_label = QLabel(format_money(reste_a_payer, currency_code), self)
        reste_label.setStyleSheet("font-weight: 600;")
        info_form.addRow("Reste à payer", reste_label)
        layout.addLayout(info_form)

        form = QFormLayout()
        self.montant_edit = QLineEdit(self)
        self.montant_edit.setPlaceholderText(str(reste_a_payer))
        form.addRow(required_label("Montant du paiement"), self.montant_edit)

        self.mode_paiement_edit = QLineEdit(self)
        self.mode_paiement_edit.setPlaceholderText("Espèces, Mobile Money, Virement…")
        form.addRow("Mode de paiement", self.mode_paiement_edit)

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
            "mode_paiement": self.mode_paiement_edit.text().strip() or None,
            "reference": self.reference_edit.text().strip() or None,
            "commentaire": self.commentaire_edit.text().strip() or None,
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
