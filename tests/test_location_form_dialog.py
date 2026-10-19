from datetime import date
from decimal import Decimal

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


# -- Lot 13 : client facultatif + création rapide ----------------------------

def test_client_combo_defaults_to_none(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    assert dialog.values()["client_id"] is None


def test_client_combo_has_no_client_option_first(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    labels = {dialog.client_combo.itemText(i) for i in range(dialog.client_combo.count())}
    assert labels == {"(Aucun client)", "Client Alpha", "Client Beta"}


def test_client_field_is_not_marked_required(qtbot) -> None:
    """Le client est facultatif (lot « Client facultatif... ») — son
    libellé ne doit porter aucun « * »."""
    from PySide6.QtWidgets import QFormLayout

    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    form = dialog.findChild(QFormLayout)
    client_row_index = None
    for i in range(form.rowCount()):
        field_item = form.itemAt(i, QFormLayout.ItemRole.FieldRole)
        if field_item is not None and field_item.widget() is None and field_item.layout() is not None:
            # client_row est un QHBoxLayout imbriqué contenant le combo client
            layout = field_item.layout()
            if layout.indexOf(dialog.client_combo) != -1:
                client_row_index = i
    assert client_row_index is not None
    label_item = form.itemAt(client_row_index, QFormLayout.ItemRole.LabelRole)
    assert "*" not in label_item.widget().text()


def test_client_combo_preselects_existing_client(qtbot) -> None:
    initial = {"client_id": 2}
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS, initial)
    qtbot.addWidget(dialog)

    assert dialog.values()["client_id"] == 2
    assert dialog.client_combo.currentText() == "Client Beta"


def test_new_client_button_disabled_without_callback(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    assert dialog.new_client_button.isEnabled() is False


def test_new_client_button_creates_and_selects_client_without_losing_data(qtbot) -> None:
    """§5 du lot : le bouton « Nouveau client… » ne doit jamais faire
    perdre les données déjà saisies (date, lignes, tarif)."""
    initial = {
        "date": date(2026, 1, 15),
        "lignes": [
            {"article_id": 10, "article_label": "ART-1 — Tente", "quantite": Decimal("2"), "tarif_jour": Decimal("5000")},
        ],
    }

    def on_create_client():
        return (99, "Client tout neuf")

    dialog = LocationFormDialog(_ARTICLES, _CLIENTS, initial, on_create_client=on_create_client)
    qtbot.addWidget(dialog)

    assert dialog.new_client_button.isEnabled() is True
    dialog._on_new_client_clicked()

    assert dialog.values()["client_id"] == 99
    assert dialog.client_combo.currentText() == "Client tout neuf"
    assert dialog.values()["date"] == date(2026, 1, 15)
    assert len(dialog.values()["lignes"]) == 1
    assert dialog.values()["lignes"][0]["article_id"] == 10
    assert dialog.values()["lignes"][0]["tarif_jour"] == Decimal("5000")


def test_new_client_button_cancelled_keeps_current_selection(qtbot) -> None:
    def on_create_client():
        return None  # l'utilisateur a annulé le sous-formulaire client

    dialog = LocationFormDialog(_ARTICLES, _CLIENTS, {"client_id": 1}, on_create_client=on_create_client)
    qtbot.addWidget(dialog)

    dialog._on_new_client_clicked()

    assert dialog.values()["client_id"] == 1


def test_new_client_button_without_callback_result_is_noop(qtbot) -> None:
    dialog = LocationFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    dialog._on_new_client_clicked()  # aucun callback : ne doit rien faire ni lever

    assert dialog.values()["client_id"] is None
