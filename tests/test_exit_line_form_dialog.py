from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.exit_line_form_dialog import ExitLineFormDialog
from tests.ui_test_helpers import assert_field_is_marked_required, assert_has_required_field_legend

_ARTICLES = [(1, "ART-1 — Eau", "500"), (2, "ART-2 — Riz", "1200")]


def test_article_and_quantite_are_marked_required(qtbot) -> None:
    dialog = ExitLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.article_combo)
    assert_field_is_marked_required(dialog, dialog.quantite_edit)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = ExitLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_shows_cmup_for_selected_article_as_readonly(qtbot) -> None:
    dialog = ExitLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.cmup_label.text() == "500"


def test_changing_article_updates_cmup_label(qtbot) -> None:
    dialog = ExitLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.article_combo.setCurrentIndex(1)

    assert dialog.cmup_label.text() == "1200"


def test_dialog_prefills_from_initial(qtbot) -> None:
    initial = {"article_id": 2, "quantite": "10"}
    dialog = ExitLineFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["article_id"] == 2
    assert values["quantite"] == "10"


def test_values_never_includes_a_cout_unitaire_field(qtbot) -> None:
    """Le coût n'est jamais une saisie utilisateur pour une sortie (§6)."""
    dialog = ExitLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert "cout_unitaire" not in dialog.values()


def test_save_button_accepts(qtbot) -> None:
    dialog = ExitLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog.quantite_edit.setText("5")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.values()["quantite"] == "5"


def test_cancel_button_rejects(qtbot) -> None:
    dialog = ExitLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_set_error_displays_message(qtbot) -> None:
    dialog = ExitLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.set_error("La quantité doit être positive.")

    assert "positive" in dialog.error_label.text()
