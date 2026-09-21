from decimal import Decimal

from app.views.payment_form_dialog import PaymentFormDialog
from tests.ui_test_helpers import (
    assert_field_is_marked_required,
    assert_field_is_not_marked_required,
    assert_has_required_field_legend,
)


def _build_dialog() -> PaymentFormDialog:
    return PaymentFormDialog(Decimal("62500"), Decimal("0"), Decimal("62500"), "XOF")


def test_montant_field_is_marked_required(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.montant_edit)


def test_optional_fields_are_not_marked_required(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    for field in (dialog.mode_paiement_edit, dialog.reference_edit, dialog.commentaire_edit):
        assert_field_is_not_marked_required(dialog, field)


def test_optional_fields_no_longer_mention_optionnel(qtbot) -> None:
    """Convention unique (audit champs obligatoires) : la mention
    « (optionnel) » devient redondante une fois l'astérisque en place sur
    les champs obligatoires — supprimée des placeholders."""
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert "optionnel" not in dialog.mode_paiement_edit.placeholderText().lower()
    assert "optionnel" not in (dialog.reference_edit.placeholderText() or "").lower()
    assert "optionnel" not in (dialog.commentaire_edit.placeholderText() or "").lower()


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_values_still_returns_optional_fields_as_none_when_empty(qtbot) -> None:
    """Non-régression : le comportement de conversion (chaîne vide -> None)
    n'est pas affecté par le retrait de la mention « (optionnel) »."""
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["mode_paiement"] is None
    assert values["reference"] is None
    assert values["commentaire"] is None
