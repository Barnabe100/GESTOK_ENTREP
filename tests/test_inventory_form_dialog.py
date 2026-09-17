from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.inventory_form_dialog import InventoryFormDialog

_ARTICLES = [(10, "ART-1 — Eau", "100"), (20, "ART-2 — Riz", "50")]


class _FakeLineDialog:
    """Remplace InventoryLineFormDialog dans les tests pour éviter tout
    dialogue modal bloquant, à l'identique du monkeypatch de QMessageBox
    ailleurs."""

    result_values = {"article_id": 10, "stock_physique": "97"}
    accepted = True

    def __init__(self, articles, initial=None, parent=None) -> None:
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted if self.accepted else QDialog.DialogCode.Rejected

    def values(self):
        return self.result_values


@pytest.fixture(autouse=True)
def _no_blocking_message_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.inventory_form_dialog.QMessageBox.warning", lambda *a, **k: None)


def test_dialog_prefills_date_from_initial(qtbot) -> None:
    initial = {"date": "2026-01-15"}
    dialog = InventoryFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.values()["date"] == "2026-01-15"


def test_dialog_prefills_lines_from_initial_with_ecart_column(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1 — Eau", "stock_theorique": Decimal("100"), "stock_physique": Decimal("97")},
        ]
    }
    dialog = InventoryFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.rowCount() == 1
    assert dialog.lines_table.item(0, 0).text() == "ART-1 — Eau"
    assert dialog.lines_table.item(0, 1).text() == "100"
    assert dialog.lines_table.item(0, 2).text() == "97"
    assert dialog.lines_table.item(0, 3).text() == "-3"


def test_add_line_appends_row_using_stock_theorique_from_articles_list(qtbot, monkeypatch) -> None:
    monkeypatch.setattr("app.views.inventory_form_dialog.InventoryLineFormDialog", _FakeLineDialog)
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    values = dialog.values()
    assert len(values["lignes"]) == 1
    assert values["lignes"][0]["article_id"] == 10
    assert values["lignes"][0]["stock_theorique"] == Decimal("100")
    assert values["lignes"][0]["stock_physique"] == Decimal("97")


def test_add_line_rejects_negative_stock_physique_and_reopens(qtbot, monkeypatch) -> None:
    calls = {"n": 0}

    class _FirstBadThenGood(_FakeLineDialog):
        def values(self):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"article_id": 10, "stock_physique": "-1"}
            return {"article_id": 10, "stock_physique": "97"}

    monkeypatch.setattr("app.views.inventory_form_dialog.InventoryLineFormDialog", _FirstBadThenGood)
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert calls["n"] == 2
    assert dialog.lines_table.rowCount() == 1


def test_add_line_accepts_zero_stock_physique(qtbot, monkeypatch) -> None:
    class _ZeroLine(_FakeLineDialog):
        result_values = {"article_id": 10, "stock_physique": "0"}

    monkeypatch.setattr("app.views.inventory_form_dialog.InventoryLineFormDialog", _ZeroLine)
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    assert dialog.values()["lignes"][0]["stock_physique"] == Decimal("0")


def test_remove_line_deletes_selected_row(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1", "stock_theorique": Decimal("100"), "stock_physique": Decimal("97")},
            {"article_id": 20, "article_label": "ART-2", "stock_theorique": Decimal("50"), "stock_physique": Decimal("55")},
        ]
    }
    dialog = InventoryFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)
    dialog.lines_table.selectRow(0)

    dialog._on_remove_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    assert dialog.values()["lignes"][0]["article_id"] == 20


def test_save_button_accepts(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cancel_button_rejects(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected
