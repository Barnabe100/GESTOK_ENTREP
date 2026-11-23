"""Panneau de recherche d'article (zone de texte + liste de résultats
filtrée en direct) — Mission 5.3 : reprend l'ergonomie de sélection déjà
en place dans les écrans de caisse Ventes/Locations (``SalesPage``/
``LocationsPage``, lot « Écran de caisse »), pour l'étendre aux formulaires
d'Entrées et de Sorties de stock sans dupliquer cette logique de filtrage
entre les modules qui la réutilisent.

Ne connaît rien du service métier ni du document (vente, entrée, sortie...)
dans lequel il s'insère : il reçoit une liste déjà construite par
l'appelant et se contente d'filtrer/afficher, puis de signaler la
sélection — exactement le même principe de séparation que les autres
composants partagés de ``app.views.common``/``app.views.design_system``.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ArticleSearchPanel(QWidget):
    """``articles`` : liste de tuples ``(article_id, libellé affiché déjà
    formaté)`` — c'est à l'appelant de composer ce libellé (référence,
    désignation, prix par défaut...), ce panneau ne formate jamais lui-même
    un montant pour rester indépendant de toute notion métier.

    Émet ``article_activated(article_id)`` sur double-clic d'un résultat ;
    ne modifie jamais la liste fournie, ne contacte jamais de service —
    l'appelant décide seul de ce qu'il advient de la sélection (ajout
    d'une ligne, avec quel prix par défaut, etc.)."""

    article_activated = Signal(int)

    def __init__(self, articles: list[tuple[int, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._articles = list(articles)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Rechercher un article", self))
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Désignation ou référence…")
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        # Même hauteur maximale que ``caisse_search_results`` (Ventes/
        # Locations) : assez de lignes visibles sans occuper une place
        # disproportionnée dans un dialogue par ailleurs compact.
        self.results_list = QListWidget(self)
        self.results_list.setMaximumHeight(140)
        layout.addWidget(self.results_list)

        self.search_edit.textChanged.connect(self._refresh_results)
        self.results_list.itemDoubleClicked.connect(self._on_item_activated)

        self._refresh_results()

    def set_articles(self, articles: list[tuple[int, str]]) -> None:
        """À appeler si la liste des articles proposés change après la
        construction (rare dans ces dialogues, la liste étant chargée une
        seule fois à l'ouverture — fourni par cohérence avec le reste de
        l'API, jamais utilisé en pratique pour l'instant)."""
        self._articles = list(articles)
        self._refresh_results()

    def clear_search(self) -> None:
        self.search_edit.clear()

    def _refresh_results(self) -> None:
        """Même logique que ``SalesPage._refresh_caisse_search_results`` :
        texte vide -> tous les articles fournis ; texte non vide ->
        filtrage insensible à la casse sur le libellé déjà formaté ;
        aucune correspondance avec un texte saisi -> message explicite,
        jamais sélectionnable (``ItemIsSelectable`` retiré)."""
        self.results_list.clear()
        normalized = self.search_edit.text().strip().lower()
        candidates = self._articles
        if normalized:
            candidates = [
                (article_id, label) for article_id, label in candidates if normalized in label.lower()
            ]
        if not candidates and normalized:
            empty_item = QListWidgetItem("Aucun article ne correspond à la recherche.", self.results_list)
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            return
        for article_id, label in candidates:
            item = QListWidgetItem(label, self.results_list)
            item.setData(Qt.ItemDataRole.UserRole, article_id)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        article_id = item.data(Qt.ItemDataRole.UserRole)
        if article_id is None:
            return
        self.article_activated.emit(article_id)
