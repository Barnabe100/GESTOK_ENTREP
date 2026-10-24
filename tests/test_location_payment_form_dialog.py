from decimal import Decimal

from PySide6.QtWidgets import QComboBox

from app.models.payment_mode import MODES_PAIEMENT
from app.views.location_payment_form_dialog import LocationPaymentFormDialog
from tests.ui_test_helpers import assert_field_is_not_marked_required


def _build_dialog() -> LocationPaymentFormDialog:
    return LocationPaymentFormDialog(Decimal("62500"), Decimal("0"), Decimal("62500"), "XOF")


def test_optional_fields_are_not_marked_required(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    for field in (dialog.mode_paiement_combo, dialog.reference_edit, dialog.commentaire_edit):
        assert_field_is_not_marked_required(dialog, field)


def test_values_still_returns_optional_fields_as_none_when_empty(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["mode_paiement"] is None
    assert values["reference"] is None
    assert values["commentaire"] is None


# -- Évolution E : liste fermée des modes de paiement (identique à Ventes) -----------


def test_mode_paiement_is_a_closed_dropdown_not_free_text(qtbot) -> None:
    """Non-régression : voir le test équivalent dans
    ``tests/test_payment_form_dialog.py`` (Ventes) — même correctif, même
    source de référence partagée (``app.models.payment_mode``)."""
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert isinstance(dialog.mode_paiement_combo, QComboBox)
    assert not hasattr(dialog, "mode_paiement_edit")


def test_mode_paiement_dropdown_proposes_exactly_the_reference_modes(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    modes_proposes = [dialog.mode_paiement_combo.itemData(i) for i in range(dialog.mode_paiement_combo.count())]
    assert modes_proposes == [None, *MODES_PAIEMENT]


def test_mode_paiement_dropdown_matches_ventes_reference_list(qtbot) -> None:
    """§6 : Ventes et Locations doivent présenter des choix cohérents et
    compatibles — même liste fermée, une seule source de référence."""
    from app.views.payment_form_dialog import PaymentFormDialog

    ventes_dialog = PaymentFormDialog(Decimal("1"), Decimal("0"), Decimal("1"), "XOF")
    location_dialog = _build_dialog()
    qtbot.addWidget(ventes_dialog)
    qtbot.addWidget(location_dialog)

    ventes_modes = [ventes_dialog.mode_paiement_combo.itemData(i) for i in range(ventes_dialog.mode_paiement_combo.count())]
    location_modes = [
        location_dialog.mode_paiement_combo.itemData(i) for i in range(location_dialog.mode_paiement_combo.count())
    ]
    assert ventes_modes == location_modes


def test_mode_paiement_defaults_to_non_precise(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert dialog.mode_paiement_combo.currentData() is None


def test_mode_paiement_selection_is_returned_as_plain_str(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    index = dialog.mode_paiement_combo.findData("Virement")
    dialog.mode_paiement_combo.setCurrentIndex(index)

    valeur = dialog.values()["mode_paiement"]
    assert valeur == "Virement"
    assert isinstance(valeur, str)
