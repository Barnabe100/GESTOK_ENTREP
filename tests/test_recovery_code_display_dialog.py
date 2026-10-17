from PySide6.QtCore import Qt

from app.views.recovery_code_display_dialog import RecoveryCodeDisplayDialog


def test_displays_the_code_in_a_read_only_field(qtbot) -> None:
    dialog = RecoveryCodeDisplayDialog("mon-code-secret")
    qtbot.addWidget(dialog)

    assert dialog.code_edit.text() == "mon-code-secret"
    assert dialog.code_edit.isReadOnly() is True


def test_copy_button_puts_code_on_clipboard(qtbot):
    from PySide6.QtWidgets import QApplication

    dialog = RecoveryCodeDisplayDialog("mon-code-secret")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.copy_button, Qt.MouseButton.LeftButton)

    clipboard = QApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text() == "mon-code-secret"


def test_close_button_accepts_dialog(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = RecoveryCodeDisplayDialog("mon-code-secret")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
