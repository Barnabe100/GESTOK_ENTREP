"""Dialogue de confirmation de la réinitialisation des données métier
(§3 du lot : « Réinitialiser les données métier »).

Une simple boîte Oui/Non (``confirm_action``) n'est volontairement pas
utilisée ici : l'opération est irréversible sans la sauvegarde de sécurité
créée automatiquement par le service, et l'instruction est explicite —
« exiger une confirmation suffisamment explicite pour éviter une
suppression accidentelle ». L'utilisateur doit recopier exactement le mot
``RÉINITIALISER`` pour activer le bouton de confirmation.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_CONFIRMATION_PHRASE = "RÉINITIALISER"

_WARNING_TEXT = (
    "Cette action va supprimer DÉFINITIVEMENT toutes les données métier de test "
    "(articles, catégories, fournisseurs, clients, entrées, sorties, ventes, "
    "paiements, inventaires, mouvements de stock).\n\n"
    "Seront conservés : les utilisateurs, les rôles et permissions, les "
    "paramètres de l'entreprise (dont le logo et la devise), la licence, et "
    "le journal d'audit.\n\n"
    "Une sauvegarde de sécurité sera créée et vérifiée automatiquement avant "
    "toute suppression. Si cette sauvegarde échoue, rien ne sera réinitialisé.\n\n"
    f"Pour confirmer, recopiez exactement le mot « {_CONFIRMATION_PHRASE} » ci-dessous."
)


class DataResetConfirmDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Réinitialiser les données métier")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)

        warning_label = QLabel(_WARNING_TEXT, self)
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("color: #DC2626;")
        layout.addWidget(warning_label)

        self.confirmation_edit = QLineEdit(self)
        self.confirmation_edit.setPlaceholderText(_CONFIRMATION_PHRASE)
        layout.addWidget(self.confirmation_edit)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.confirm_button = QPushButton("Réinitialiser définitivement", self)
        self.confirm_button.setEnabled(False)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.confirm_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        self.confirmation_edit.textChanged.connect(self._on_confirmation_text_changed)

    def _on_confirmation_text_changed(self, text: str) -> None:
        self.confirm_button.setEnabled(text.strip() == _CONFIRMATION_PHRASE)
