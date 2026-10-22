"""Lot 23 (§E / extension quantités) : formatage des champs de saisie des
trois dialogues de location non couverts par un fichier de test dédié
(``LocationCautionDialog``, ``LocationPaymentFormDialog``,
``LocationLineFormDialog``) — aucune décimale superflue, aucune perte de
décimale réellement significative, aucune valeur stockée modifiée (ces
dialogues ne font que restituer une saisie en texte)."""
from decimal import Decimal

from app.views.location_caution_dialog import LocationCautionDialog
from app.views.location_line_form_dialog import LocationLineFormDialog
from app.views.location_payment_form_dialog import LocationPaymentFormDialog


def test_location_caution_dialog_montant_strips_unnecessary_decimals(qtbot) -> None:
    dialog = LocationCautionDialog(
        Decimal("10000.00"), Decimal("0"), "XOF", peut_modifier_montant=True,
    )
    qtbot.addWidget(dialog)

    assert dialog.montant_edit.text() == "10000"


def test_location_caution_dialog_preserves_real_decimal(qtbot) -> None:
    dialog = LocationCautionDialog(
        Decimal("10000.50"), Decimal("0"), "XOF", peut_modifier_montant=True,
    )
    qtbot.addWidget(dialog)

    assert dialog.montant_edit.text() == "10000.5"


def test_location_caution_dialog_no_prefill_when_restitution_mode(qtbot) -> None:
    """Non-régression : en mode restitution (``peut_modifier_montant=False``),
    le champ reste vide (saisie libre d'un montant à restituer), jamais
    pré-rempli."""
    dialog = LocationCautionDialog(
        Decimal("10000.00"), Decimal("0"), "XOF", peut_modifier_montant=False,
    )
    qtbot.addWidget(dialog)

    assert dialog.montant_edit.text() == ""


def test_location_payment_form_dialog_placeholder_strips_unnecessary_decimals(qtbot) -> None:
    dialog = LocationPaymentFormDialog(
        Decimal("62500.00"), Decimal("0"), Decimal("62500.00"), "XOF",
    )
    qtbot.addWidget(dialog)

    assert dialog.montant_edit.placeholderText() == "62500"


def test_location_line_form_dialog_quantite_prefill_strips_unnecessary_decimals(qtbot) -> None:
    articles = [(1, "ART-LOC — Tente", "500")]
    dialog = LocationLineFormDialog(articles, {"article_id": 1, "quantite": Decimal("3.000")})
    qtbot.addWidget(dialog)

    assert dialog.quantite_edit.text() == "3"


def test_location_line_form_dialog_tarif_jour_prefill_strips_unnecessary_decimals(qtbot) -> None:
    articles = [(1, "ART-LOC — Tente", "500")]
    dialog = LocationLineFormDialog(articles, {"article_id": 1, "tarif_jour": Decimal("500.00")})
    qtbot.addWidget(dialog)

    assert dialog.tarif_jour_edit.text() == "500"


def test_location_line_form_dialog_tarif_jour_from_article_selection(qtbot) -> None:
    """Le tarif pré-rempli depuis la sélection d'un article (tuple construit
    par ``LocationsPage._load_articles_for_form``) ne doit plus afficher de
    ``.00`` superflu."""
    articles = [(1, "ART-LOC — Tente", "7500")]
    dialog = LocationLineFormDialog(articles)
    qtbot.addWidget(dialog)

    assert dialog.tarif_jour_edit.text() == "7500"
