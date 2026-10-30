"""Dialogue de gestion de la caution d'une location.

Deux usages selon l'état de la location (voir ``LocationService``) :
- avant le départ (BROUILLON/CONFIRMEE) : le montant de la caution peut
  encore être défini/modifié (``peut_modifier_montant=True``) ;
- après le départ (EN_COURS/RETOURNEE) : le montant est figé, seule une
  restitution/retenue peut être enregistrée (``peut_modifier_montant=False``),
  un simple enregistrement manuel cumulatif — jamais calculé automatiquement
  (décision métier explicite de ce lot).
"""
from __future__ import annotations

from decimal import Decimal

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
from app.views.common import build_required_field_legend, format_decimal_for_input, required_label


class LocationCautionDialog(QDialog):
    def __init__(
        self,
        caution_montant: Decimal,
        caution_rendue: Decimal,
        currency_code: str,
        peut_modifier_montant: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._peut_modifier_montant = peut_modifier_montant

        self.setWindowTitle("Caution")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        info_form = QFormLayout()
        info_form.addRow("Montant de la caution", QLabel(format_money(caution_montant, currency_code), self))
        info_form.addRow("Déjà restitué/retenu", QLabel(format_money(caution_rendue, currency_code), self))
        reste_label = QLabel(format_money(caution_montant - caution_rendue, currency_code), self)
        reste_label.setStyleSheet("font-weight: 600;")
        info_form.addRow("Reste à restituer", reste_label)
        layout.addLayout(info_form)

        form = QFormLayout()
        self.montant_edit = QLineEdit(self)
        if peut_modifier_montant:
            self.montant_edit.setText(format_decimal_for_input(caution_montant))
            form.addRow(required_label("Nouveau montant de la caution"), self.montant_edit)
        else:
            form.addRow(required_label("Montant à restituer/retenir"), self.montant_edit)
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
        self.save_button.setProperty("variant", "primary")
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def peut_modifier_montant(self) -> bool:
        return self._peut_modifier_montant

    def values(self) -> dict:
        return {"montant": self.montant_edit.text()}

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
