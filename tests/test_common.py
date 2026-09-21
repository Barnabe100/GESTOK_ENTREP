from PySide6.QtWidgets import QWidget

from app.views.common import (
    REQUIRED_FIELD_LEGEND,
    REQUIRED_FIELD_MARKER,
    build_required_field_legend,
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
