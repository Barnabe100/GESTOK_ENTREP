from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.exit_form_dialog import ExitFormDialog

_MOTIFS = [(1, "Perte"), (2, "Casse")]
_ARTICLES = [(10, "ART-1 — Eau", "500"), (20, "ART-2 — Riz", "1200")]


class _FakeLineDialog:
    """Remplace ExitLineFormDialog dans les tests pour éviter tout dialogue
    modal bloquant, à l'identique du monkeypatch de QMessageBox ailleurs."""

    result_values = {"article_id": 10, "quantite": "5"}
    accepted = True

    def __init__(self, articles, initial=None, parent=None) -> None:
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted if self.accepted else QDialog.DialogCode.Rejected

    def values(self):
        return self.result_values


@pytest.fixture(autouse=True)
def _no_blocking_message_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.exit_form_dialog.QMessageBox.warning", lambda *a, **k: None)


def test_dialog_prefills_header_from_initial(qtbot) -> None:
    initial = {
        "motif_id": 2, "date": "2026-01-15",
        "beneficiaire": "Service RH", "reference": "REF-1", "commentaire": "Sortie test",
    }
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["motif_id"] == 2
    assert values["date"] == "2026-01-15"
    assert values["beneficiaire"] == "Service RH"
    assert values["reference"] == "REF-1"
    assert values["commentaire"] == "Sortie test"


def test_dialog_prefills_lines_from_initial(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1 — Eau", "quantite": Decimal("10"), "cout_unitaire": Decimal("500")},
        ]
    }
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.rowCount() == 1
    assert dialog.lines_table.item(0, 0).text() == "ART-1 — Eau"
    assert dialog.lines_table.item(0, 1).text() == "10"
    assert "5000" in dialog.total_label.text()


def test_add_line_appends_row_using_cmup_from_articles_list(qtbot, monkeypatch) -> None:
    monkeypatch.setattr("app.views.exit_form_dialog.ExitLineFormDialog", _FakeLineDialog)
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    values = dialog.values()
    assert len(values["lignes"]) == 1
    assert values["lignes"][0]["article_id"] == 10
    assert values["lignes"][0]["quantite"] == Decimal("5")
    assert values["lignes"][0]["cout_unitaire"] == Decimal("500")


def test_add_line_rejects_non_positive_quantity_and_reopens(qtbot, monkeypatch) -> None:
    calls = {"n": 0}

    class _FirstBadThenGood(_FakeLineDialog):
        def values(self):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"article_id": 10, "quantite": "0"}
            return {"article_id": 10, "quantite": "5"}

    monkeypatch.setattr("app.views.exit_form_dialog.ExitLineFormDialog", _FirstBadThenGood)
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert calls["n"] == 2
    assert dialog.lines_table.rowCount() == 1


def test_remove_line_deletes_selected_row(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1", "quantite": Decimal("10"), "cout_unitaire": Decimal("500")},
            {"article_id": 20, "article_label": "ART-2", "quantite": Decimal("2"), "cout_unitaire": Decimal("1200")},
        ]
    }
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES, initial)
    qtbot.addWidget(dialog)
    dialog.lines_table.selectRow(0)

    dialog._on_remove_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    assert dialog.values()["lignes"][0]["article_id"] == 20


def test_save_button_accepts(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cancel_button_rejects(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected
