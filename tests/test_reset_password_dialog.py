"""Dialogue de réinitialisation de mot de passe — valide uniquement la
correspondance des deux champs saisis, aucune logique métier (voir
app/views/reset_password_dialog.py)."""
from PySide6.QtWidgets import QDialog

from app.views.reset_password_dialog import ResetPasswordDialog


def test_matching_passwords_accept_dialog(qtbot) -> None:
    dialog = ResetPasswordDialog()
    qtbot.addWidget(dialog)

    dialog.password_edit.setText("NouveauMotDePasse99")
    dialog.confirm_password_edit.setText("NouveauMotDePasse99")

    dialog.submit_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.password() == "NouveauMotDePasse99"


def test_mismatched_passwords_show_error_and_do_not_accept(qtbot) -> None:
    dialog = ResetPasswordDialog()
    qtbot.addWidget(dialog)

    dialog.password_edit.setText("NouveauMotDePasse99")
    dialog.confirm_password_edit.setText("Different99")

    dialog.submit_button.click()

    assert dialog.error_label.text() != ""
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_password_field_uses_masked_echo_mode(qtbot) -> None:
    dialog = ResetPasswordDialog()
    qtbot.addWidget(dialog)

    from PySide6.QtWidgets import QLineEdit

    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.confirm_password_edit.echoMode() == QLineEdit.EchoMode.Password


def test_set_error_displays_service_message(qtbot) -> None:
    dialog = ResetPasswordDialog()
    qtbot.addWidget(dialog)

    dialog.set_error("Le mot de passe doit contenir au moins 8 caractères.")

    assert dialog.error_label.text() == "Le mot de passe doit contenir au moins 8 caractères."
