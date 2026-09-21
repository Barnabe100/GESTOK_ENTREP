from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.exit_reason_form_dialog import ExitReasonFormDialog
from tests.ui_test_helpers import (
    assert_field_is_marked_required,
    assert_field_is_not_marked_required,
    assert_has_required_field_legend,
)


def test_libelle_field_is_marked_required(qtbot) -> None:
    dialog = ExitReasonFormDialog()
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.label_edit)


def test_description_field_is_not_marked_required(qtbot) -> None:
    dialog = ExitReasonFormDialog()
    qtbot.addWidget(dialog)

    assert_field_is_not_marked_required(dialog, dialog.description_edit)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = ExitReasonFormDialog()
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


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
