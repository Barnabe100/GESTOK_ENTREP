"""Formulaire de création/modification d'un article.

Ne connaît rien du service métier : collecte uniquement une saisie et la
restitue sous forme de dictionnaire de chaînes ; c'est :class:`ArticlesPage`
qui appelle ``ArticleService`` et gère la validation (même principe que les
formulaires Catégories/Fournisseurs/Motifs de sortie).

Point important : ce formulaire n'expose **aucun** champ « stock actuel »
librement modifiable. En création, seul un « stock initial » est proposé
(traité par le service comme une opération d'initialisation tracée, pas
comme une affectation directe). En modification, le stock actuel et le CMUP
sont affichés en lecture seule, avec une mention explicite qu'ils sont
pilotés par le système.
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.utils.quantity import format_quantity

UNIT_SUGGESTIONS = ["pièce", "unité", "carton", "paquet", "kg", "litre", "mètre"]


class ArticleFormDialog(QDialog):
    def __init__(
        self,
        categories: list[tuple[int, str]],
        suppliers: list[tuple[int, str]],
        initial: Optional[dict] = None,
        is_edit: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        initial = initial or {}
        self.is_edit = is_edit

        self.setWindowTitle("Article")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.reference_edit = QLineEdit(self)
        self.reference_edit.setText(initial.get("reference", ""))
        form.addRow("Référence", self.reference_edit)

        self.designation_edit = QLineEdit(self)
        self.designation_edit.setText(initial.get("designation", ""))
        form.addRow("Désignation", self.designation_edit)

        self.category_combo = QComboBox(self)
        for category_id, nom in categories:
            self.category_combo.addItem(nom, category_id)
        self._select_combo_data(self.category_combo, initial.get("category_id"))
        form.addRow("Catégorie", self.category_combo)

        self.supplier_combo = QComboBox(self)
        self.supplier_combo.addItem("(Aucun)", None)
        for supplier_id, nom in suppliers:
            self.supplier_combo.addItem(nom, supplier_id)
        self._select_combo_data(self.supplier_combo, initial.get("fournisseur_principal_id"))
        form.addRow("Fournisseur principal", self.supplier_combo)

        self.unite_combo = QComboBox(self)
        self.unite_combo.setEditable(True)
        self.unite_combo.addItems(UNIT_SUGGESTIONS)
        self.unite_combo.setCurrentText(initial.get("unite", "") or "")
        form.addRow("Unité", self.unite_combo)

        self.prix_achat_edit = QLineEdit(self)
        self.prix_achat_edit.setText(_as_text(initial.get("prix_achat"), default="0"))
        form.addRow("Prix d'achat", self.prix_achat_edit)

        self.prix_vente_edit = QLineEdit(self)
        self.prix_vente_edit.setText(_as_text(initial.get("prix_vente"), default="0"))
        form.addRow("Prix de vente", self.prix_vente_edit)

        self.stock_min_edit = QLineEdit(self)
        self.stock_min_edit.setText(
            format_quantity(initial["stock_min"]) if initial.get("stock_min") is not None else "0"
        )
        form.addRow("Stock minimum", self.stock_min_edit)

        self.stock_max_edit = QLineEdit(self)
        self.stock_max_edit.setText(
            format_quantity(initial["stock_max"]) if initial.get("stock_max") is not None else ""
        )
        form.addRow("Stock maximum (optionnel)", self.stock_max_edit)

        self.stock_initial_edit: Optional[QLineEdit] = None
        self.stock_actuel_label: Optional[QLabel] = None
        self.cmup_label: Optional[QLabel] = None

        if is_edit:
            self.stock_actuel_label = QLabel(
                format_quantity(initial["stock_actuel"]) if initial.get("stock_actuel") is not None else "0", self
            )
            self.stock_actuel_label.setStyleSheet("color: #6B7280;")
            form.addRow("Stock actuel (piloté par le système)", self.stock_actuel_label)

            self.cmup_label = QLabel(_as_text(initial.get("cout_moyen_pondere"), default="0"), self)
            self.cmup_label.setStyleSheet("color: #6B7280;")
            form.addRow("CMUP (piloté par le système)", self.cmup_label)
        else:
            self.stock_initial_edit = QLineEdit(self)
            self.stock_initial_edit.setText("0")
            form.addRow("Stock initial", self.stock_initial_edit)

        self.emplacement_edit = QLineEdit(self)
        self.emplacement_edit.setText(initial.get("emplacement", "") or "")
        form.addRow("Emplacement", self.emplacement_edit)

        self.code_barres_edit = QLineEdit(self)
        self.code_barres_edit.setText(initial.get("code_barres", "") or "")
        form.addRow("Code-barres (optionnel)", self.code_barres_edit)

        self.description_edit = QTextEdit(self)
        self.description_edit.setPlainText(initial.get("description", "") or "")
        self.description_edit.setFixedHeight(60)
        form.addRow("Description", self.description_edit)

        layout.addLayout(form)

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

    @staticmethod
    def _select_combo_data(combo: QComboBox, data) -> None:
        if data is None:
            return
        index = combo.findData(data)
        if index >= 0:
            combo.setCurrentIndex(index)

    def values(self) -> dict:
        return {
            "reference": self.reference_edit.text(),
            "designation": self.designation_edit.text(),
            "category_id": self.category_combo.currentData(),
            "fournisseur_principal_id": self.supplier_combo.currentData(),
            "unite": self.unite_combo.currentText(),
            "prix_achat": self.prix_achat_edit.text(),
            "prix_vente": self.prix_vente_edit.text(),
            "stock_min": self.stock_min_edit.text(),
            "stock_max": self.stock_max_edit.text(),
            "emplacement": self.emplacement_edit.text(),
            "code_barres": self.code_barres_edit.text(),
            "description": self.description_edit.toPlainText(),
            "stock_initial": self.stock_initial_edit.text() if self.stock_initial_edit else "0",
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)


def _as_text(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value)
