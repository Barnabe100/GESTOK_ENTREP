"""Dialogue de création d'une nouvelle unité d'article (§7.3, bouton
« Nouveau » du formulaire article).

Ne connaît rien du service métier : collecte uniquement une saisie, à
l'identique de :class:`ExitReasonFormDialog` — c'est :class:`ArticleFormDialog`
(``_on_new_unite_clicked``) qui appelle ``UniteArticleService.create_unite``
(via la fonction fournie par :class:`ArticlesPage`) et gère la validation
(trim, rejet des valeurs vides, doublons insensibles à la casse).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
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


class ArticleUniteDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouvelle unité")
        self.setModal(True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.libelle_edit = QLineEdit(self)
        form.addRow(required_label("Libellé"), self.libelle_edit)
        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Créer", self)
        self.save_button.setProperty("variant", "primary")
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def libelle(self) -> str:
        return self.libelle_edit.text()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
