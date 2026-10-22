from decimal import Decimal

import pytest
from PySide6.QtWidgets import QWidget

from app.views.common import (
    REQUIRED_FIELD_LEGEND,
    REQUIRED_FIELD_MARKER,
    build_required_field_legend,
    format_decimal_for_input,
    parse_decimal,
    required_label,
)


def test_required_field_marker_is_a_single_asterisk() -> None:
    """Convention unique de l'application (audit champs obligatoires) :
    « * » pour obligatoire, rien pour facultatif — jamais « (optionnel) »."""
    assert REQUIRED_FIELD_MARKER == "*"


def test_required_label_appends_marker_to_text() -> None:
    assert required_label("Référence") == "Référence *"


def test_required_label_does_not_mutate_original_text() -> None:
    text = "Nom"
    required_label(text)
    assert text == "Nom"  # aucun effet de bord


def test_required_field_legend_text_is_exact() -> None:
    assert REQUIRED_FIELD_LEGEND == "* Champ obligatoire"


def test_build_required_field_legend_returns_label_with_expected_text(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    legend = build_required_field_legend(parent)

    assert legend.text() == REQUIRED_FIELD_LEGEND
    assert legend.objectName() == "requiredFieldLegend"


# -- format_decimal_for_input (Lot 23, §E) ----------------------------------------------
#
# Même principe que ``app.utils.quantity.format_quantity`` (déjà testé dans
# ``test_quantity_format.py``), appliqué aux montants/prix — mais avec « . »
# comme séparateur, jamais la virgule.


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("7500.00"), "7500"),
        (Decimal("5000.00"), "5000"),
        (Decimal("9500.00"), "9500"),
        (Decimal("100.00"), "100"),
        (Decimal("0.00"), "0"),
        (Decimal("0"), "0"),
        (Decimal("1000000.00"), "1000000"),
    ],
)
def test_format_decimal_for_input_strips_unnecessary_decimals(value, expected) -> None:
    assert format_decimal_for_input(value) == expected


def test_format_decimal_for_input_zero_has_no_sign() -> None:
    assert format_decimal_for_input(Decimal("0.00")) == "0"
    assert format_decimal_for_input(Decimal("-0.00")) == "0"


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("7500.50"), "7500.5"),
        (Decimal("2.75"), "2.75"),
        (Decimal("0.10"), "0.1"),
        (Decimal("100.05"), "100.05"),
    ],
)
def test_format_decimal_for_input_preserves_real_decimal_precision(value, expected) -> None:
    """Une décimale réellement significative n'est jamais supprimée —
    séparateur « . », jamais la virgule (contrairement à format_quantity)."""
    assert format_decimal_for_input(value) == expected


def test_format_decimal_for_input_does_not_round_or_truncate_precision() -> None:
    assert format_decimal_for_input(Decimal("1.234")) == "1.234"


def test_format_decimal_for_input_never_uses_scientific_notation() -> None:
    assert format_decimal_for_input(Decimal("1000000.00")) == "1000000"
    assert "E" not in format_decimal_for_input(Decimal("1000000.00"))


def test_format_decimal_for_input_round_trips_through_parse_decimal() -> None:
    """La valeur affichée sans décimale superflue reste exploitable par
    ``parse_decimal`` — aucune perte d'information pour une nouvelle saisie
    ou une modification."""
    original = Decimal("7500.00")
    displayed = format_decimal_for_input(original)
    reparsed = parse_decimal(displayed, "montant")

    assert reparsed == original


def test_format_decimal_for_input_round_trips_real_decimal() -> None:
    original = Decimal("7500.50")
    displayed = format_decimal_for_input(original)
    reparsed = parse_decimal(displayed, "montant")

    assert reparsed == original
