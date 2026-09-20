from PySide6.QtWidgets import QDialog

from app.views.data_reset_confirm_dialog import DataResetConfirmDialog


def test_confirm_button_disabled_by_default(qtbot) -> None:
    dialog = DataResetConfirmDialog()
    qtbot.addWidget(dialog)

    assert dialog.confirm_button.isEnabled() is False


def test_confirm_button_disabled_with_wrong_text(qtbot) -> None:
    dialog = DataResetConfirmDialog()
    qtbot.addWidget(dialog)

    dialog.confirmation_edit.setText("reinitialiser")  # mauvaise casse / sans accent

    assert dialog.confirm_button.isEnabled() is False


def test_confirm_button_enabled_with_exact_phrase(qtbot) -> None:
    dialog = DataResetConfirmDialog()
    qtbot.addWidget(dialog)

    dialog.confirmation_edit.setText("RÉINITIALISER")

    assert dialog.confirm_button.isEnabled() is True


def test_confirm_button_click_accepts_dialog(qtbot) -> None:
    dialog = DataResetConfirmDialog()
    qtbot.addWidget(dialog)
    dialog.confirmation_edit.setText("RÉINITIALISER")

    dialog.confirm_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cancel_button_rejects_dialog(qtbot) -> None:
    dialog = DataResetConfirmDialog()
    qtbot.addWidget(dialog)

    dialog.cancel_button.click()

    assert dialog.result() == QDialog.DialogCode.Rejected
