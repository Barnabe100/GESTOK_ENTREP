"""Validation de la date d'une opération métier (entrées, sorties, ventes,
inventaires) : ``date_operation`` ne doit jamais être postérieure à la date
du jour.

Utilise systématiquement ``date.today()`` — la date **locale** du poste,
jamais un ``datetime`` UTC comparé naïvement — cohérente avec les colonnes
``Date`` (sans heure ni fuseau) portées par ``Entree``/``Sortie``/``Vente``/
``Inventaire`` et avec la date affichée par les formulaires Qt
(``QDate.currentDate()``, également basée sur l'horloge locale du poste).
"""
from __future__ import annotations

from datetime import date

from app.utils.exceptions import ValidationError

DATE_FUTURE_MESSAGE = "La date de l'opération ne peut pas être postérieure à la date du jour."


def validate_not_future_date(value: date) -> date:
    """Lève :class:`ValidationError` si ``value`` est postérieure à
    aujourd'hui (date locale). Ne s'applique jamais à une date passée ou
    égale à aujourd'hui, quel que soit le statut (brouillon compris) de
    l'opération qui la porte."""
    if value > date.today():
        raise ValidationError(DATE_FUTURE_MESSAGE)
    return value
