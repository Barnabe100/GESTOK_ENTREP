"""Affichage unique du code de récupération administrateur, juste après sa
génération (voir ``AccountRecoveryService.generate_code``) — le code n'est
jamais stocké en clair ni rejournalisé : cette fenêtre est la seule et
dernière fois qu'il est visible. Fermer ce dialogue ne permet pas de le
rouvrir ; seule une nouvelle génération (qui invalide celui-ci) en produit
un autre."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RecoveryCodeDisplayDialog(QDialog):
    def __init__(self, code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Code de récupération généré")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        warning = QLabel(
            "Notez ce code immédiatement et conservez-le en lieu sûr : il ne "
            "sera plus jamais affiché. Toute nouvelle génération invalidera "
            "immédiatement ce code.",
            self,
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("font-weight: 600;")
        layout.addWidget(warning)

        code_row = QHBoxLayout()
        self.code_edit = QLineEdit(self)
        self.code_edit.setText(code)
        self.code_edit.setReadOnly(True)
        code_row.addWidget(self.code_edit)

        self.copy_button = QPushButton("Copier", self)
        self.copy_button.clicked.connect(self._on_copy_clicked)
        code_row.addWidget(self.copy_button)
        layout.addLayout(code_row)

        self.close_button = QPushButton("J'ai noté ce code", self)
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button)

    def _on_copy_clicked(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.code_edit.text())
