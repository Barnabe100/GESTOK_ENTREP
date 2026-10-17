from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.account_recovery_dialog import AccountRecoveryDialog
from app.views.password_line_edit import PasswordLineEdit


def test_fields_use_password_line_edit_for_code_and_passwords(qtbot) -> None:
    dialog = AccountRecoveryDialog()
    qtbot.addWidget(dialog)

    assert isinstance(dialog.code_edit, PasswordLineEdit)
    assert isinstance(dialog.new_password_edit, PasswordLineEdit)
    assert isinstance(dialog.confirm_password_edit, PasswordLineEdit)


def test_initial_username_is_prefilled(qtbot) -> None:
    dialog = AccountRecoveryDialog(initial_username="admin")
    qtbot.addWidget(dialog)

    assert dialog.username() == "admin"


def test_accessors_return_entered_values(qtbot) -> None:
    dialog = AccountRecoveryDialog()
    qtbot.addWidget(dialog)

    dialog.username_edit.setText("  admin  ")
    dialog.code_edit.setText("le-code")
    dialog.new_password_edit.setText("NouveauMotDePasse!1")

    assert dialog.username() == "admin"
    assert dialog.code() == "le-code"
    assert dialog.new_password() == "NouveauMotDePasse!1"


def test_mismatched_passwords_block_submission(qtbot) -> None:
    dialog = AccountRecoveryDialog()
    qtbot.addWidget(dialog)

    dialog.username_edit.setText("admin")
    dialog.code_edit.setText("le-code")
    dialog.new_password_edit.setText("MotDePasse!1")
    dialog.confirm_password_edit.setText("Autre!2")

    qtbot.mouseClick(dialog.submit_button, Qt.MouseButton.LeftButton)

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "correspondent" in dialog.error_label.text().lower()


def test_matching_passwords_accept_dialog(qtbot) -> None:
    dialog = AccountRecoveryDialog()
    qtbot.addWidget(dialog)

    dialog.username_edit.setText("admin")
    dialog.code_edit.setText("le-code")
    dialog.new_password_edit.setText("MotDePasse!1")
    dialog.confirm_password_edit.setText("MotDePasse!1")

    qtbot.mouseClick(dialog.submit_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_set_error_displays_message(qtbot) -> None:
    dialog = AccountRecoveryDialog()
    qtbot.addWidget(dialog)

    dialog.set_error("Code invalide.")

    assert dialog.error_label.text() == "Code invalide."
