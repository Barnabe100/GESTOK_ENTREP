from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.supplier_form_dialog import SupplierFormDialog
from tests.ui_test_helpers import (
    assert_field_is_marked_required,
    assert_field_is_not_marked_required,
    assert_has_required_field_legend,
)


def test_name_field_is_marked_required(qtbot) -> None:
    dialog = SupplierFormDialog()
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.name_edit)


def test_optional_fields_are_not_marked_required(qtbot) -> None:
    dialog = SupplierFormDialog()
    qtbot.addWidget(dialog)

    for field in (
        dialog.contact_edit, dialog.telephone_edit, dialog.email_edit,
        dialog.adresse_edit, dialog.ville_edit, dialog.pays_edit, dialog.observations_edit,
    ):
        assert_field_is_not_marked_required(dialog, field)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = SupplierFormDialog()
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_dialog_prefills_all_fields(qtbot) -> None:
    initial = {
        "nom": "Fournisseur",
        "contact": "Jean",
        "telephone": "0102030405",
        "email": "jean@example.com",
        "adresse": "1 rue X",
        "ville": "Lyon",
        "pays": "France",
        "observations": "Note",
    }
    dialog = SupplierFormDialog(initial)
    qtbot.addWidget(dialog)

    values = dialog.values()
    for key, value in initial.items():
        assert values[key] == value


def test_dialog_empty_initial_gives_empty_fields(qtbot) -> None:
    dialog = SupplierFormDialog()
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["nom"] == ""
    assert values["email"] == ""


def test_dialog_save_button_accepts(qtbot) -> None:
    dialog = SupplierFormDialog()
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("Nouveau fournisseur")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.values()["nom"] == "Nouveau fournisseur"


def test_dialog_cancel_button_rejects(qtbot) -> None:
    dialog = SupplierFormDialog({"nom": "Fournisseur"})
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_dialog_set_error_displays_message(qtbot) -> None:
    dialog = SupplierFormDialog()
    qtbot.addWidget(dialog)

    dialog.set_error("L'adresse email n'est pas valide.")

    assert "email" in dialog.error_label.text()
