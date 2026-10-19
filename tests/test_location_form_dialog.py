from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.location_form_dialog import LocationFormDialog

_ARTICLES = [(10, "ART-1 — Tente", "5000")]
_CLIENTS = [(1, "Client Alpha"), (2, "Client Beta")]


# -- Lot 11 : validation directe (bouton « Valider ») -------------------------
#
# Pour Location, « Valider » ne déclenche que LocationService.confirm_location
# (voir LocationsPage._submit_form) — jamais depart_location, qui exige une
# date de départ absente de ce formulaire.

def test_buttons_are_ordered_annuler_brouillon_valider(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    assert dialog.cancel_button.text() == "Annuler"
    assert dialog.save_button.text() == "Enregistrer en brouillon"
    assert dialog.validate_button.text() == "Valider"


def test_requested_action_defaults_to_draft(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    assert dialog.requested_action() == "draft"


def test_save_button_accepts_with_draft_action(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.requested_action() == "draft"


def test_validate_button_accepts_with_validate_action(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.requested_action() == "validate"


def test_validate_button_click_disables_save_and_validate_buttons(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)

    assert dialog.save_button.isEnabled() is False
    assert dialog.validate_button.isEnabled() is False
