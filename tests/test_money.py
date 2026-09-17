from decimal import Decimal

from app.utils.money import format_money, round_money


def test_round_money_applies_half_up() -> None:
    assert round_money(Decimal("10.005")) == Decimal("10.01")
    assert round_money(Decimal("10.004")) == Decimal("10.00")
    assert round_money(Decimal("10.015")) == Decimal("10.02")


def test_format_money_xof_has_no_decimals() -> None:
    assert format_money(Decimal("15000.00"), "XOF") == "15 000 FCFA"


def test_format_money_xof_rounds_before_truncating_display() -> None:
    assert format_money(Decimal("15000.60"), "XOF") == "15 001 FCFA"


def test_format_money_eur_keeps_two_decimals() -> None:
    assert format_money(Decimal("1234.5"), "EUR") == "1 234.50 €"


def test_format_money_unknown_currency_uses_code_as_symbol() -> None:
    assert format_money(Decimal("10.00"), "GBP") == "10.00 GBP"
