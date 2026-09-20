"""Formatage centralisé des quantités (stock, mouvements, écarts).

Point unique de présentation d'une quantité : aucun autre module ne doit
formater une quantité directement (même principe que ``app.utils.money``
pour les montants). La valeur interne (``Decimal``, colonnes SQL, calculs de
stock/CMUP/écarts) n'est jamais modifiée par ce module — uniquement sa
représentation textuelle :

- une quantité entière ne doit jamais afficher de décimales inutiles
  (``Decimal("10.000")`` -> ``"10"``, jamais ``"10.000"``, qui prête à
  confusion avec un millier) ;
- une vraie valeur décimale conserve sa précision réelle
  (``Decimal("10.500")`` -> ``"10,5"``), jamais arrondie ni tronquée ;
- séparateur décimal « , » (convention déjà utilisée par
  ``app.views.common.parse_decimal``, qui accepte la virgule en saisie).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Union

Number = Union[Decimal, int, float, str]


def _to_decimal(value: Number) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def format_quantity(value: Number) -> str:
    """Représentation la plus courte et exacte d'une quantité : entière sans
    décimale superflue, décimale avec sa précision réelle conservée."""
    quantity = _to_decimal(value)
    if quantity == 0:
        return "0"
    text = format(quantity.normalize(), "f")
    return text.replace(".", ",")


def format_quantity_signed(value: Number) -> str:
    """Comme :func:`format_quantity`, avec un signe explicite (``+``/``-``)
    devant toute valeur non nulle — pour les écarts d'inventaire, jamais
    pour une quantité simple (une quantité vendue/entrée/sortie n'a pas de
    signe à afficher, seul un écart en a besoin)."""
    quantity = _to_decimal(value)
    if quantity == 0:
        return "0"
    text = format_quantity(quantity)
    return f"+{text}" if quantity > 0 else text
