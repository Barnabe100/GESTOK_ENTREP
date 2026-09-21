"""Formulaire (dialogue modal) de saisie d'une ligne de sortie.

Contrairement à une ligne d'entrée, aucun coût n'est saisi ici : le coût de
valorisation d'une sortie est toujours le CMUP courant de l'article (§6 du
cahier des charges de cette phase), affiché à titre indicatif seulement. La
valeur réellement appliquée au mouvement est celle rafraîchie par
``ExitService.validate_exit`` au moment de la validation.
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

from app.views.common import build_required_field_legend, required_label


class ExitLineFormDialog(QDialog):
    def __init__(
        self,
        articles: list[tuple[int, str, str]],
        initial: Optional[dict] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, CMUP courant en texte)."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles

        self.setWindowTitle("Ligne de sortie")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.article_combo = QComboBox(self)
        for article_id, label, cmup in articles:
            self.article_combo.addItem(label, (article_id, cmup))
        self._select_combo_data_by_id(initial.get("article_id"))
        form.addRow(required_label("Article"), self.article_combo)

        self.quantite_edit = QLineEdit(self)
        self.quantite_edit.setText(str(initial.get("quantite", "")) if initial.get("quantite") is not None else "")
        form.addRow(required_label("Quantité"), self.quantite_edit)

        self.cmup_label = QLabel("", self)
        self.cmup_label.setStyleSheet("color: #6B7280;")
        form.addRow("Coût de valorisation (CMUP courant)", self.cmup_label)

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

        if articles:
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
        _article_id, cmup = data
        self.cmup_label.setText(str(cmup))

    def values(self) -> dict:
        data = self.article_combo.currentData()
        return {
            "article_id": data[0] if data else None,
            "quantite": self.quantite_edit.text(),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
