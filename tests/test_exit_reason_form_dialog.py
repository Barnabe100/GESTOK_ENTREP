from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.exit_reason_form_dialog import ExitReasonFormDialog


def test_dialog_prefills_libelle_and_description(qtbot) -> None:
    dialog = ExitReasonFormDialog("Perte", "Marchandise perdue")
    qtbot.addWidget(dialog)

    assert dialog.libelle() == "Perte"
    assert dialog.description() == "Marchandise perdue"


def test_dialog_save_button_accepts(qtbot) -> None:
    dialog = ExitReasonFormDialog()
    qtbot.addWidget(dialog)
    dialog.label_edit.setText("Casse")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.libelle() == "Casse"


def test_dialog_cancel_button_rejects(qtbot) -> None:
    dialog = ExitReasonFormDialog("Perte")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_dialog_set_error_displays_message(qtbot) -> None:
    dialog = ExitReasonFormDialog()
    qtbot.addWidget(dialog)

    dialog.set_error("Un motif équivalent existe déjà.")

    assert "existe déjà" in dialog.error_label.text()
