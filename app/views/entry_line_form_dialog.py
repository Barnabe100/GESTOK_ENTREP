"""Formulaire (dialogue modal) de saisie d'une ligne d'entrée.

Ne connaît rien du service métier : restitue la sélection sous forme de
dictionnaire de chaînes, à l'identique des autres formulaires. Le prix
unitaire est pré-rempli avec le prix d'achat par défaut de l'article
sélectionné, mais reste librement modifiable (le prix réellement facturé par
le fournisseur peut différer du prix par défaut).
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


class EntryLineFormDialog(QDialog):
    def __init__(
        self,
        articles: list[tuple[int, str, str]],
        initial: Optional[dict] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, prix d'achat par défaut en texte)."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles

        self.setWindowTitle("Ligne d'entrée")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.article_combo = QComboBox(self)
        for article_id, label, prix_achat in articles:
            self.article_combo.addItem(label, (article_id, prix_achat))
        self._select_combo_data_by_id(initial.get("article_id"))
        form.addRow("Article", self.article_combo)

        self.quantite_edit = QLineEdit(self)
        self.quantite_edit.setText(str(initial.get("quantite", "")) if initial.get("quantite") is not None else "")
        form.addRow("Quantité", self.quantite_edit)

        self.prix_unitaire_edit = QLineEdit(self)
        if initial.get("prix_unitaire") is not None:
            self.prix_unitaire_edit.setText(str(initial.get("prix_unitaire")))
        form.addRow("Prix d'achat unitaire", self.prix_unitaire_edit)

        layout.addLayout(form)

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

        if not initial.get("prix_unitaire") and articles:
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
        _article_id, prix_achat_defaut = data
        self.prix_unitaire_edit.setText(str(prix_achat_defaut))

    def values(self) -> dict:
        data = self.article_combo.currentData()
        return {
            "article_id": data[0] if data else None,
            "quantite": self.quantite_edit.text(),
            "prix_unitaire": self.prix_unitaire_edit.text(),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
