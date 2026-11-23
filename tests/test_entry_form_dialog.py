from datetime import date
from decimal import Decimal

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


def test_dialog_uses_qdateedit_with_calendar_popup(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert isinstance(dialog.date_edit, QDateEdit)
    assert dialog.date_edit.calendarPopup() is True
    assert dialog.date_edit.displayFormat() == "dd/MM/yyyy"


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


# -- Mission 5.3 : sélection d'article par recherche en direct ----------------
#
# Remplace l'ancien EntryLineFormDialog (dialogue séparé par ligne) — voir
# ArticleSearchPanel, partagé avec exit_form_dialog.py.


def test_search_panel_shows_all_articles_with_default_price(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.article_search_panel.results_list.count() == len(_ARTICLES)
    assert "500" in dialog.article_search_panel.results_list.item(0).text()


def test_double_clicking_search_result_adds_line_with_default_price(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)

    assert dialog.lines_table.rowCount() == 1
    values = dialog.values()
    assert len(values["lignes"]) == 1
    assert values["lignes"][0]["article_id"] == 10
    assert values["lignes"][0]["quantite"] == Decimal("1")
    assert values["lignes"][0]["prix_unitaire"] == Decimal("500")


def test_double_clicking_search_result_clears_search_text(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog.article_search_panel.search_edit.setText("Eau")

    dialog._on_article_activated(10)

    assert dialog.article_search_panel.search_edit.text() == ""


def test_quantity_editable_in_place_updates_line_and_total(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, 1)
    item.setText("20")

    assert dialog.values()["lignes"][0]["quantite"] == Decimal("20")
    assert "10000" in dialog.total_label.text()


def test_price_editable_in_place_updates_line(qtbot) -> None:
    """§B de la mission : le prix d'achat unitaire reste librement
    modifiable — désormais directement dans le tableau."""
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, 2)
    item.setText("480")

    assert dialog.values()["lignes"][0]["prix_unitaire"] == Decimal("480")


def test_non_positive_quantity_edit_is_rejected_and_reverted(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, 1)
    item.setText("0")

    assert dialog.values()["lignes"][0]["quantite"] == Decimal("1")
    assert dialog.lines_table.item(0, 1).text() == "1"
    assert "strictement positive" in dialog.error_label.text()


def test_negative_price_edit_is_rejected_and_reverted(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, 2)
    item.setText("-10")

    assert dialog.values()["lignes"][0]["prix_unitaire"] == Decimal("500")
    assert "négatif" in dialog.error_label.text()


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


# -- Mission 5.4, Évolution A.2 : compteur dynamique "Lignes (n)" -------------------


def test_lines_label_starts_at_zero(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.lines_label.text() == "Lignes (0)"


def test_lines_label_reflects_prefilled_lines(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1", "quantite": Decimal("10"), "prix_unitaire": Decimal("500")},
        ]
    }
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_label.text() == "Lignes (1)"


def test_lines_label_increments_after_add(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    assert dialog.lines_label.text() == "Lignes (1)"

    dialog._on_article_activated(20)
    assert dialog.lines_label.text() == "Lignes (2)"


def test_lines_label_decrements_after_remove(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)
    dialog._on_article_activated(20)
    dialog.lines_table.selectRow(0)

    dialog._on_remove_line_clicked()

    assert dialog.lines_label.text() == "Lignes (1)"


def test_lines_label_stays_consistent_across_multiple_operations(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    dialog._on_article_activated(20)
    dialog._on_article_activated(10)
    assert dialog.lines_label.text() == "Lignes (3)"

    dialog.lines_table.selectRow(1)
    dialog._on_remove_line_clicked()
    assert dialog.lines_label.text() == "Lignes (2)"

    dialog.lines_table.selectRow(0)
    dialog._on_remove_line_clicked()
    assert dialog.lines_label.text() == "Lignes (1)"


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


# -- Lot 11 : validation directe (bouton « Valider ») -------------------------

def test_buttons_are_ordered_annuler_brouillon_valider(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.cancel_button.text() == "Annuler"
    assert dialog.save_button.text() == "Enregistrer en brouillon"
    assert dialog.validate_button.text() == "Valider"


def test_requested_action_defaults_to_draft(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.requested_action() == "draft"


def test_save_button_accepts_with_draft_action(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.requested_action() == "draft"


def test_validate_button_accepts_with_validate_action(qtbot) -> None:
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.requested_action() == "validate"


def test_validate_button_click_disables_save_and_validate_buttons(qtbot) -> None:
    """Défense en profondeur ergonomique uniquement : la véritable garantie
    anti-double-validation reste le contrôle de statut côté service
    (``statut != BROUILLON``), combiné à ``run_modal_form`` qui n'appelle
    ``submit`` qu'une fois par cycle ``exec()``."""
    dialog = EntryFormDialog(_SUPPLIERS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)

    assert dialog.save_button.isEnabled() is False
    assert dialog.validate_button.isEnabled() is False
