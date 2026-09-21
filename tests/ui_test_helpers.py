"""Petits utilitaires partagés pour vérifier le rendu réel des formulaires
PySide6 (convention « champ obligatoire = * », voir app.views.common) — pas
de recherche de chaîne dans le code source, uniquement l'état effectif des
widgets une fois le dialogue construit."""
from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from app.views.common import REQUIRED_FIELD_LEGEND


def field_label_text(dialog: QWidget, field_widget) -> str:
    """Texte réel du libellé associé à ``field_widget``, cherché dans tous
    les ``QFormLayout`` sous ``dialog`` (certains dialogues, ex. paiement,
    en comportent plusieurs — un bloc d'informations en lecture seule et le
    formulaire de saisie proprement dit) — reflète ce que l'utilisateur voit
    réellement à l'écran, jamais une simple recherche de chaîne."""
    forms = dialog.findChildren(QFormLayout)
    assert forms, "Aucun QFormLayout trouvé dans ce dialogue."
    for form in forms:
        label = form.labelForField(field_widget)
        if label is not None:
            return label.text()
    raise AssertionError(f"Aucun libellé associé à {field_widget!r}.")


def required_field_legend_text(dialog: QWidget) -> str | None:
    """Texte de la légende commune « * Champ obligatoire », ou ``None`` si
    absente du dialogue."""
    legend = dialog.findChild(QLabel, "requiredFieldLegend")
    return legend.text() if legend is not None else None


def assert_field_is_marked_required(dialog: QWidget, field_widget) -> None:
    text = field_label_text(dialog, field_widget)
    assert text.rstrip().endswith("*"), f"Champ obligatoire non marqué d'un « * » : {text!r}"


def assert_field_is_not_marked_required(dialog: QWidget, field_widget) -> None:
    text = field_label_text(dialog, field_widget)
    assert not text.rstrip().endswith("*"), f"Champ facultatif marqué à tort d'un « * » : {text!r}"


def assert_has_required_field_legend(dialog: QWidget) -> None:
    assert required_field_legend_text(dialog) == REQUIRED_FIELD_LEGEND
