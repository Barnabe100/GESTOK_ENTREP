from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.inventory_line_form_dialog import InventoryLineFormDialog

_ARTICLES = [(1, "ART-1 — Eau", "100"), (2, "ART-2 — Riz", "50")]


def test_shows_stock_theorique_for_selected_article_as_readonly(qtbot) -> None:
    dialog = InventoryLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.stock_theorique_label.text() == "100"


def test_changing_article_updates_stock_theorique_label(qtbot) -> None:
    dialog = InventoryLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.article_combo.setCurrentIndex(1)

    assert dialog.stock_theorique_label.text() == "50"


def test_ecart_label_updates_live_as_stock_physique_changes(qtbot) -> None:
    dialog = InventoryLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.stock_physique_edit.setText("97")

    assert dialog.ecart_label.text() == "-3"


def test_ecart_label_shows_positive_sign(qtbot) -> None:
    dialog = InventoryLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.stock_physique_edit.setText("105")

    assert dialog.ecart_label.text() == "+5"


def test_stock_theorique_label_strips_unnecessary_decimals(qtbot) -> None:
    articles = [(1, "ART-1 — Eau", "100.000")]
    dialog = InventoryLineFormDialog(articles)
    qtbot.addWidget(dialog)

    assert dialog.stock_theorique_label.text() == "100"  # jamais "100.000"


def test_stock_theorique_label_preserves_real_decimal(qtbot) -> None:
    articles = [(1, "ART-1 — Eau", "10.500")]
    dialog = InventoryLineFormDialog(articles)
    qtbot.addWidget(dialog)

    assert dialog.stock_theorique_label.text() == "10,5"


def test_ecart_computation_is_not_broken_by_decimal_display_formatting(qtbot) -> None:
    """Non-régression : la chaîne transportée dans la donnée du combo reste
    un nombre brut (jamais reformatée avec virgule), pour que le parsing
    interne (``Decimal(str(data[1]))``) continue de fonctionner — seul
    l'affichage final est formaté."""
    articles = [(1, "ART-1 — Eau", "10.500")]
    dialog = InventoryLineFormDialog(articles)
    qtbot.addWidget(dialog)

    dialog.stock_physique_edit.setText("12")

    assert dialog.ecart_label.text() == "+1,5"


def test_dialog_prefills_from_initial(qtbot) -> None:
    initial = {"article_id": 2, "stock_physique": "48"}
    dialog = InventoryLineFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["article_id"] == 2
    assert values["stock_physique"] == "48"


def test_values_never_includes_stock_theorique_field(qtbot) -> None:
    """Le stock théorique n'est jamais une saisie utilisateur."""
    dialog = InventoryLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert "stock_theorique" not in dialog.values()


def test_save_button_accepts(qtbot) -> None:
    dialog = InventoryLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog.stock_physique_edit.setText("97")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.values()["stock_physique"] == "97"


def test_cancel_button_rejects(qtbot) -> None:
    dialog = InventoryLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_set_error_displays_message(qtbot) -> None:
    dialog = InventoryLineFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.set_error("Le stock compté ne peut pas être négatif.")

    assert "négatif" in dialog.error_label.text()
