"""Fenêtre de personnalisation du Dashboard (Mission 3, §6.2) : choix des
indicateurs (KPI) à afficher, organisés par catégorie.

Ne connaît rien du calcul des indicateurs ni des permissions : reçoit déjà
de ``DashboardPage`` la liste des indicateurs réellement accessibles à
l'utilisateur courant (``options``) — cette fenêtre ne fait qu'afficher des
cases à cocher et restituer la sélection, à l'identique du principe déjà
en place pour les autres formulaires de ce projet (ex. ``ArticleFormDialog``
ne connaît pas non plus le service métier)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class KpiOption:
    """Un indicateur sélectionnable tel que présenté dans cette fenêtre —
    ``dashboard_page.py`` reste l'unique source de vérité pour la liste
    réelle des indicateurs, leurs libellés et leurs catégories."""

    id: str
    label: str
    category: str


class DashboardKpiSettingsDialog(QDialog):
    def __init__(
        self,
        options: Sequence[KpiOption],
        selected_ids: Sequence[str],
        default_ids: Sequence[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Personnaliser le tableau de bord")
        self.setModal(True)
        self.setMinimumWidth(440)

        self._default_ids = list(default_ids)
        self._checkboxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Choisissez les indicateurs à afficher sur le Dashboard, "
            "regroupés par catégorie. Les graphiques restent inchangés.",
            self,
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "secondary")
        layout.addWidget(intro)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)

        categories: dict[str, list[KpiOption]] = {}
        for option in options:
            categories.setdefault(option.category, []).append(option)

        selected_set = set(selected_ids)
        for category, category_options in categories.items():
            group = QGroupBox(category, self)
            group_layout = QVBoxLayout(group)
            for option in category_options:
                checkbox = QCheckBox(option.label, self)
                checkbox.setChecked(option.id in selected_set)
                self._checkboxes[option.id] = checkbox
                group_layout.addWidget(checkbox)
            content_layout.addWidget(group)
        content_layout.addStretch(1)

        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        button_row = QHBoxLayout()
        self.reset_button = QPushButton("Rétablir les valeurs par défaut", self)
        button_row.addWidget(self.reset_button)
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Enregistrer", self)
        self.save_button.setProperty("variant", "primary")
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.reset_button.clicked.connect(self._on_reset_clicked)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def _on_reset_clicked(self) -> None:
        defaults = set(self._default_ids)
        for kpi_id, checkbox in self._checkboxes.items():
            checkbox.setChecked(kpi_id in defaults)

    def selected_ids(self) -> list[str]:
        return [kpi_id for kpi_id, checkbox in self._checkboxes.items() if checkbox.isChecked()]
