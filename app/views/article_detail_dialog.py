"""Consultation détaillée, en lecture seule, d'un article.

Aucun champ n'est modifiable ici : c'est une vue, pas un formulaire. Toute
modification passe par :class:`ArticleFormDialog` via l'action « Modifier ».
"""
from __future__ import annotations

from app.services.articles.article_service import ArticleSummary
from app.utils.money import format_money
from app.utils.quantity import format_quantity
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ArticleDetailDialog(QDialog):
    def __init__(self, article: ArticleSummary, currency_code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Article — {article.reference}")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Référence", QLabel(article.reference, self))
        form.addRow("Désignation", QLabel(article.designation, self))
        form.addRow("Catégorie", QLabel(article.category_nom, self))
        form.addRow("Fournisseur principal", QLabel(article.fournisseur_principal_nom or "—", self))
        form.addRow("Unité", QLabel(article.unite, self))
        form.addRow("Prix d'achat", QLabel(format_money(article.prix_achat, currency_code), self))
        form.addRow("Prix de vente", QLabel(format_money(article.prix_vente, currency_code), self))

        cmup_label = QLabel(format_money(article.cout_moyen_pondere, currency_code), self)
        cmup_label.setToolTip("Coût Moyen Unitaire Pondéré — piloté par le système, non modifiable ici.")
        form.addRow("CMUP", cmup_label)

        stock_label = QLabel(format_quantity(article.stock_actuel), self)
        if article.en_rupture:
            stock_label.setStyleSheet("color: #DC2626; font-weight: 600;")
            stock_label.setText(f"{format_quantity(article.stock_actuel)} (rupture)")
        elif article.stock_faible:
            stock_label.setStyleSheet("color: #B45309; font-weight: 600;")
            stock_label.setText(f"{format_quantity(article.stock_actuel)} (stock faible)")
        stock_label.setToolTip("Piloté par le système de mouvements de stock, non modifiable ici.")
        form.addRow("Stock actuel", stock_label)

        form.addRow("Stock minimum", QLabel(format_quantity(article.stock_min), self))
        form.addRow(
            "Stock maximum",
            QLabel(format_quantity(article.stock_max) if article.stock_max is not None else "—", self),
        )
        form.addRow("Emplacement", QLabel(article.emplacement or "—", self))
        form.addRow("Code-barres", QLabel(article.code_barres or "—", self))
        form.addRow("Description", QLabel(article.description or "—", self))
        form.addRow("Statut", QLabel("Actif" if article.actif else "Inactif", self))
        form.addRow("Créé le", QLabel(article.date_creation.strftime("%Y-%m-%d %H:%M"), self))
        form.addRow("Modifié le", QLabel(article.date_modification.strftime("%Y-%m-%d %H:%M"), self))

        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_button = QPushButton("Fermer", self)
        self.close_button.clicked.connect(self.accept)
        button_row.addWidget(self.close_button)
        layout.addLayout(button_row)
