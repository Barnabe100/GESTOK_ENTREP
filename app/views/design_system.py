"""Design System centralisé de StockManager Desktop (refonte visuelle
globale) — complète ``app/resources/styles/app.qss``, qui porte tout ce qui
est exprimable en QSS (couleurs, typographie, boutons par ``variant``,
champs de saisie, tableaux, cartes...). Ce module porte ce qui ne l'est
pas : les couleurs utiles au code Python (séries de graphiques
``QtCharts``, qui ne lisent jamais la feuille de style) et les deux
composants réutilisables qui n'ont pas d'équivalent Qt natif.

Jamais de logique métier ici : uniquement de la présentation. Importer les
couleurs d'ici plutôt que de recopier un code hexadécimal dans chaque page
— une seule source de vérité pour la palette, cohérente avec ``app.qss``.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QSizePolicy, QVBoxLayout, QWidget

# -- Palette (voir app.qss pour le détail des composants QSS) ------------------------

COLOR_SIDEBAR = "#172B4D"
COLOR_PRIMARY = "#2563EB"
COLOR_BACKGROUND = "#F4F6FA"
COLOR_CARD = "#FFFFFF"
COLOR_BORDER = "#E2E8F0"
COLOR_TEXT_PRIMARY = "#1E293B"
COLOR_TEXT_SECONDARY = "#64748B"
COLOR_SUCCESS = "#16A34A"
COLOR_WARNING = "#D97706"
COLOR_DANGER = "#DC2626"
COLOR_INFO = "#0284C7"
COLOR_INDIGO = "#4F46E5"
COLOR_VIOLET = "#7C3AED"

# Accents disponibles pour KpiCard — mêmes valeurs que les sélecteurs
# QFrame#kpiCard[accent="..."] de app.qss, jamais dupliquées à la main.
_KPI_ACCENT_COLORS: dict[str, str] = {
    "blue": COLOR_PRIMARY,
    "indigo": COLOR_INDIGO,
    "orange": COLOR_WARNING,
    "red": COLOR_DANGER,
    "green": COLOR_SUCCESS,
    "violet": COLOR_VIOLET,
}


def qcolor(hex_value: str) -> QColor:
    """Convertit une couleur de la palette en ``QColor`` — utile pour les
    séries ``QtCharts`` (``QBarSet.setColor``/``QPieSlice.setBrush``), qui
    ne lisent jamais ``app.qss`` (rendu par QPainter, pas par le moteur de
    style Qt)."""
    return QColor(hex_value)


# -- KpiCard : carte d'indicateur (icône + intitulé + valeur + accent coloré) --------


class KpiCard(QFrame):
    """Carte d'indicateur du Dashboard (§4.3 de la refonte) : une icône
    discrète (simple glyphe Unicode, jamais une dépendance à un jeu
    d'icônes externe non packagé), un intitulé, une valeur mise en
    évidence, et un accent coloré sur la bordure gauche selon la nature de
    l'indicateur — jamais la carte entière coloriée (§4.3 : « éviter de
    colorer intégralement toutes les cartes »).

    Purement un composant de présentation : ``set_value`` est la seule
    méthode appelée après construction, aucune logique métier ni appel de
    service ici."""

    def __init__(self, title: str, icon: str, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if accent not in _KPI_ACCENT_COLORS:
            raise ValueError(f"Accent inconnu : {accent!r} (attendu : {sorted(_KPI_ACCENT_COLORS)})")
        self.setObjectName("kpiCard")
        self.setProperty("accent", accent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        icon_label = QLabel(icon, self)
        icon_label.setObjectName("kpiIcon")
        header_row.addWidget(icon_label)
        title_label = QLabel(title, self)
        title_label.setObjectName("kpiTitle")
        title_label.setWordWrap(True)
        header_row.addWidget(title_label, stretch=1)
        layout.addLayout(header_row)

        self.value_label = QLabel("—", self)
        self.value_label.setObjectName("kpiValue")
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


# -- FlowLayout : disposition en flux, avec retour à la ligne automatique -----------


class FlowLayout(QLayout):
    """Disposition en flux horizontal avec retour à la ligne automatique
    selon la largeur disponible — contrairement à ``QHBoxLayout``, ne
    déborde jamais horizontalement (§4.7 de la refonte : correction du
    débordement des boutons d'accès rapide du Dashboard). Adaptation du
    recueil Qt officiel (« Flow Layout » example), strictement un
    agencement géométrique : ne modifie jamais le contenu ni le
    comportement des widgets qu'elle dispose."""

    def __init__(self, parent: Optional[QWidget] = None, margin: int = 0, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def __del__(self) -> None:
        while self.count():
            self.takeAt(0)

    def addItem(self, item) -> None:  # noqa: N802 - API Qt imposée
        self._items.append(item)

    def count(self) -> int:  # noqa: N802 - API Qt imposée
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - API Qt imposée
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802 - API Qt imposée
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802 - API Qt imposée
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - API Qt imposée
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - API Qt imposée
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect) -> None:  # noqa: N802 - API Qt imposée
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt imposée
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - API Qt imposée
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, *, apply: bool) -> int:
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue
            item_size = item.sizeHint()
            next_x = x + item_size.width() + spacing
            if next_x - spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + spacing
                next_x = x + item_size.width() + spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), item_size))
            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y()
