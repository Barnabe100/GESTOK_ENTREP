from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.views.article_form_dialog import ArticleFormDialog

_CATEGORIES = [(1, "Boissons"), (2, "Épicerie")]
_SUPPLIERS = [(10, "Fournisseur A"), (20, "Fournisseur B")]


def test_create_mode_shows_stock_initial_not_stock_actuel(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.stock_initial_edit is not None
    assert dialog.stock_actuel_label is None
    assert dialog.cmup_label is None


def test_edit_mode_shows_stock_actuel_and_cmup_as_readonly_labels(qtbot) -> None:
    initial = {
        "reference": "ART-1", "designation": "Article", "category_id": 1,
        "stock_actuel": "42.000", "cout_moyen_pondere": "12.50",
    }
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.stock_initial_edit is None
    assert dialog.stock_actuel_label is not None
    assert dialog.stock_actuel_label.text() == "42.000"
    assert dialog.cmup_label is not None
    assert dialog.cmup_label.text() == "12.50"


def test_dialog_prefills_fields_from_initial(qtbot) -> None:
    initial = {
        "reference": "ART-2", "designation": "Désignation", "category_id": 2,
        "fournisseur_principal_id": 20, "unite": "kg",
        "prix_achat": "10.00", "prix_vente": "15.00", "stock_min": "5.000",
        "stock_max": "50.000", "emplacement": "Rayon A1", "code_barres": "123",
        "description": "Une description",
    }
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, initial, is_edit=True)
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["reference"] == "ART-2"
    assert values["category_id"] == 2
    assert values["fournisseur_principal_id"] == 20
    assert values["unite"] == "kg"
    assert values["prix_achat"] == "10.00"
    assert values["stock_max"] == "50.000"
    assert values["emplacement"] == "Rayon A1"
    assert values["code_barres"] == "123"
    assert values["description"] == "Une description"


def test_supplier_combo_defaults_to_none(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.values()["fournisseur_principal_id"] is None


def test_unite_combo_is_editable_with_suggestions(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.unite_combo.isEditable() is True
    assert dialog.unite_combo.count() >= 7
    dialog.unite_combo.setCurrentText("bidon de 20L")  # valeur libre, hors suggestions
    assert dialog.values()["unite"] == "bidon de 20L"


def test_save_button_accepts(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, is_edit=False)
    qtbot.addWidget(dialog)
    dialog.reference_edit.setText("ART-NEW")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.values()["reference"] == "ART-NEW"


def test_cancel_button_rejects(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, is_edit=False)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_set_error_displays_message(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, is_edit=False)
    qtbot.addWidget(dialog)

    dialog.set_error("La référence « ART-1 » est déjà utilisée.")

    assert "déjà utilisée" in dialog.error_label.text()
