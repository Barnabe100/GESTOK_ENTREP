"""Formulaire (dialogue modal) d'enregistrement d'un retour (total ou
partiel) sur une ligne de location en cours.

Affiche la quantité encore en location en lecture seule avant la saisie —
la validation (quantités, dépassement) reste de la responsabilité de
``LocationService.return_location_line``, jamais dupliquée ici.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.quantity import format_quantity
from app.views.common import build_required_field_legend, date_to_qdate, required_label


class LocationReturnFormDialog(QDialog):
    def __init__(
        self,
        lignes: list[tuple[int, str, Decimal]],
        parent: QWidget | None = None,
    ) -> None:
        """``lignes`` : liste de tuples (location_ligne_id, libellé affiché,
        quantité encore en location) — lignes avec ``qte_en_location > 0``
        uniquement, filtrées par l'appelant."""
        super().__init__(parent)
        self._lignes = lignes

        self.setWindowTitle("Enregistrer un retour")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ligne_combo = QComboBox(self)
        for ligne_id, label, qte_en_location in lignes:
            self.ligne_combo.addItem(label, (ligne_id, qte_en_location))
        form.addRow(required_label("Ligne"), self.ligne_combo)

        self.qte_en_location_label = QLabel("", self)
        form.addRow("Quantité encore en location", self.qte_en_location_label)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setDate(date_to_qdate(date.today()))
        form.addRow(required_label("Date de retour"), self.date_edit)

        self.quantite_bon_etat_edit = QLineEdit(self)
        self.quantite_bon_etat_edit.setText("0")
        form.addRow("Quantité en bon état", self.quantite_bon_etat_edit)

        self.quantite_immobilisee_edit = QLineEdit(self)
        self.quantite_immobilisee_edit.setText("0")
        form.addRow("Quantité immobilisée (non remise en stock)", self.quantite_immobilisee_edit)

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
        self.save_button = QPushButton("Enregistrer le retour", self)
        self.save_button.setProperty("variant", "primary")
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        self.ligne_combo.currentIndexChanged.connect(self._on_ligne_changed)

        if lignes:
            self._on_ligne_changed(0)

    def _on_ligne_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self.ligne_combo.itemData(index)
        if data is None:
            return
        _ligne_id, qte_en_location = data
        self.qte_en_location_label.setText(format_quantity(qte_en_location))

    def values(self) -> dict:
        data = self.ligne_combo.currentData()
        return {
            "location_ligne_id": data[0] if data else None,
            "date_retour": self.date_edit.date().toPython(),
            "quantite_bon_etat": self.quantite_bon_etat_edit.text(),
            "quantite_immobilisee": self.quantite_immobilisee_edit.text(),
            "commentaire": self.commentaire_edit.text().strip() or None,
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
