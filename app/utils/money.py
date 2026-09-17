"""Logique monétaire centralisée.

Point unique d'arrondi et de formatage des montants. Aucun autre module ne
doit appeler ``Decimal.quantize`` ou formater un montant directement.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")

# Devises ne s'affichant traditionnellement sans décimales.
_ZERO_DECIMAL_CURRENCIES = {"XOF", "XAF"}

_CURRENCY_SYMBOLS = {
    "XOF": "FCFA",
    "XAF": "FCFA",
    "EUR": "€",
    "USD": "$",
}


def round_money(amount: Decimal) -> Decimal:
    """Arrondit un montant à 2 décimales selon la règle ROUND_HALF_UP (référence unique)."""
    return amount.quantize(CENTS, rounding=ROUND_HALF_UP)


def format_money(amount: Decimal, currency_code: str) -> str:
    """Formate un montant pour l'affichage, selon les conventions de la devise.

    Le stockage reste toujours en Decimal(14,2) ; seul l'affichage varie
    (ex. XOF : pas de décimales -> "15 000 FCFA").
    """
    currency_code = currency_code.upper()
    rounded = round_money(amount)

    if currency_code in _ZERO_DECIMAL_CURRENCIES:
        integer_value = int(rounded.to_integral_value(rounding=ROUND_HALF_UP))
        formatted_number = f"{integer_value:,}".replace(",", " ")
    else:
        formatted_number = f"{rounded:,.2f}".replace(",", " ")

    symbol = _CURRENCY_SYMBOLS.get(currency_code, currency_code)
    return f"{formatted_number} {symbol}"
