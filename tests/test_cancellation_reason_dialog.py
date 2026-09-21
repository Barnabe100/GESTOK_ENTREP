"""Dialogue de motif d'annulation — valide uniquement une longueur minimale
côté interface (confort utilisateur) ; la garantie réelle vit dans les
services concernés (voir tests/test_entry_service.py,
tests/test_exit_service.py, tests/test_sale_service.py)."""
from PySide6.QtWidgets import QDialog

from app.views.cancellation_reason_dialog import CancellationReasonDialog
from tests.ui_test_helpers import assert_field_is_marked_required, assert_has_required_field_legend


def test_reason_field_is_marked_required(qtbot) -> None:
    dialog = CancellationReasonDialog("cette opération", parent=None)
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.reason_edit)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = CancellationReasonDialog("cette opération", parent=None)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_empty_reason_is_refused(qtbot) -> None:
    dialog = CancellationReasonDialog("cette opération", parent=None)
    qtbot.addWidget(dialog)

    dialog.confirm_button.click()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.text() != ""


def test_whitespace_only_reason_is_refused(qtbot) -> None:
    dialog = CancellationReasonDialog("cette opération", parent=None)
    qtbot.addWidget(dialog)

    dialog.reason_edit.setPlainText("     ")
    dialog.confirm_button.click()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.text() != ""


def test_reason_shorter_than_minimum_is_refused(qtbot) -> None:
    dialog = CancellationReasonDialog("cette opération", parent=None)
    qtbot.addWidget(dialog)

    dialog.reason_edit.setPlainText("abcd")
    dialog.confirm_button.click()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.text() != ""


def test_valid_reason_accepts_dialog(qtbot) -> None:
    dialog = CancellationReasonDialog("cette opération", parent=None)
    qtbot.addWidget(dialog)

    dialog.reason_edit.setPlainText("Erreur de saisie de quantité")
    dialog.confirm_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.reason() == "Erreur de saisie de quantité"


def test_reason_is_trimmed(qtbot) -> None:
    dialog = CancellationReasonDialog("cette opération", parent=None)
    qtbot.addWidget(dialog)

    dialog.reason_edit.setPlainText("   Motif avec espaces   ")
    dialog.confirm_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.reason() == "Motif avec espaces"


def test_close_button_rejects_dialog(qtbot) -> None:
    dialog = CancellationReasonDialog("cette opération", parent=None)
    qtbot.addWidget(dialog)

    dialog.close_button.click()

    assert dialog.result() == QDialog.DialogCode.Rejected
