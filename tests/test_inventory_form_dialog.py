from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDateEdit, QDialog

from app.views.inventory_form_dialog import InventoryFormDialog
from tests.ui_test_helpers import assert_field_is_marked_required, assert_has_required_field_legend

_ARTICLES = [(10, "ART-1 — Eau", "100"), (20, "ART-2 — Riz", "50")]


def test_date_field_is_marked_required(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.date_edit)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


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


def test_dialog_uses_qdateedit_with_calendar_popup(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert isinstance(dialog.date_edit, QDateEdit)
    assert dialog.date_edit.calendarPopup() is True
    assert dialog.date_edit.displayFormat() == "yyyy-MM-dd"


def test_dialog_defaults_date_to_today_on_creation(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.date_edit.date() == QDate.currentDate()
    assert dialog.values()["date"] == date.today()


def test_dialog_date_edit_cannot_be_set_beyond_today(qtbot) -> None:
    """Confort d'interface (§ dates futures) : le calendrier ne doit pas
    permettre de sélectionner une date future — la garantie réelle reste
    portée par InventoryService (voir tests/test_business_date_validation.py)."""
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.date_edit.maximumDate() == QDate.currentDate()

    dialog.date_edit.setDate(QDate.currentDate().addDays(5))
    assert dialog.date_edit.date() == QDate.currentDate()  # clampé par Qt, jamais une date future


def test_dialog_prefills_date_from_initial(qtbot) -> None:
    initial = {"date": date(2026, 1, 15)}
    dialog = InventoryFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.date_edit.date() == QDate(2026, 1, 15)
    assert dialog.values()["date"] == date(2026, 1, 15)


def test_dialog_date_change_is_reflected_in_values(qtbot) -> None:
    initial = {"date": date(2026, 1, 15)}
    dialog = InventoryFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)

    dialog.date_edit.setDate(QDate(2026, 3, 1))

    assert dialog.values()["date"] == date(2026, 3, 1)
    assert isinstance(dialog.values()["date"], date)


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


def test_dialog_prefills_lines_preserve_real_decimal_precision(qtbot) -> None:
    initial = {
        "lignes": [
            {
                "article_id": 10, "article_label": "ART-1 — Eau",
                "stock_theorique": Decimal("10.500"), "stock_physique": Decimal("12.000"),
            },
        ]
    }
    dialog = InventoryFormDialog(_ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.item(0, 1).text() == "10,5"  # décimale réelle conservée
    assert dialog.lines_table.item(0, 2).text() == "12"  # jamais "12.000"
    assert dialog.lines_table.item(0, 3).text() == "+1,5"  # écart signé, décimale conservée

    # non-régression : la valeur interne réellement soumise reste un Decimal exact,
    # jamais la chaîne d'affichage formatée avec virgule.
    assert dialog.values()["lignes"][0]["stock_theorique"] == Decimal("10.500")
    assert dialog.values()["lignes"][0]["stock_physique"] == Decimal("12.000")


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


# -- scan code-barres (lecteur USB « keyboard wedge ») -----------------------------
#
# Le matériel physique n'est jamais disponible en test : ces cas simulent
# l'entrée clavier produite par un scanner (texte tapé puis Entrée), sans
# jamais prétendre tester un vrai lecteur USB.


def test_scan_disabled_without_lookup_callback(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.scan_edit.isEnabled() is False


def test_scan_known_barcode_preselects_article_in_line_dialog(qtbot, monkeypatch) -> None:
    captured_initial = {}

    class _CapturingLineDialog(_FakeLineDialog):
        def __init__(self, articles, initial=None, parent=None) -> None:
            captured_initial.update(initial or {})
            super().__init__(articles, initial, parent)

    monkeypatch.setattr("app.views.inventory_form_dialog.InventoryLineFormDialog", _CapturingLineDialog)
    dialog = InventoryFormDialog(_ARTICLES, on_lookup_barcode=lambda code: (10, "ART-1 — Eau", "100"))
    qtbot.addWidget(dialog)

    qtbot.keyClicks(dialog.scan_edit, "1234567890123")
    qtbot.keyClick(dialog.scan_edit, Qt.Key.Key_Return)

    assert captured_initial.get("article_id") == 10
    assert dialog.lines_table.rowCount() == 1
    assert dialog.scan_edit.text() == ""


def test_scan_unknown_barcode_opens_no_line_dialog_and_warns(qtbot, monkeypatch) -> None:
    warnings: list[tuple] = []
    monkeypatch.setattr(
        "app.views.inventory_form_dialog.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    line_dialog_calls = {"n": 0}

    class _ShouldNotOpen(_FakeLineDialog):
        def __init__(self, articles, initial=None, parent=None) -> None:
            line_dialog_calls["n"] += 1
            super().__init__(articles, initial, parent)

    monkeypatch.setattr("app.views.inventory_form_dialog.InventoryLineFormDialog", _ShouldNotOpen)
    dialog = InventoryFormDialog(_ARTICLES, on_lookup_barcode=lambda code: None)
    qtbot.addWidget(dialog)

    qtbot.keyClicks(dialog.scan_edit, "0000000000000")
    qtbot.keyClick(dialog.scan_edit, Qt.Key.Key_Return)

    assert line_dialog_calls["n"] == 0
    assert dialog.lines_table.rowCount() == 0
    assert len(warnings) == 1


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
