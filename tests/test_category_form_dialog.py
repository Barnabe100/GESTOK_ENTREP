from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.category_form_dialog import CategoryFormDialog


def test_dialog_prefills_name(qtbot) -> None:
    dialog = CategoryFormDialog("Boissons")
    qtbot.addWidget(dialog)
    assert dialog.name() == "Boissons"


def test_dialog_save_button_accepts(qtbot) -> None:
    dialog = CategoryFormDialog("")
    qtbot.addWidget(dialog)
    dialog.name_edit.setText("Nouvelle catégorie")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.name() == "Nouvelle catégorie"


def test_dialog_cancel_button_rejects(qtbot) -> None:
    dialog = CategoryFormDialog("Boissons")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_dialog_set_error_displays_message(qtbot) -> None:
    dialog = CategoryFormDialog("Boissons")
    qtbot.addWidget(dialog)

    dialog.set_error("Une catégorie nommée « Boissons » existe déjà.")

    assert "existe déjà" in dialog.error_label.text()
