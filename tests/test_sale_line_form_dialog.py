from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.sale_line_form_dialog import SaleLineFormDialog
from tests.ui_test_helpers import assert_field_is_marked_required, assert_has_required_field_legend

_ARTICLES = [(1, "ART-1 — Eau", "800"), (2, "ART-2 — Riz", "1500")]


def test_all_fields_are_marked_required(qtbot) -> None:
    dialog = SaleLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.article_combo)
    assert_field_is_marked_required(dialog, dialog.quantite_edit)
    assert_field_is_marked_required(dialog, dialog.prix_unitaire_edit)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = SaleLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_prefills_price_from_selected_article_default(qtbot) -> None:
    dialog = SaleLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.prix_unitaire_edit.text() == "800"


def test_changing_article_updates_default_price(qtbot) -> None:
    dialog = SaleLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.article_combo.setCurrentIndex(1)

    assert dialog.prix_unitaire_edit.text() == "1500"


def test_price_remains_editable_after_prefill(qtbot) -> None:
    dialog = SaleLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.prix_unitaire_edit.setText("750")

    assert dialog.values()["prix_unitaire"] == "750"


def test_dialog_prefills_from_initial(qtbot) -> None:
    initial = {"article_id": 2, "quantite": "10", "prix_unitaire": "1400"}
    dialog = SaleLineFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["article_id"] == 2
    assert values["quantite"] == "10"
    assert values["prix_unitaire"] == "1400"


def test_save_button_accepts(qtbot) -> None:
    dialog = SaleLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog.quantite_edit.setText("5")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.values()["quantite"] == "5"


def test_cancel_button_rejects(qtbot) -> None:
    dialog = SaleLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_set_error_displays_message(qtbot) -> None:
    dialog = SaleLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.set_error("La quantité doit être positive.")

    assert "positive" in dialog.error_label.text()
