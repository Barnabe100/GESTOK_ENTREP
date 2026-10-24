from decimal import Decimal

from PySide6.QtWidgets import QComboBox

from app.models.payment_mode import MODES_PAIEMENT
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

    for field in (dialog.mode_paiement_combo, dialog.reference_edit, dialog.commentaire_edit):
        assert_field_is_not_marked_required(dialog, field)


def test_optional_fields_no_longer_mention_optionnel(qtbot) -> None:
    """Convention unique (audit champs obligatoires) : la mention
    « (optionnel) » devient redondante une fois l'astérisque en place sur
    les champs obligatoires — supprimée des placeholders."""
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert "optionnel" not in (dialog.reference_edit.placeholderText() or "").lower()
    assert "optionnel" not in (dialog.commentaire_edit.placeholderText() or "").lower()


# -- Évolution D : liste fermée des modes de paiement ---------------------------------


def test_mode_paiement_is_a_closed_dropdown_not_free_text(qtbot) -> None:
    """Non-régression : le champ ne doit plus jamais redevenir une saisie
    libre (QLineEdit), qui permettait des fautes de frappe/valeurs
    arbitraires — c'est exactement ce que cette évolution corrige."""
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert isinstance(dialog.mode_paiement_combo, QComboBox)
    assert not hasattr(dialog, "mode_paiement_edit")


def test_mode_paiement_dropdown_proposes_exactly_the_reference_modes(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    modes_proposes = [dialog.mode_paiement_combo.itemData(i) for i in range(dialog.mode_paiement_combo.count())]
    assert modes_proposes == [None, *MODES_PAIEMENT]


def test_mode_paiement_defaults_to_non_precise(qtbot) -> None:
    """Préserve le comportement par défaut d'avant ce lot (champ laissé
    vide -> ``None``) : aucun mode n'est imposé sans règle métier."""
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert dialog.mode_paiement_combo.currentData() is None


def test_mode_paiement_selection_is_returned_as_plain_str(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    index = dialog.mode_paiement_combo.findData("Mobile Money")
    dialog.mode_paiement_combo.setCurrentIndex(index)

    valeur = dialog.values()["mode_paiement"]
    assert valeur == "Mobile Money"
    assert isinstance(valeur, str)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_montant_placeholder_strips_unnecessary_decimals(qtbot) -> None:
    """Lot 23 (§E) : le placeholder indicatif du montant à payer (reste à
    payer) ne doit plus afficher ``62500.00``."""
    dialog = PaymentFormDialog(Decimal("62500.00"), Decimal("0"), Decimal("62500.00"), "XOF")
    qtbot.addWidget(dialog)

    assert dialog.montant_edit.placeholderText() == "62500"


def test_values_still_returns_optional_fields_as_none_when_empty(qtbot) -> None:
    """Non-régression : le comportement de conversion (chaîne vide -> None)
    n'est pas affecté par le retrait de la mention « (optionnel) »."""
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["mode_paiement"] is None
    assert values["reference"] is None
    assert values["commentaire"] is None
