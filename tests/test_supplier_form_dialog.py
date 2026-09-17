from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.supplier_form_dialog import SupplierFormDialog


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
