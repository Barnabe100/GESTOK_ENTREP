from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDateEdit, QDialog

from app.views.entry_form_dialog import EntryFormDialog
from tests.ui_test_helpers import (
    assert_field_is_marked_required,
    assert_field_is_not_marked_required,
    assert_has_required_field_legend,
)

_SUPPLIERS = [(1, "Fournisseur A"), (2, "Fournisseur B")]
_ARTICLES = [(10, "ART-1 — Eau", "500"), (20, "ART-2 — Riz", "1200")]


def test_required_fields_are_marked_required(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.supplier_combo)
    assert_field_is_marked_required(dialog, dialog.date_edit)


def test_optional_fields_are_not_marked_required(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert_field_is_not_marked_required(dialog, dialog.reference_document_edit)
    assert_field_is_not_marked_required(dialog, dialog.commentaire_edit)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


class _FakeLineDialog:
    """Remplace EntryLineFormDialog dans les tests pour éviter tout dialogue
    modal bloquant, à l'identique du monkeypatch de QMessageBox ailleurs."""

    result_values = {"article_id": 10, "quantite": "5", "prix_unitaire": "500"}
    accepted = True

    def __init__(self, articles, initial=None, parent=None) -> None:
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted if self.accepted else QDialog.DialogCode.Rejected

    def values(self):
        return self.result_values


@pytest.fixture(autouse=True)
def _no_blocking_message_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.entry_form_dialog.QMessageBox.warning", lambda *a, **k: None)


def test_dialog_uses_qdateedit_with_calendar_popup(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert isinstance(dialog.date_edit, QDateEdit)
    assert dialog.date_edit.calendarPopup() is True
    assert dialog.date_edit.displayFormat() == "yyyy-MM-dd"


def test_dialog_defaults_date_to_today_on_creation(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.date_edit.date() == QDate.currentDate()
    assert dialog.values()["date"] == date.today()


def test_dialog_date_edit_cannot_be_set_beyond_today(qtbot) -> None:
    """Confort d'interface (§ dates futures) : le calendrier ne doit pas
    permettre de sélectionner une date future — la garantie réelle reste
    portée par EntryService (voir tests/test_business_date_validation.py)."""
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.date_edit.maximumDate() == QDate.currentDate()

    dialog.date_edit.setDate(QDate.currentDate().addDays(5))
    assert dialog.date_edit.date() == QDate.currentDate()  # clampé par Qt, jamais une date future


def test_dialog_date_change_is_reflected_in_values(qtbot) -> None:
    initial = {"date": date(2026, 1, 15)}
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    dialog.date_edit.setDate(QDate(2026, 3, 1))

    assert dialog.values()["date"] == date(2026, 3, 1)
    assert isinstance(dialog.values()["date"], date)


def test_dialog_prefills_header_from_initial(qtbot) -> None:
    initial = {
        "fournisseur_id": 2, "date": date(2026, 1, 15),
        "reference_document": "BL-42", "commentaire": "Livraison test",
    }
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["fournisseur_id"] == 2
    assert values["date"] == date(2026, 1, 15)
    assert dialog.date_edit.date() == QDate(2026, 1, 15)
    assert values["reference_document"] == "BL-42"
    assert values["commentaire"] == "Livraison test"


def test_dialog_prefills_lines_from_initial(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1 — Eau", "quantite": Decimal("10"), "prix_unitaire": Decimal("500")},
        ]
    }
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.rowCount() == 1
    assert dialog.lines_table.item(0, 0).text() == "ART-1 — Eau"
    assert dialog.lines_table.item(0, 1).text() == "10"
    assert "5000" in dialog.total_label.text() or "5000.0" in dialog.total_label.text()


def test_dialog_prefills_lines_preserve_real_decimal_quantity(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1 — Eau", "quantite": Decimal("10.500"), "prix_unitaire": Decimal("500")},
        ]
    }
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.item(0, 1).text() == "10,5"


def test_add_line_appends_row_and_updates_total(qtbot, monkeypatch) -> None:
    monkeypatch.setattr("app.views.entry_form_dialog.EntryLineFormDialog", _FakeLineDialog)
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    values = dialog.values()
    assert len(values["lignes"]) == 1
    assert values["lignes"][0]["article_id"] == 10
    assert values["lignes"][0]["quantite"] == Decimal("5")
    assert values["lignes"][0]["prix_unitaire"] == Decimal("500")


def test_add_line_rejects_non_positive_quantity_and_reopens(qtbot, monkeypatch) -> None:
    calls = {"n": 0}

    class _FirstBadThenGood(_FakeLineDialog):
        def values(self):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"article_id": 10, "quantite": "0", "prix_unitaire": "500"}
            return {"article_id": 10, "quantite": "5", "prix_unitaire": "500"}

    monkeypatch.setattr("app.views.entry_form_dialog.EntryLineFormDialog", _FirstBadThenGood)
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert calls["n"] == 2
    assert dialog.lines_table.rowCount() == 1


def test_remove_line_deletes_selected_row(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1", "quantite": Decimal("10"), "prix_unitaire": Decimal("500")},
            {"article_id": 20, "article_label": "ART-2", "quantite": Decimal("2"), "prix_unitaire": Decimal("1200")},
        ]
    }
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES, initial)
    qtbot.addWidget(dialog)
    dialog.lines_table.selectRow(0)

    dialog._on_remove_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    assert dialog.values()["lignes"][0]["article_id"] == 20


def test_save_button_accepts(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cancel_button_rejects(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected
