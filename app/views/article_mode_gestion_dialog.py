"""Dialogue de bascule du mode de gestion d'un article (VENTE <-> LOCATION,
module Locations, lot dédié).

Action volontairement séparée du formulaire d'édition habituel
(``ArticleFormDialog``) : chaque changement est audité et historisé
(``ArticleModeGestionChangement`` via ``ArticleService.switch_mode_gestion``),
jamais un simple champ parmi d'autres.

Lot « Gestion du mode Vente / Location » : contrairement au formulaire de
création/modification (qui exige désormais un tarif journalier strictement
positif avant d'appliquer une bascule vers Location), ce dialogue reste
volontairement inchangé dans son comportement — ``switch_mode_gestion``
autorise toujours une bascule vers Location sans aucun tarif renseigné
(règle métier existante, voir ``ArticleService``, conservée pour ne pas
casser les parcours qui en dépendent). Un simple avertissement informatif,
sans aucun effet bloquant, signale ce cas avant confirmation.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import ModeGestionArticle

_MODE_LABELS = {
    ModeGestionArticle.VENTE: "Vente",
    ModeGestionArticle.LOCATION: "Location",
}


class ArticleModeGestionDialog(QDialog):
    def __init__(
        self,
        article_reference: str,
        mode_actuel: ModeGestionArticle,
        tarif_location_jour: Optional[Decimal] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tarif_location_jour = tarif_location_jour
        self.setWindowTitle("Mode de gestion")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Article", QLabel(article_reference, self))
        form.addRow("Mode actuel", QLabel(_MODE_LABELS.get(mode_actuel, str(mode_actuel)), self))

        self.mode_combo = QComboBox(self)
        for mode, label in _MODE_LABELS.items():
            self.mode_combo.addItem(label, mode)
        autre_mode = (
            ModeGestionArticle.LOCATION if mode_actuel == ModeGestionArticle.VENTE else ModeGestionArticle.VENTE
        )
        index = self.mode_combo.findData(autre_mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        form.addRow("Nouveau mode", self.mode_combo)
        layout.addLayout(form)

        self.tarif_warning_label = QLabel("", self)
        self.tarif_warning_label.setStyleSheet("color: #B45309;")
        self.tarif_warning_label.setWordWrap(True)
        layout.addWidget(self.tarif_warning_label)
        self.mode_combo.currentIndexChanged.connect(self._update_tarif_warning)
        self._update_tarif_warning()

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Confirmer la bascule", self)
        self.save_button.setProperty("variant", "primary")
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def _update_tarif_warning(self) -> None:
        """Avertissement purement informatif (jamais bloquant) : signale
        qu'une bascule vers Location sans tarif catalogue reste autorisée
        ici, mais que l'article ne pourra être proposé dans une location
        tant qu'un tarif n'aura pas été renseigné (modifiable depuis sa
        fiche) — voir la docstring du module."""
        cible_location = self.mode_combo.currentData() == ModeGestionArticle.LOCATION
        sans_tarif = self._tarif_location_jour is None or self._tarif_location_jour <= 0
        if cible_location and sans_tarif:
            self.tarif_warning_label.setText(
                "Aucun tarif de location journalier n'est actuellement défini pour cet article. "
                "La bascule reste autorisée, mais l'article ne pourra pas être proposé dans une "
                "location tant qu'un tarif n'aura pas été renseigné depuis sa fiche."
            )
        else:
            self.tarif_warning_label.setText("")

    def nouveau_mode(self) -> ModeGestionArticle:
        # Correctif (incident « mode de gestion ») : voir le commentaire
        # équivalent dans ``app/views/article_form_dialog.py::values`` —
        # ``QComboBox.currentData()`` restitue un ``str`` nu, jamais le
        # membre ``ModeGestionArticle`` réellement passé à ``addItem``, pour
        # une énumération dérivant de ``str``. Reconstruit ici le membre
        # d'énumération pour que cette méthode retourne réellement le type
        # qu'elle déclare.
        return ModeGestionArticle(self.mode_combo.currentData())

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
