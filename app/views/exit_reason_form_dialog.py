"""Formulaire de création/modification d'un motif de sortie.

Ne connaît rien du service métier : collecte uniquement une saisie. C'est
:class:`ExitReasonsPage` qui appelle ``ExitReasonService`` et gère la
validation (même principe que :class:`CategoryFormDialog`).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
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


class ExitReasonFormDialog(QDialog):
    def __init__(
        self, initial_libelle: str = "", initial_description: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Motif de sortie")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.label_edit = QLineEdit(self)
        self.label_edit.setText(initial_libelle)
        form.addRow("Libellé", self.label_edit)

        self.description_edit = QTextEdit(self)
        self.description_edit.setPlainText(initial_description)
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

    def libelle(self) -> str:
        return self.label_edit.text()

    def description(self) -> str:
        return self.description_edit.toPlainText()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
