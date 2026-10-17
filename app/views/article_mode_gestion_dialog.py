"""Dialogue de bascule du mode de gestion d'un article (VENTE <-> LOCATION,
module Locations, lot dédié).

Action volontairement séparée du formulaire d'édition habituel
(``ArticleFormDialog``) : chaque changement est audité et historisé
(``ArticleModeGestionChangement`` via ``ArticleService.switch_mode_gestion``),
jamais un simple champ parmi d'autres.
"""
from __future__ import annotations

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
    def __init__(self, article_reference: str, mode_actuel: ModeGestionArticle, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Confirmer la bascule", self)
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def nouveau_mode(self) -> ModeGestionArticle:
        return self.mode_combo.currentData()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
