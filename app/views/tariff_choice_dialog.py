"""Dialogue partagé de choix du tarif (Mission 5, §2.4/§3.1) — réutilisé par
Ventes et Locations : même présentation des 3 tarifs possibles (Normal,
Sous-traitant, Autre), même règle de présélection (Normal par défaut), même
validation côté interface de l'intervalle « Autre » (la validation
réellement autoritaire reste côté service, voir
``app.utils.tariff_validation.validate_chosen_tariff`` — ce dialogue ne
fait qu'éviter un aller-retour inutile pour une erreur déjà prévisible).

Ne connaît rien du service métier : collecte uniquement un choix (type de
tarif + montant) et le restitue via ``values()`` — c'est l'appelant
(``SalesPage``/``LocationsPage``) qui construit la ligne avec ce choix.
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
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import TypeTarif
from app.utils.exceptions import ValidationError
from app.utils.money import format_money
from app.views.common import format_decimal_for_input, parse_decimal

_TYPE_LABELS_VENTE = {
    TypeTarif.NORMAL: "Prix normal",
    TypeTarif.SOUS_TRAITANT: "Prix sous-traitant",
    TypeTarif.AUTRE: "Autre prix",
}
_TYPE_LABELS_LOCATION = {
    TypeTarif.NORMAL: "Tarif normal",
    TypeTarif.SOUS_TRAITANT: "Tarif sous-traitant",
    TypeTarif.AUTRE: "Autre tarif",
}


class TariffChoiceDialog(QDialog):
    def __init__(
        self,
        article_label: str,
        prix_normal: Decimal,
        prix_sous_traitant: Optional[Decimal],
        intervalle_min: Optional[Decimal],
        intervalle_max: Optional[Decimal],
        currency_code: str,
        *,
        is_location: bool = False,
        initial_type: TypeTarif = TypeTarif.NORMAL,
        initial_montant: Optional[Decimal] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._prix_normal = prix_normal
        self._prix_sous_traitant = prix_sous_traitant
        self._intervalle_min = intervalle_min
        self._intervalle_max = intervalle_max
        self._currency_code = currency_code
        self._labels = _TYPE_LABELS_LOCATION if is_location else _TYPE_LABELS_VENTE
        self._noun = "tarif" if is_location else "prix"

        self.setWindowTitle(f"Choix du {self._noun}")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(article_label, self))

        # Mission 5, §2.4 : comportement par défaut, le tarif normal doit
        # être automatiquement sélectionné — sauf lors d'une re-sélection
        # sur une ligne déjà choisie (``initial_type`` reflète alors le
        # choix précédent de cette même ligne, jamais une réinitialisation
        # silencieuse).
        self.normal_radio = QRadioButton(
            f"{self._labels[TypeTarif.NORMAL]} ({format_money(prix_normal, currency_code)})", self
        )
        layout.addWidget(self.normal_radio)

        self.sous_traitant_radio = QRadioButton(self)
        if prix_sous_traitant is not None:
            self.sous_traitant_radio.setText(
                f"{self._labels[TypeTarif.SOUS_TRAITANT]} ({format_money(prix_sous_traitant, currency_code)})"
            )
        else:
            self.sous_traitant_radio.setText(f"{self._labels[TypeTarif.SOUS_TRAITANT]} (non configuré)")
            self.sous_traitant_radio.setEnabled(False)
        layout.addWidget(self.sous_traitant_radio)

        self.autre_radio = QRadioButton(self)
        interval_configured = intervalle_min is not None and intervalle_max is not None
        if interval_configured:
            self.autre_radio.setText(
                f"{self._labels[TypeTarif.AUTRE]} (entre {format_money(intervalle_min, currency_code)} "
                f"et {format_money(intervalle_max, currency_code)})"
            )
        else:
            self.autre_radio.setText(f"{self._labels[TypeTarif.AUTRE]} (aucun intervalle configuré)")
            self.autre_radio.setEnabled(False)
        layout.addWidget(self.autre_radio)

        autre_form = QFormLayout()
        self.autre_montant_edit = QLineEdit(self)
        self.autre_montant_edit.setEnabled(False)
        autre_form.addRow(f"Montant du « {self._labels[TypeTarif.AUTRE].lower()} »", self.autre_montant_edit)
        layout.addLayout(autre_form)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.ok_button = QPushButton("Valider", self)
        self.ok_button.setProperty("variant", "primary")
        self.ok_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.ok_button)
        layout.addLayout(button_row)

        self.normal_radio.toggled.connect(self._update_autre_field_state)
        self.sous_traitant_radio.toggled.connect(self._update_autre_field_state)
        self.autre_radio.toggled.connect(self._update_autre_field_state)
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self._on_ok_clicked)

        self._select_initial(initial_type, initial_montant, interval_configured)
        self._update_autre_field_state()

    def _select_initial(
        self, initial_type: TypeTarif, initial_montant: Optional[Decimal], interval_configured: bool
    ) -> None:
        if initial_type == TypeTarif.SOUS_TRAITANT and self._prix_sous_traitant is not None:
            self.sous_traitant_radio.setChecked(True)
        elif initial_type == TypeTarif.AUTRE and interval_configured:
            self.autre_radio.setChecked(True)
            if initial_montant is not None:
                self.autre_montant_edit.setText(format_decimal_for_input(initial_montant))
        else:
            self.normal_radio.setChecked(True)

    def _update_autre_field_state(self) -> None:
        self.autre_montant_edit.setEnabled(self.autre_radio.isChecked())

    def _on_ok_clicked(self) -> None:
        if self.autre_radio.isChecked():
            try:
                montant = parse_decimal(self.autre_montant_edit.text(), f"montant ({self._noun})")
            except ValidationError as exc:
                self.error_label.setText(str(exc))
                return
            if (
                self._intervalle_min is not None
                and self._intervalle_max is not None
                and not (self._intervalle_min <= montant <= self._intervalle_max)
            ):
                self.error_label.setText(
                    f"Le montant doit être compris entre {format_money(self._intervalle_min, self._currency_code)} "
                    f"et {format_money(self._intervalle_max, self._currency_code)}."
                )
                return
        self.accept()

    def values(self) -> tuple[TypeTarif, Decimal]:
        if self.sous_traitant_radio.isChecked():
            return TypeTarif.SOUS_TRAITANT, self._prix_sous_traitant
        if self.autre_radio.isChecked():
            return TypeTarif.AUTRE, parse_decimal(self.autre_montant_edit.text(), f"montant ({self._noun})")
        return TypeTarif.NORMAL, self._prix_normal
