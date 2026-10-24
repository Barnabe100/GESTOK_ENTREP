from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.article_unite_dialog import ArticleUniteDialog
from tests.ui_test_helpers import assert_field_is_marked_required, assert_has_required_field_legend


def test_libelle_field_is_marked_required(qtbot) -> None:
    dialog = ArticleUniteDialog()
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.libelle_edit)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = ArticleUniteDialog()
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_dialog_save_button_accepts(qtbot) -> None:
    dialog = ArticleUniteDialog()
    qtbot.addWidget(dialog)
    dialog.libelle_edit.setText("Botte")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.libelle() == "Botte"


def test_dialog_cancel_button_rejects(qtbot) -> None:
    dialog = ArticleUniteDialog()
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_dialog_set_error_displays_message(qtbot) -> None:
    dialog = ArticleUniteDialog()
    qtbot.addWidget(dialog)

    dialog.set_error("Une unité équivalente existe déjà.")

    assert "existe déjà" in dialog.error_label.text()
