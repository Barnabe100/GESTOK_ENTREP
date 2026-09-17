"""Formulaire (dialogue modal) de saisie d'une ligne d'inventaire.

Le stock théorique est affiché en lecture seule (jamais saisi ni
modifiable) : c'est la valeur système au moment de l'ajout de la ligne,
capturée par le service (voir ``InventoryService._build_lignes``). Seul le
stock physiquement compté est une saisie utilisateur ; l'écart est recalculé
à l'affichage pour donner un retour immédiat, mais c'est le service qui fait
foi pour la valeur réellement enregistrée.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
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


class InventoryLineFormDialog(QDialog):
    def __init__(
        self,
        articles: list[tuple[int, str, str]],
        initial: Optional[dict] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, stock théorique actuel en texte)."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles

        self.setWindowTitle("Ligne d'inventaire")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.article_combo = QComboBox(self)
        for article_id, label, stock_theorique in articles:
            self.article_combo.addItem(label, (article_id, stock_theorique))
        self._select_combo_data_by_id(initial.get("article_id"))
        form.addRow("Article", self.article_combo)

        self.stock_theorique_label = QLabel("", self)
        self.stock_theorique_label.setStyleSheet("color: #6B7280;")
        form.addRow("Stock théorique (système)", self.stock_theorique_label)

        self.stock_physique_edit = QLineEdit(self)
        self.stock_physique_edit.setText(
            str(initial.get("stock_physique", "")) if initial.get("stock_physique") is not None else ""
        )
        form.addRow("Stock compté", self.stock_physique_edit)

        self.ecart_label = QLabel("—", self)
        form.addRow("Écart", self.ecart_label)

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
        self.stock_physique_edit.textChanged.connect(self._refresh_ecart)

        if articles:
            self._on_article_changed(self.article_combo.currentIndex())
        self._refresh_ecart()

    def _select_combo_data_by_id(self, article_id: Optional[int]) -> None:
        if article_id is None:
            return
        for index in range(self.article_combo.count()):
            if self.article_combo.itemData(index)[0] == article_id:
                self.article_combo.setCurrentIndex(index)
                return

    def _current_stock_theorique(self) -> Optional[Decimal]:
        data = self.article_combo.currentData()
        if data is None:
            return None
        try:
            return Decimal(str(data[1]))
        except InvalidOperation:
            return None

    def _on_article_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self.article_combo.itemData(index)
        if data is None:
            return
        _article_id, stock_theorique = data
        self.stock_theorique_label.setText(str(stock_theorique))
        self._refresh_ecart()

    def _refresh_ecart(self) -> None:
        stock_theorique = self._current_stock_theorique()
        try:
            stock_physique = Decimal((self.stock_physique_edit.text() or "").strip().replace(",", "."))
        except InvalidOperation:
            self.ecart_label.setText("—")
            return
        if stock_theorique is None:
            self.ecart_label.setText("—")
            return
        ecart = stock_physique - stock_theorique
        self.ecart_label.setText(f"{ecart:+}")

    def values(self) -> dict:
        data = self.article_combo.currentData()
        return {
            "article_id": data[0] if data else None,
            "stock_physique": self.stock_physique_edit.text(),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
