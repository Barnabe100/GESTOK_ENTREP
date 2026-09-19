from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.sale_form_dialog import SaleFormDialog

_ARTICLES = [(10, "ART-1 — Eau", "800"), (20, "ART-2 — Riz", "1500")]
_CLIENTS = [(1, "Client Alpha"), (2, "Client Beta")]


class _FakeLineDialog:
    """Remplace SaleLineFormDialog dans les tests pour éviter tout dialogue
    modal bloquant, à l'identique du monkeypatch de QMessageBox ailleurs."""

    result_values = {"article_id": 10, "quantite": "5", "prix_unitaire": "800"}
    accepted = True

    def __init__(self, articles, initial=None, parent=None) -> None:
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted if self.accepted else QDialog.DialogCode.Rejected

    def values(self):
        return self.result_values


@pytest.fixture(autouse=True)
def _no_blocking_message_boxes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.sale_form_dialog.QMessageBox.warning", lambda *a, **k: None)


def test_dialog_prefills_date_from_initial(qtbot) -> None:
    initial = {"date": "2026-01-15"}
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS, initial)
    qtbot.addWidget(dialog)

    assert dialog.values()["date"] == "2026-01-15"


def test_dialog_header_fields_are_date_and_client(qtbot) -> None:
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    assert set(dialog.values().keys()) == {"date", "client_id", "lignes"}


def test_dialog_defaults_to_no_client(qtbot) -> None:
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    assert dialog.values()["client_id"] is None
    assert dialog.client_combo.currentText() == "(Aucun client / Vente comptant)"


def test_dialog_prefills_client_from_initial(qtbot) -> None:
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS, {"client_id": 2})
    qtbot.addWidget(dialog)

    assert dialog.values()["client_id"] == 2
    assert dialog.client_combo.currentText() == "Client Beta"


def test_dialog_client_combo_lists_all_provided_clients(qtbot) -> None:
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    labels = {dialog.client_combo.itemText(i) for i in range(dialog.client_combo.count())}
    assert labels == {"(Aucun client / Vente comptant)", "Client Alpha", "Client Beta"}


def test_new_client_button_disabled_without_callback(qtbot) -> None:
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    assert dialog.new_client_button.isEnabled() is False


def test_new_client_button_creates_and_selects_client_without_losing_lines(qtbot) -> None:
    """§5 : le bouton « Nouveau client » ne doit jamais faire perdre les
    données déjà saisies dans la vente (ici : une ligne déjà ajoutée)."""
    initial = {
        "date": "2026-01-15",
        "lignes": [
            {"article_id": 10, "article_label": "ART-1 — Eau", "quantite": Decimal("3"), "prix_unitaire": Decimal("800")},
        ],
    }

    def on_create_client():
        return (99, "Client tout neuf")

    dialog = SaleFormDialog(_ARTICLES, _CLIENTS, initial, on_create_client=on_create_client)
    qtbot.addWidget(dialog)

    assert dialog.new_client_button.isEnabled() is True
    dialog._on_new_client_clicked()

    assert dialog.values()["client_id"] == 99
    assert dialog.client_combo.currentText() == "Client tout neuf"
    # La date et la ligne déjà saisies sont intactes.
    assert dialog.values()["date"] == "2026-01-15"
    assert len(dialog.values()["lignes"]) == 1
    assert dialog.values()["lignes"][0]["article_id"] == 10


def test_new_client_button_cancelled_keeps_current_selection(qtbot) -> None:
    def on_create_client():
        return None  # l'utilisateur a annulé le sous-formulaire client

    dialog = SaleFormDialog(_ARTICLES, _CLIENTS, {"client_id": 1}, on_create_client=on_create_client)
    qtbot.addWidget(dialog)

    dialog._on_new_client_clicked()

    assert dialog.values()["client_id"] == 1


def test_dialog_prefills_lines_from_initial(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1 — Eau", "quantite": Decimal("10"), "prix_unitaire": Decimal("800")},
        ]
    }
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.rowCount() == 1
    assert dialog.lines_table.item(0, 0).text() == "ART-1 — Eau"
    assert dialog.lines_table.item(0, 1).text() == "10"
    assert "8000" in dialog.total_label.text()


def test_add_line_appends_row_and_updates_total(qtbot, monkeypatch) -> None:
    monkeypatch.setattr("app.views.sale_form_dialog.SaleLineFormDialog", _FakeLineDialog)
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    values = dialog.values()
    assert len(values["lignes"]) == 1
    assert values["lignes"][0]["article_id"] == 10
    assert values["lignes"][0]["quantite"] == Decimal("5")
    assert values["lignes"][0]["prix_unitaire"] == Decimal("800")


def test_add_line_rejects_non_positive_quantity_and_reopens(qtbot, monkeypatch) -> None:
    calls = {"n": 0}

    class _FirstBadThenGood(_FakeLineDialog):
        def values(self):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"article_id": 10, "quantite": "0", "prix_unitaire": "800"}
            return {"article_id": 10, "quantite": "5", "prix_unitaire": "800"}

    monkeypatch.setattr("app.views.sale_form_dialog.SaleLineFormDialog", _FirstBadThenGood)
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    dialog._on_add_line_clicked()

    assert calls["n"] == 2
    assert dialog.lines_table.rowCount() == 1


def test_remove_line_deletes_selected_row(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1", "quantite": Decimal("10"), "prix_unitaire": Decimal("800")},
            {"article_id": 20, "article_label": "ART-2", "quantite": Decimal("2"), "prix_unitaire": Decimal("1500")},
        ]
    }
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS, initial)
    qtbot.addWidget(dialog)
    dialog.lines_table.selectRow(0)

    dialog._on_remove_line_clicked()

    assert dialog.lines_table.rowCount() == 1
    assert dialog.values()["lignes"][0]["article_id"] == 20


def test_save_button_accepts(qtbot) -> None:
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cancel_button_rejects(qtbot) -> None:
    dialog = SaleFormDialog(_ARTICLES, _CLIENTS)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected
