from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.models.enums import ModeGestionArticle
from app.views.article_form_dialog import ArticleFormDialog
from tests.ui_test_helpers import (
    assert_field_is_marked_required,
    assert_field_is_not_marked_required,
    assert_has_required_field_legend,
)

_CATEGORIES = [(1, "Boissons"), (2, "Épicerie")]
_SUPPLIERS = [(10, "Fournisseur A"), (20, "Fournisseur B")]
_UNITES = ["Pièce", "Unité", "Carton"]


def test_required_fields_are_marked_in_create_mode(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    for field in (
        dialog.reference_edit, dialog.designation_edit, dialog.category_combo,
        dialog.unite_row, dialog.prix_achat_edit, dialog.prix_vente_edit,
        dialog.stock_min_edit, dialog.stock_initial_edit,
    ):
        assert_field_is_marked_required(dialog, field)


def test_optional_fields_are_not_marked_required(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    for field in (
        dialog.supplier_combo, dialog.stock_max_edit, dialog.emplacement_edit,
        dialog.code_barres_edit, dialog.description_edit,
    ):
        assert_field_is_not_marked_required(dialog, field)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_create_mode_shows_stock_initial_not_stock_actuel(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.stock_initial_edit is not None
    assert dialog.stock_actuel_label is None
    assert dialog.cmup_label is None


def test_edit_mode_shows_stock_actuel_and_cmup_as_readonly_labels(qtbot) -> None:
    initial = {
        "reference": "ART-1", "designation": "Article", "category_id": 1,
        "stock_actuel": "42.000", "cout_moyen_pondere": "12.50",
    }
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.stock_initial_edit is None
    assert dialog.stock_actuel_label is not None
    assert dialog.stock_actuel_label.text() == "42"  # formatage des quantités : pas de décimales superflues
    assert dialog.cmup_label is not None
    assert dialog.cmup_label.text() == "12.5"  # Lot 23 (§E) : pas de décimale superflue


def test_dialog_prefills_fields_from_initial(qtbot) -> None:
    initial = {
        "reference": "ART-2", "designation": "Désignation", "category_id": 2,
        "fournisseur_principal_id": 20, "unite": "kg",
        "prix_achat": "10.00", "prix_vente": "15.00", "stock_min": "5.000",
        "stock_max": "50.000", "emplacement": "Rayon A1", "code_barres": "123",
        "description": "Une description",
    }
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    values = dialog.values()
    assert values["reference"] == "ART-2"
    assert values["category_id"] == 2
    assert values["fournisseur_principal_id"] == 20
    assert values["unite"] == "kg"
    assert values["prix_achat"] == "10"  # Lot 23 (§E) : pas de décimale superflue
    assert values["stock_max"] == "50"  # formatage des quantités : pas de décimales superflues
    assert values["emplacement"] == "Rayon A1"
    assert values["code_barres"] == "123"
    assert values["description"] == "Une description"


def test_stock_fields_preserve_real_decimal_precision(qtbot) -> None:
    """Une vraie valeur décimale (ex. 5,5) n'est jamais transformée en
    entier par le formatage — seules les décimales superflues (ex. 42.000)
    sont supprimées à l'affichage."""
    initial = {
        "reference": "ART-3", "designation": "Désignation", "category_id": 1,
        "stock_min": "5.500", "stock_max": "50.750", "stock_actuel": "12.250", "cout_moyen_pondere": "1.00",
    }
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.stock_min_edit.text() == "5,5"
    assert dialog.stock_max_edit.text() == "50,75"
    assert dialog.stock_actuel_label.text() == "12,25"


def test_supplier_combo_defaults_to_none(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.values()["fournisseur_principal_id"] is None


# -- Évolution F : liste fermée des unités (plus de champ libre) --------------------


def test_unite_combo_is_a_closed_dropdown_not_free_text(qtbot) -> None:
    """Non-régression (§7.1) : le champ ne doit plus jamais redevenir une
    saisie libre — c'est exactement ce que cette évolution corrige."""
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.unite_combo.isEditable() is False
    assert [dialog.unite_combo.itemText(i) for i in range(dialog.unite_combo.count())] == _UNITES


def test_unite_combo_defaults_to_piece_in_create_mode(qtbot) -> None:
    """§7.2 : « Pièce » par défaut à la création, quand elle figure dans la
    liste proposée."""
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.values()["unite"] == "Pièce"


def test_unite_combo_shows_existing_value_in_edit_mode(qtbot) -> None:
    initial = {"reference": "ART-1", "designation": "Article", "category_id": 1, "unite": "Carton"}
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.values()["unite"] == "Carton"


def test_unite_combo_preserves_legacy_value_not_in_the_reference_list(qtbot) -> None:
    """§7.4 : un article existant dont l'unité (saisie libre antérieure à
    ce lot) ne figure pas dans la liste de référence doit continuer à
    s'afficher et à se modifier sans aucune altération silencieuse."""
    initial = {"reference": "ART-1", "designation": "Article", "category_id": 1, "unite": "bidon de 20L"}
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.values()["unite"] == "bidon de 20L"


def test_new_unite_button_disabled_without_callback(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.new_unite_button.isEnabled() is False


def test_new_unite_button_adds_and_selects_created_unite(qtbot) -> None:
    dialog = ArticleFormDialog(
        _CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False, on_create_unite=lambda: "Botte"
    )
    qtbot.addWidget(dialog)

    assert dialog.new_unite_button.isEnabled() is True
    dialog._on_new_unite_clicked()

    assert dialog.unite_combo.findText("Botte") != -1
    assert dialog.values()["unite"] == "Botte"


def test_new_unite_button_does_nothing_when_callback_returns_none(qtbot) -> None:
    """Annulation du sous-dialogue de création (§7.3) : la sélection
    courante ne doit pas changer."""
    dialog = ArticleFormDialog(
        _CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False, on_create_unite=lambda: None
    )
    qtbot.addWidget(dialog)
    before = dialog.values()["unite"]

    dialog._on_new_unite_clicked()

    assert dialog.values()["unite"] == before


def test_delete_unite_button_disabled_without_callback(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.delete_unite_button.isEnabled() is False


def test_delete_unite_button_updates_combo_and_selection(qtbot) -> None:
    """§4.1/§4.5 : la liste déroulante est actualisée et une autre unité
    disponible est sélectionnée après une suppression réussie."""
    dialog = ArticleFormDialog(
        _CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False,
        on_delete_unite=lambda libelle: (["Pièce", "Unité"], "Unité"),
    )
    qtbot.addWidget(dialog)

    assert dialog.delete_unite_button.isEnabled() is True
    dialog._on_delete_unite_clicked()

    assert dialog.unite_combo.findText("Carton") == -1
    assert dialog.values()["unite"] == "Unité"


def test_delete_unite_button_does_nothing_when_callback_returns_none(qtbot) -> None:
    """Refus/annulation côté appelant (unité utilisée, confirmation
    annulée…) : le menu déroulant ne doit pas changer."""
    dialog = ArticleFormDialog(
        _CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False,
        on_delete_unite=lambda libelle: None,
    )
    qtbot.addWidget(dialog)
    before = [dialog.unite_combo.itemText(i) for i in range(dialog.unite_combo.count())]

    dialog._on_delete_unite_clicked()

    after = [dialog.unite_combo.itemText(i) for i in range(dialog.unite_combo.count())]
    assert after == before


def test_delete_unite_button_passes_currently_selected_label(qtbot) -> None:
    received = {}

    def on_delete_unite(libelle: str):
        received["libelle"] = libelle
        return None

    dialog = ArticleFormDialog(
        _CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False, on_delete_unite=on_delete_unite
    )
    qtbot.addWidget(dialog)
    dialog.unite_combo.setCurrentText("Carton")

    dialog._on_delete_unite_clicked()

    assert received["libelle"] == "Carton"


def test_save_button_accepts(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)
    dialog.reference_edit.setText("ART-NEW")

    qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.values()["reference"] == "ART-NEW"


def test_cancel_button_rejects(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_set_error_displays_message(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    dialog.set_error("La référence « ART-1 » est déjà utilisée.")

    assert "déjà utilisée" in dialog.error_label.text()


# -- Lot 12 : mode de gestion (Vente / Location) -----------------------------

def test_mode_gestion_defaults_to_vente_in_create_mode(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.values()["mode_gestion"] == ModeGestionArticle.VENTE


def test_mode_gestion_shows_real_value_in_edit_mode(qtbot) -> None:
    initial = {
        "reference": "ART-LOC", "designation": "Article", "category_id": 1,
        "mode_gestion": ModeGestionArticle.LOCATION, "tarif_location_jour": "500",
    }
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.values()["mode_gestion"] == ModeGestionArticle.LOCATION


def test_mode_gestion_is_a_real_enum_member_not_a_bare_str(qtbot) -> None:
    """Non-régression (incident « mode de gestion ») : QComboBox.currentData()
    restitue un ``str`` nu pour une énumération dérivant de ``str`` — une
    égalité ``== ModeGestionArticle.X`` reste vraie malgré cela (voir les
    deux tests ci-dessus) et ne l'aurait donc jamais détecté. Seule une
    vérification de type (ou un accès à ``.value``) le révèle ; c'est
    exactement l'accès qui levait ``AttributeError: 'str' object has no
    attribute 'value'`` dans ``ArticleService.switch_mode_gestion``."""
    for mode in (ModeGestionArticle.VENTE, ModeGestionArticle.LOCATION):
        initial = {
            "reference": "ART-X", "designation": "Article", "category_id": 1,
            "mode_gestion": mode, "tarif_location_jour": "500",
        }
        dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
        qtbot.addWidget(dialog)

        valeur = dialog.values()["mode_gestion"]
        assert type(valeur) is ModeGestionArticle
        assert valeur.value == mode.value


def test_tarif_field_disabled_by_default_in_vente_mode(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.tarif_location_jour_edit.isEnabled() is False


def test_tarif_field_enabled_when_location_selected(qtbot) -> None:
    initial = {"reference": "ART-LOC", "designation": "Article", "category_id": 1, "mode_gestion": ModeGestionArticle.LOCATION}
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.tarif_location_jour_edit.isEnabled() is True


def test_switching_mode_updates_tarif_field_state_immediately(qtbot) -> None:
    """§5 du lot : le passage d'un mode à l'autre actualise immédiatement
    l'état du champ tarif, sans effacer une saisie déjà faite."""
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)
    assert dialog.tarif_location_jour_edit.isEnabled() is False

    index_location = dialog.mode_gestion_combo.findData(ModeGestionArticle.LOCATION)
    dialog.mode_gestion_combo.setCurrentIndex(index_location)
    assert dialog.tarif_location_jour_edit.isEnabled() is True

    dialog.tarif_location_jour_edit.setText("500")
    index_vente = dialog.mode_gestion_combo.findData(ModeGestionArticle.VENTE)
    dialog.mode_gestion_combo.setCurrentIndex(index_vente)

    assert dialog.tarif_location_jour_edit.isEnabled() is False
    assert dialog.tarif_location_jour_edit.text() == "500"  # jamais effacée par un aller-retour


# -- Lot 18 : désactivation symétrique des champs de prix --------------------
#
# Le mode Vente désactivant déjà le tarif de location (couvert ci-dessus par
# test_tarif_field_disabled_by_default_in_vente_mode /
# test_tarif_field_enabled_when_location_selected, non dupliqués ici), seul
# le comportement symétrique du prix de vente est testé dans cette section,
# ainsi que les scénarios combinant les deux champs.

def test_prix_vente_field_enabled_by_default_in_vente_mode(qtbot) -> None:
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    assert dialog.values()["mode_gestion"] == ModeGestionArticle.VENTE
    assert dialog.prix_vente_edit.isEnabled() is True


def test_prix_vente_field_disabled_in_location_mode_at_opening(qtbot) -> None:
    """L'état initial des deux champs doit être correct dès l'ouverture, en
    modification d'un article déjà en mode Location — pas seulement après
    un changement ultérieur du sélecteur."""
    initial = {
        "reference": "ART-LOC", "designation": "Article", "category_id": 1,
        "mode_gestion": ModeGestionArticle.LOCATION, "tarif_location_jour": "500",
    }
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.prix_vente_edit.isEnabled() is False
    assert dialog.tarif_location_jour_edit.isEnabled() is True


def test_existing_location_article_keeps_and_shows_prix_vente_disabled(qtbot) -> None:
    """Un article existant en mode Location, avec un prix de vente déjà
    enregistré (ex. hérité d'un ancien mode Vente), conserve et affiche
    cette valeur dans un champ désactivé dès l'ouverture du formulaire."""
    initial = {
        "reference": "ART-LOC", "designation": "Article", "category_id": 1,
        "mode_gestion": ModeGestionArticle.LOCATION, "tarif_location_jour": "500",
        "prix_vente": "1200",
    }
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, initial, is_edit=True)
    qtbot.addWidget(dialog)

    assert dialog.prix_vente_edit.isEnabled() is False
    assert dialog.prix_vente_edit.text() == "1200"
    assert dialog.values()["prix_vente"] == "1200"


def test_switching_mode_updates_both_price_fields_immediately(qtbot) -> None:
    """Le passage d'un mode à l'autre actualise immédiatement et
    symétriquement l'état des deux champs de prix."""
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)
    assert dialog.prix_vente_edit.isEnabled() is True
    assert dialog.tarif_location_jour_edit.isEnabled() is False

    index_location = dialog.mode_gestion_combo.findData(ModeGestionArticle.LOCATION)
    dialog.mode_gestion_combo.setCurrentIndex(index_location)
    assert dialog.prix_vente_edit.isEnabled() is False
    assert dialog.tarif_location_jour_edit.isEnabled() is True

    index_vente = dialog.mode_gestion_combo.findData(ModeGestionArticle.VENTE)
    dialog.mode_gestion_combo.setCurrentIndex(index_vente)
    assert dialog.prix_vente_edit.isEnabled() is True
    assert dialog.tarif_location_jour_edit.isEnabled() is False


def test_switching_mode_multiple_times_preserves_both_field_values(qtbot) -> None:
    """Plusieurs bascules successives ne doivent jamais effacer les
    valeurs des deux champs, désactivés ou non."""
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)

    dialog.prix_vente_edit.setText("1500")
    index_location = dialog.mode_gestion_combo.findData(ModeGestionArticle.LOCATION)
    index_vente = dialog.mode_gestion_combo.findData(ModeGestionArticle.VENTE)

    dialog.mode_gestion_combo.setCurrentIndex(index_location)
    dialog.tarif_location_jour_edit.setText("500")
    dialog.mode_gestion_combo.setCurrentIndex(index_vente)
    dialog.mode_gestion_combo.setCurrentIndex(index_location)
    dialog.mode_gestion_combo.setCurrentIndex(index_vente)
    dialog.mode_gestion_combo.setCurrentIndex(index_location)

    assert dialog.prix_vente_edit.text() == "1500"
    assert dialog.tarif_location_jour_edit.text() == "500"
    assert dialog.prix_vente_edit.isEnabled() is False
    assert dialog.tarif_location_jour_edit.isEnabled() is True


def test_values_returns_prix_vente_even_when_field_disabled(qtbot) -> None:
    """``values()`` continue de renvoyer la valeur réelle d'un champ
    désactivé — aucune perte de donnée liée au seul état d'activation."""
    dialog = ArticleFormDialog(_CATEGORIES, _SUPPLIERS, _UNITES, is_edit=False)
    qtbot.addWidget(dialog)
    dialog.prix_vente_edit.setText("999")

    index_location = dialog.mode_gestion_combo.findData(ModeGestionArticle.LOCATION)
    dialog.mode_gestion_combo.setCurrentIndex(index_location)

    assert dialog.prix_vente_edit.isEnabled() is False
    assert dialog.values()["prix_vente"] == "999"
