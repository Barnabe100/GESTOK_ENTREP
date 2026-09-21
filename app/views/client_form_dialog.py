"""Formulaire de création/modification d'un client.

Ne connaît rien du service métier : collecte uniquement une saisie. C'est
:class:`ClientsPage` (ou ``SalesPage`` pour la création à la volée depuis le
formulaire de vente) qui appelle ``ClientService`` et gère la validation
(même principe que :class:`SupplierFormDialog`).
"""
from __future__ import annotations

from typing import Optional

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

from app.views.common import build_required_field_legend, required_label


class ClientFormDialog(QDialog):
    def __init__(self, initial: Optional[dict] = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        initial = initial or {}

        self.setWindowTitle("Client")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(self)
        self.name_edit.setText(initial.get("nom", ""))
        form.addRow(required_label("Nom"), self.name_edit)

        self.telephone_edit = QLineEdit(self)
        self.telephone_edit.setText(initial.get("telephone", "") or "")
        form.addRow("Téléphone", self.telephone_edit)

        self.email_edit = QLineEdit(self)
        self.email_edit.setText(initial.get("email", "") or "")
        form.addRow("Email", self.email_edit)

        self.adresse_edit = QLineEdit(self)
        self.adresse_edit.setText(initial.get("adresse", "") or "")
        form.addRow("Adresse", self.adresse_edit)

        self.observations_edit = QTextEdit(self)
        self.observations_edit.setPlainText(initial.get("observations", "") or "")
        self.observations_edit.setFixedHeight(60)
        form.addRow("Observations", self.observations_edit)

        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

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

    def values(self) -> dict:
        return {
            "nom": self.name_edit.text(),
            "telephone": self.telephone_edit.text(),
            "email": self.email_edit.text(),
            "adresse": self.adresse_edit.text(),
            "observations": self.observations_edit.toPlainText(),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
