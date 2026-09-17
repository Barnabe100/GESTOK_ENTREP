"""Formulaire de création/modification d'une catégorie.

Ne connaît rien du service métier : collecte uniquement une saisie. C'est
:class:`CategoriesPage` qui appelle ``CategoryService`` et gère la validation.
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


class CategoryFormDialog(QDialog):
    def __init__(self, initial_name: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Catégorie")
        self.setModal(True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(self)
        self.name_edit.setText(initial_name)
        form.addRow("Nom", self.name_edit)
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

    def name(self) -> str:
        return self.name_edit.text()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
