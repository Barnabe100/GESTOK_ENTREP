"""Composant UI réutilisable pour une date de filtre optionnelle
(Lot E-B.1).

Un ``QDateEdit`` porte toujours une date valide : il ne peut pas, seul,
représenter l'absence de borne (« tout l'historique »), pourtant nécessaire
aux filtres de période de Rapports/Mouvements/Audit. Ce composant associe
une case à cocher (date active ou non) à un ``QDateEdit`` (calendrier
popup, format ``yyyy-MM-dd``), désactivé tant que la case n'est pas
cochée — la date affichée reste mémorisée dans le widget même décoché,
pour être retrouvée telle quelle si l'utilisateur recoche la case.

Composant purement UI : aucune logique métier, aucun accès
service/repository, aucune validation au-delà de ce que ``QDateEdit``
garantit déjà nativement (une date toujours valide).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QCheckBox, QDateEdit, QHBoxLayout, QWidget

from app.views.common import date_to_qdate


class OptionalDateEdit(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.checkbox = QCheckBox(self)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setEnabled(False)

        layout.addWidget(self.checkbox)
        layout.addWidget(self.date_edit)

        self.checkbox.toggled.connect(self.date_edit.setEnabled)

    def date_or_none(self) -> Optional[date]:
        """``None`` si la case n'est pas cochée — jamais la date
        actuellement affichée par le ``QDateEdit`` désactivé, même si une
        date y reste mémorisée."""
        if not self.checkbox.isChecked():
            return None
        return self.date_edit.date().toPython()

    def set_date_or_none(self, value: Optional[date]) -> None:
        """``None`` décoche la case (le ``QDateEdit`` se désactive en
        conséquence, sans que sa dernière valeur affichée soit effacée).
        Une date coche la case et préremplit le ``QDateEdit``."""
        if value is None:
            self.checkbox.setChecked(False)
            return
        self.date_edit.setDate(date_to_qdate(value))
        self.checkbox.setChecked(True)
