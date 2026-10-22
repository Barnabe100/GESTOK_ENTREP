"""Formulaire (dialogue modal) de saisie d'une ligne de location.

Le tarif journalier est pré-rempli avec le tarif catalogue de l'article
sélectionné (``Article.tarif_location_jour``), mais reste librement
modifiable — c'est le tarif réellement appliqué qui doit être conservé,
jamais recalculé automatiquement si le tarif catalogue change ensuite
(même principe que ``SaleLineFormDialog``/``VenteLigne.prix_unitaire``).
"""
from __future__ import annotations

from typing import Optional

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

from app.utils.quantity import format_quantity
from app.views.common import build_required_field_legend, format_decimal_for_input, required_label


class LocationLineFormDialog(QDialog):
    def __init__(
        self,
        articles: list[tuple[int, str, str]],
        initial: Optional[dict] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, tarif de
        location journalier actuel en texte — articles en mode Location
        uniquement, filtrés par l'appelant)."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles

        self.setWindowTitle("Ligne de location")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.article_combo = QComboBox(self)
        for article_id, label, tarif_jour in articles:
            self.article_combo.addItem(label, (article_id, tarif_jour))
        self._select_combo_data_by_id(initial.get("article_id"))
        form.addRow(required_label("Article"), self.article_combo)

        self.quantite_edit = QLineEdit(self)
        self.quantite_edit.setText(
            format_quantity(initial["quantite"]) if initial.get("quantite") is not None else ""
        )
        form.addRow(required_label("Quantité"), self.quantite_edit)

        self.tarif_jour_edit = QLineEdit(self)
        if initial.get("tarif_jour") is not None:
            self.tarif_jour_edit.setText(format_decimal_for_input(initial.get("tarif_jour")))
        form.addRow(required_label("Tarif journalier"), self.tarif_jour_edit)

        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Ajouter", self)
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)
        self.article_combo.currentIndexChanged.connect(self._on_article_changed)

        if not initial.get("tarif_jour") and articles:
            self._on_article_changed(self.article_combo.currentIndex())

    def _select_combo_data_by_id(self, article_id: Optional[int]) -> None:
        if article_id is None:
            return
        for index in range(self.article_combo.count()):
            if self.article_combo.itemData(index)[0] == article_id:
                self.article_combo.setCurrentIndex(index)
                return

    def _on_article_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self.article_combo.itemData(index)
        if data is None:
            return
        _article_id, tarif_jour = data
        self.tarif_jour_edit.setText(str(tarif_jour) if tarif_jour is not None else "")

    def values(self) -> dict:
        data = self.article_combo.currentData()
        return {
            "article_id": data[0] if data else None,
            "quantite": self.quantite_edit.text(),
            "tarif_jour": self.tarif_jour_edit.text(),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
