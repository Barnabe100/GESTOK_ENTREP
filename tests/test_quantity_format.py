"""Formatage centralisé des quantités (``app.utils.quantity``) : une
quantité entière ne doit jamais afficher de décimales superflues (source de
confusion avec un millier, cf. lot « formatage des quantités »), une vraie
valeur décimale conserve sa précision réelle, et un écart peut porter un
signe explicite. Aucune valeur interne (Decimal, calculs de stock) n'est
modifiée par ces fonctions — uniquement leur représentation textuelle."""
from decimal import Decimal

import pytest

from app.utils.quantity import format_quantity, format_quantity_signed

# -- format_quantity : entiers -------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("10.000"), "10"),
        (Decimal("100.000"), "100"),
        (Decimal("-20.000"), "-20"),
        (Decimal("15.000"), "15"),
        (Decimal("0.000"), "0"),
        (Decimal("0"), "0"),
        (Decimal("1000000.000"), "1000000"),
    ],
)
def test_format_quantity_strips_unnecessary_decimals(value, expected) -> None:
    assert format_quantity(value) == expected


def test_format_quantity_zero_has_no_sign() -> None:
    assert format_quantity(Decimal("0.000")) == "0"
    assert format_quantity(Decimal("-0.000")) == "0"  # zéro négatif -> zéro canonique


# -- format_quantity : décimales réelles conservées -----------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("10.500"), "10,5"),
        (Decimal("2.750"), "2,75"),
        (Decimal("-2.500"), "-2,5"),
        (Decimal("0.100"), "0,1"),
        (Decimal("-0.500"), "-0,5"),
    ],
)
def test_format_quantity_preserves_real_decimal_precision(value, expected) -> None:
    """Une vraie quantité décimale n'est jamais transformée en entier — sa
    précision réelle est conservée, avec la virgule comme séparateur."""
    assert format_quantity(value) == expected


def test_format_quantity_does_not_round_or_truncate_precision() -> None:
    assert format_quantity(Decimal("1.234")) == "1,234"


# -- format_quantity : types d'entrée flexibles ----------------------------------------


def test_format_quantity_accepts_int() -> None:
    assert format_quantity(10) == "10"


def test_format_quantity_accepts_float() -> None:
    assert format_quantity(10.5) == "10,5"


def test_format_quantity_accepts_numeric_string() -> None:
    assert format_quantity("10.000") == "10"


# -- format_quantity_signed -------------------------------------------------------------


def test_format_quantity_signed_positive_integer_has_plus_sign() -> None:
    assert format_quantity_signed(15) == "+15"


def test_format_quantity_signed_negative_integer_keeps_minus_sign() -> None:
    assert format_quantity_signed(-15) == "-15"


def test_format_quantity_signed_zero_has_no_sign() -> None:
    assert format_quantity_signed(0) == "0"
    assert format_quantity_signed(Decimal("0.000")) == "0"


def test_format_quantity_signed_positive_decimal() -> None:
    assert format_quantity_signed(Decimal("1.500")) == "+1,5"


def test_format_quantity_signed_negative_decimal() -> None:
    assert format_quantity_signed(Decimal("-1.500")) == "-1,5"


def test_format_quantity_signed_never_produces_double_sign() -> None:
    """Le signe négatif porté par Decimal.normalize() ne doit jamais se
    cumuler avec le préfixe « + » (uniquement ajouté pour une valeur
    strictement positive)."""
    assert format_quantity_signed(Decimal("-3")).count("-") == 1
    assert not format_quantity_signed(Decimal("-3")).startswith("+-")
