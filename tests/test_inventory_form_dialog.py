from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDateEdit, QDialog

from app.views.inventory_form_dialog import _STOCK_PHYSIQUE_COLUMN, InventoryFormDialog
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


def test_dialog_uses_qdateedit_with_calendar_popup(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert isinstance(dialog.date_edit, QDateEdit)
    assert dialog.date_edit.calendarPopup() is True
    assert dialog.date_edit.displayFormat() == "dd/MM/yyyy"


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


# -- Mission 5.5, Évolution C : recherche en direct (ArticleSearchPanel) ----------


def test_double_clicking_search_result_adds_line_with_stock_theorique_as_default_stock_physique(qtbot) -> None:
    """Le stock compté démarre toujours au stock théorique (écart nul) —
    jamais une valeur devinée au hasard — puis reste librement modifiable
    directement dans le tableau."""
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)

    assert dialog.lines_table.rowCount() == 1
    values = dialog.values()
    assert len(values["lignes"]) == 1
    assert values["lignes"][0]["article_id"] == 10
    assert values["lignes"][0]["stock_theorique"] == Decimal("100")
    assert values["lignes"][0]["stock_physique"] == Decimal("100")
    assert dialog.lines_table.item(0, 3).text() == "0"


def test_double_clicking_search_result_clears_search_text(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog.article_search_panel.search_edit.setText("Eau")

    dialog._on_article_activated(10)

    assert dialog.article_search_panel.search_edit.text() == ""


def test_search_panel_shows_five_results_without_scrolling(qtbot) -> None:
    many_articles = [(i, f"ART-{i} — Désignation {i}", "10") for i in range(8)]
    dialog = InventoryFormDialog(many_articles)
    qtbot.addWidget(dialog)

    row_height = dialog.article_search_panel.results_list.sizeHintForRow(0)
    assert dialog.article_search_panel.results_list.height() == 5 * row_height + 6


def test_search_panel_filters_results_live(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog.article_search_panel.search_edit.setText("Riz")

    labels = [
        dialog.article_search_panel.results_list.item(i).text()
        for i in range(dialog.article_search_panel.results_list.count())
    ]
    assert len(labels) == 1
    assert "Riz" in labels[0]


def test_search_panel_and_scan_do_not_interfere(qtbot) -> None:
    """La recherche manuelle et le scan coexistent sans conflit : chacun
    n'ajoute une ligne qu'en passant par le même point d'entrée unique
    (``_on_article_activated``), sans jamais partager ou réinitialiser
    l'état de l'autre."""
    dialog = InventoryFormDialog(_ARTICLES, on_lookup_barcode=lambda code: (20, "ART-2 — Riz", "50"))
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    qtbot.keyClicks(dialog.scan_edit, "1234567890123")
    qtbot.keyClick(dialog.scan_edit, Qt.Key.Key_Return)

    assert dialog.lines_table.rowCount() == 2
    values = dialog.values()
    assert {ligne["article_id"] for ligne in values["lignes"]} == {10, 20}


# -- scan code-barres (lecteur USB « keyboard wedge ») -----------------------------
#
# Le matériel physique n'est jamais disponible en test : ces cas simulent
# l'entrée clavier produite par un scanner (texte tapé puis Entrée), sans
# jamais prétendre tester un vrai lecteur USB.


def test_scan_disabled_without_lookup_callback(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.scan_edit.isEnabled() is False


def test_scan_known_barcode_adds_line_directly(qtbot) -> None:
    """Mission 5.5, Évolution C : le scan n'ouvre plus de formulaire
    intermédiaire — un code reconnu ajoute directement la ligne, comme un
    double-clic sur un résultat de recherche."""
    dialog = InventoryFormDialog(_ARTICLES, on_lookup_barcode=lambda code: (10, "ART-1 — Eau", "100"))
    qtbot.addWidget(dialog)

    qtbot.keyClicks(dialog.scan_edit, "1234567890123")
    qtbot.keyClick(dialog.scan_edit, Qt.Key.Key_Return)

    assert dialog.lines_table.rowCount() == 1
    assert dialog.values()["lignes"][0]["article_id"] == 10
    assert dialog.values()["lignes"][0]["stock_physique"] == Decimal("100")
    assert dialog.scan_edit.text() == ""


def test_scan_unknown_barcode_adds_no_line_and_warns(qtbot, monkeypatch) -> None:
    warnings: list[tuple] = []
    monkeypatch.setattr(
        "app.views.inventory_form_dialog.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    dialog = InventoryFormDialog(_ARTICLES, on_lookup_barcode=lambda code: None)
    qtbot.addWidget(dialog)

    qtbot.keyClicks(dialog.scan_edit, "0000000000000")
    qtbot.keyClick(dialog.scan_edit, Qt.Key.Key_Return)

    assert dialog.lines_table.rowCount() == 0
    assert len(warnings) == 1


# -- Mission 5.5, Évolution C : stock compté éditable, théorique/écart lecture seule --


def test_stock_theorique_cell_is_not_editable(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, 1)
    assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)


def test_ecart_cell_is_not_editable(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, 3)
    assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)


def test_stock_physique_cell_is_editable(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    item = dialog.lines_table.item(0, _STOCK_PHYSIQUE_COLUMN)
    assert bool(item.flags() & Qt.ItemFlag.ItemIsEditable)


def test_editing_stock_physique_updates_line_and_recomputes_ecart(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    dialog.lines_table.item(0, _STOCK_PHYSIQUE_COLUMN).setText("97")

    assert dialog.values()["lignes"][0]["stock_physique"] == Decimal("97")
    assert dialog.values()["lignes"][0]["stock_theorique"] == Decimal("100")  # jamais modifié
    assert dialog.lines_table.item(0, 3).text() == "-3"


def test_editing_stock_physique_to_zero_is_accepted(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    dialog.lines_table.item(0, _STOCK_PHYSIQUE_COLUMN).setText("0")

    assert dialog.values()["lignes"][0]["stock_physique"] == Decimal("0")
    assert dialog.lines_table.item(0, 3).text() == "-100"


def test_editing_stock_physique_to_negative_is_rejected_and_reverted(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)
    dialog._on_article_activated(10)

    dialog.lines_table.item(0, _STOCK_PHYSIQUE_COLUMN).setText("-1")

    assert dialog.values()["lignes"][0]["stock_physique"] == Decimal("100")  # valeur précédente conservée
    assert dialog.lines_table.item(0, _STOCK_PHYSIQUE_COLUMN).text() == "100"
    assert "négatif" in dialog.error_label.text()


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


# -- Mission 5.5, Évolution C : compteur dynamique "Lignes (n)" -------------------


def test_lines_label_starts_at_zero(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.lines_label.text() == "Lignes (0)"


def test_lines_label_increments_after_add_and_decrements_after_remove(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    assert dialog.lines_label.text() == "Lignes (1)"

    dialog._on_article_activated(20)
    assert dialog.lines_label.text() == "Lignes (2)"

    dialog.lines_table.selectRow(0)
    dialog._on_remove_line_clicked()
    assert dialog.lines_label.text() == "Lignes (1)"


# -- Mission 5.5, Évolution C : tableau compact (2 lignes visibles) --------------


def _header_height(table) -> int:
    return table.horizontalHeader().sizeHint().height() or 32


def test_lines_table_has_header_only_height_with_no_lines(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.maximumHeight() == _header_height(dialog.lines_table) + 12


def test_lines_table_height_fits_exactly_two_rows_by_default(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    dialog._on_article_activated(20)

    expected = _header_height(dialog.lines_table) + 2 * 34 + 12
    assert dialog.lines_table.maximumHeight() == expected
    assert dialog.lines_table.minimumHeight() == expected


def test_lines_table_height_caps_at_two_rows_with_more_lines(qtbot) -> None:
    many_articles = [(10, "ART-1 — Eau", "100"), (20, "ART-2 — Riz", "50"), (30, "ART-3 — Sucre", "20")]
    dialog = InventoryFormDialog(many_articles)
    qtbot.addWidget(dialog)

    dialog._on_article_activated(10)
    dialog._on_article_activated(20)
    two_rows_height = dialog.lines_table.maximumHeight()

    dialog._on_article_activated(30)

    assert dialog.lines_table.maximumHeight() == two_rows_height
    assert dialog.lines_table.rowCount() == 3
    assert len(dialog.values()["lignes"]) == 3


def test_lines_table_never_disables_vertical_scrollbar(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.lines_table.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff


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


# -- Lot 11 : validation directe (bouton « Valider ») -------------------------

def test_buttons_are_ordered_annuler_brouillon_valider(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.cancel_button.text() == "Annuler"
    assert dialog.save_button.text() == "Enregistrer en brouillon"
    assert dialog.validate_button.text() == "Valider"


def test_requested_action_defaults_to_draft(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    assert dialog.requested_action() == "draft"


def test_save_button_accepts_with_draft_action(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.requested_action() == "draft"


def test_validate_button_accepts_with_validate_action(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.requested_action() == "validate"


def test_validate_button_click_disables_save_and_validate_buttons(qtbot) -> None:
    dialog = InventoryFormDialog(_ARTICLES)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)

    assert dialog.save_button.isEnabled() is False
    assert dialog.validate_button.isEnabled() is False
