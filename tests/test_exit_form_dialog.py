from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDateEdit, QDialog

from app.views.exit_form_dialog import _QUANTITY_COLUMN, ExitFormDialog
from tests.ui_test_helpers import (
    assert_field_is_marked_required,
    assert_field_is_not_marked_required,
    assert_has_required_field_legend,
)

_MOTIFS = [(1, "Perte"), (2, "Casse")]
_ARTICLES = [(10, "ART-1 — Eau", "500"), (20, "ART-2 — Riz", "1200")]


def test_required_fields_are_marked_required(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert_field_is_marked_required(dialog, dialog.motif_combo)
    assert_field_is_marked_required(dialog, dialog.date_edit)


def test_optional_fields_are_not_marked_required(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert_field_is_not_marked_required(dialog, dialog.beneficiaire_edit)
    assert_field_is_not_marked_required(dialog, dialog.reference_edit)
    assert_field_is_not_marked_required(dialog, dialog.commentaire_edit)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_dialog_uses_qdateedit_with_calendar_popup(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert isinstance(dialog.date_edit, QDateEdit)
    assert dialog.date_edit.calendarPopup() is True
    assert dialog.date_edit.displayFormat() == "dd/MM/yyyy"


def test_dialog_defaults_date_to_today_on_creation(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.date_edit.date() == QDate.currentDate()
    assert dialog.values()["date"] == date.today()


def test_dialog_date_edit_cannot_be_set_beyond_today(qtbot) -> None:
    """Confort d'interface (§ dates futures) : le calendrier ne doit pas
    permettre de sélectionner une date future — la garantie réelle reste
    portée par ExitService (voir tests/test_business_date_validation.py)."""
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.date_edit.maximumDate() == QDate.currentDate()

    dialog.date_edit.setDate(QDate.currentDate().addDays(5))
    assert dialog.date_edit.date() == QDate.currentDate()  # clampé par Qt, jamais une date future


def test_dialog_date_change_is_reflected_in_values(qtbot) -> None:
    initial = {"date": date(2026, 1, 15)}
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    dialog.date_edit.setDate(QDate(2026, 3, 1))

    assert dialog.values()["date"] == date(2026, 3, 1)
    assert isinstance(dialog.values()["date"], date)


def test_dialog_prefills_header_from_initial(qtbot) -> None:
    initial = {
        "motif_id": 2, "date": date(2026, 1, 15),
        "beneficiaire": "Service RH", "reference": "REF-1", "commentaire": "Sortie test",
    }
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["motif_id"] == 2
    assert values["date"] == date(2026, 1, 15)
    assert dialog.date_edit.date() == QDate(2026, 1, 15)
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


def test_dialog_prefills_lines_preserve_real_decimal_quantity(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1 — Eau", "quantite": Decimal("2.500"), "cout_unitaire": Decimal("500")},
        ]
    }
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.item(0, 1).text() == "2,5"


# -- Mission 5.3 : sélection d'article par recherche en direct ----------------
#
# Remplace l'ancien ExitLineFormDialog (dialogue séparé par ligne) — voir
# ArticleSearchPanel, partagé avec entry_form_dialog.py.


def test_search_panel_shows_all_articles_with_cmup(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.article_search_panel.results_list.count() == len(_ARTICLES)
    assert "500" in dialog.article_search_panel.results_list.item(0).text()


def test_double_clicking_search_result_adds_line_using_cmup_from_articles_list(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)

    assert dialog.lines_table.rowCount() == 1
    values = dialog.values()
    assert len(values["lignes"]) == 1
    assert values["lignes"][0]["article_id"] == 10
    assert values["lignes"][0]["quantite"] == Decimal("1")
    assert values["lignes"][0]["cout_unitaire"] == Decimal("500")


def test_quantity_editable_in_place_updates_line_and_total(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, 1)
    item.setText("5")

    assert dialog.values()["lignes"][0]["quantite"] == Decimal("5")
    assert "2500" in dialog.total_label.text()


def test_non_positive_quantity_edit_is_rejected_and_reverted(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, 1)
    item.setText("0")

    assert dialog.values()["lignes"][0]["quantite"] == Decimal("1")
    assert dialog.lines_table.item(0, 1).text() == "1"
    assert "strictement positive" in dialog.error_label.text()


def test_cmup_column_stays_read_only(qtbot) -> None:
    """Règle importante de la mission : aucune règle de valorisation/CMUP
    n'est changée — le Coût (CMUP) ne doit jamais devenir éditable."""
    from PySide6.QtCore import Qt as _Qt

    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    cout_item = dialog.lines_table.item(0, 2)
    assert not (cout_item.flags() & _Qt.ItemFlag.ItemIsEditable)


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


# -- Mission 5.4, Évolution A.2 : compteur dynamique "Lignes (n)" -------------------


def test_lines_label_starts_at_zero(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.lines_label.text() == "Lignes (0)"


def test_lines_label_reflects_prefilled_lines(qtbot) -> None:
    initial = {
        "lignes": [
            {"article_id": 10, "article_label": "ART-1", "quantite": Decimal("10"), "cout_unitaire": Decimal("500")},
        ]
    }
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES, initial)
    qtbot.addWidget(dialog)

    assert dialog.lines_label.text() == "Lignes (1)"


def test_lines_label_increments_after_add(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    assert dialog.lines_label.text() == "Lignes (1)"

    dialog._on_article_activated(20)
    assert dialog.lines_label.text() == "Lignes (2)"


def test_lines_label_decrements_after_remove(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)
    dialog._on_article_activated(20)
    dialog.lines_table.selectRow(0)

    dialog._on_remove_line_clicked()

    assert dialog.lines_label.text() == "Lignes (1)"


def test_lines_label_stays_consistent_across_multiple_operations(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
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
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cancel_button_rejects(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


# -- Lot 11 : validation directe (bouton « Valider ») -------------------------

def test_buttons_are_ordered_annuler_brouillon_valider(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.cancel_button.text() == "Annuler"
    assert dialog.save_button.text() == "Enregistrer en brouillon"
    assert dialog.validate_button.text() == "Valider"


def test_requested_action_defaults_to_draft(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.requested_action() == "draft"


def test_save_button_accepts_with_draft_action(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.requested_action() == "draft"


def test_validate_button_accepts_with_validate_action(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.requested_action() == "validate"


def test_validate_button_click_disables_save_and_validate_buttons(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)

    assert dialog.save_button.isEnabled() is False
    assert dialog.validate_button.isEnabled() is False


# -- Mission 5.5, Évolution A : lines_table compact (2 lignes visibles) ------------


def _header_height(table) -> int:
    return table.horizontalHeader().sizeHint().height() or 32


def test_lines_table_has_header_only_height_with_no_lines(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.maximumHeight() == _header_height(dialog.lines_table) + 12


def test_lines_table_height_fits_exactly_two_rows_by_default(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    dialog._on_article_activated(20)

    expected = _header_height(dialog.lines_table) + 2 * 34 + 12
    assert dialog.lines_table.maximumHeight() == expected
    assert dialog.lines_table.minimumHeight() == expected


def test_lines_table_height_caps_at_two_rows_with_more_lines(qtbot) -> None:
    """Au-delà de 2 lignes, la hauteur visible n'augmente plus (défilement
    vertical du tableau pour les lignes suivantes) — mais aucune ligne
    n'est jamais perdue : ``rowCount``/``values()`` reflètent toujours le
    nombre réel de lignes."""
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    dialog._on_article_activated(20)
    two_rows_height = dialog.lines_table.maximumHeight()

    dialog._on_article_activated(10)

    assert dialog.lines_table.maximumHeight() == two_rows_height
    assert dialog.lines_table.rowCount() == 3
    assert len(dialog.values()["lignes"]) == 3


def test_lines_table_column_widths_preserved_after_multiple_refreshes(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    dialog._on_article_activated(20)
    dialog._on_article_activated(10)

    assert dialog.lines_table.columnWidth(_QUANTITY_COLUMN) == 95
    assert dialog.lines_table.columnWidth(2) == 120


def test_lines_table_never_disables_vertical_scrollbar(qtbot) -> None:
    dialog = ExitFormDialog(_MOTIFS, _ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
