"""Page d'attente générique.

Chaque module métier (Articles, Entrées, Ventes, ...) sera implémenté dans
une phase ultérieure. En Phase 1, la navigation existe et fonctionne, mais
les pages ne contiennent aucune logique métier.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    def __init__(self, module_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.module_name = module_name

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(f"Module « {module_name} » — à venir")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
