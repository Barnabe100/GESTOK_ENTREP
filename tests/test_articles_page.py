from datetime import datetime
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.config.settings import get_settings
from app.db.session import session_scope
from app.models.catalog import Article
from app.models.enums import ModeGestionArticle
from app.views.pages.articles_page import ArticlesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.articles_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.articles_page.QMessageBox.warning", lambda *a, **k: None)


def _make_article(stack, reference="ART-1"):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0")
    )


def _build_page(stack) -> ArticlesPage:
    return ArticlesPage(
        stack.articles, stack.categories, stack.suppliers, stack.unites_article, stack.permissions
    )


def test_articles_page_formats_whole_stock_without_decimals(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article(
        "ART-INT", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("10"),
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "ART-INT")
    assert page.table.item(row, 3).text() == "10"  # jamais "10.000"


def test_articles_page_preserves_real_decimal_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article(
        "ART-DEC", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("10.5"),
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "ART-DEC")
    assert page.table.item(row, 3).text() == "10,5"


def test_articles_page_lists_articles_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article("ART-1", "Eau", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"))

    page = _build_page(stack)
    qtbot.addWidget(page)

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "ART-1" in references


def test_articles_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article("ART-EAU", "Eau minérale", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.create_article("ART-RIZ", "Riz basmati", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("eau")

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert references == {"ART-EAU"}


def test_articles_page_category_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    boissons = stack.categories.create_category("Boissons")
    epicerie = stack.categories.create_category("Épicerie")
    stack.articles.create_article("ART-B", "Article boissons", boissons.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.create_article("ART-E", "Article épicerie", epicerie.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    page = _build_page(stack)
    qtbot.addWidget(page)

    index = page.category_filter_combo.findData(boissons.id)
    assert index >= 0
    page.category_filter_combo.setCurrentIndex(index)

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert references == {"ART-B"}


def test_articles_page_status_filter_defaults_to_actifs(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    active = stack.articles.create_article("ART-ON", "Actif", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    inactive = stack.articles.create_article("ART-OFF", "Inactif", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.deactivate_article(inactive.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert references == {"ART-ON"}


def test_articles_page_status_filter_inactifs(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article("ART-ON2", "Actif", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    inactive = stack.articles.create_article("ART-OFF2", "Inactif", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.deactivate_article(inactive.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.status_filter_combo.setCurrentIndex(2)  # Inactifs

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert references == {"ART-OFF2"}


def test_articles_page_low_stock_checkbox_filters(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article(
        "ART-LOW", "Faible", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("10"), stock_initial=Decimal("2")
    )
    stack.articles.create_article(
        "ART-OK", "Suffisant", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("10"), stock_initial=Decimal("50")
    )

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.status_filter_combo.setCurrentIndex(0)  # Tous, pour ne pas interférer
    page.low_stock_checkbox.setChecked(True)

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert references == {"ART-LOW"}


def test_articles_page_shows_rupture_indicator(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article("ART-RUPT", "Rupture", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("5"))

    page = _build_page(stack)
    qtbot.addWidget(page)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "ART-RUPT")
    stock_item = page.table.item(row, 3)
    assert stock_item.foreground().color().name() == "#dc2626"


def test_articles_page_buttons_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True
    assert page.edit_button.isEnabled() is True
    assert page.toggle_button.isEnabled() is True


def test_articles_page_buttons_disabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is False
    assert page.edit_button.isEnabled() is False
    assert page.toggle_button.isEnabled() is False


def test_articles_page_vendeur_still_sees_articles(qtbot, login_as) -> None:
    """Le Vendeur a ARTICLE_VIEW : la table s'affiche même sans droits d'écriture."""
    admin_stack, _ = login_as("Administrateur")
    category = admin_stack.categories.create_category("Boissons")
    admin_stack.articles.create_article("ART-VUE", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    vendeur_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_stack)
    qtbot.addWidget(page)

    references = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "ART-VUE" in references


def test_submit_form_creates_article_with_initial_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "reference": "ART-SUBMIT", "designation": "Article soumis", "category_id": category.id,
        "fournisseur_principal_id": None, "unite": "unité",
        "prix_achat": "100", "prix_vente": "150", "stock_min": "5", "stock_max": "",
        "emplacement": "", "code_barres": "", "description": "", "stock_initial": "20",
    }

    result = page._submit_form(None, values)
    page.refresh()

    assert result is True
    created = stack.articles.list_articles(search="ART-SUBMIT")[0]
    assert created.stock_actuel == Decimal("20")
    assert created.cout_moyen_pondere == Decimal("100")


def test_submit_form_shows_error_on_duplicate_reference(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article("ART-DUP", "Existant", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "reference": "ART-DUP", "designation": "Doublon", "category_id": category.id,
        "fournisseur_principal_id": None, "unite": "unité",
        "prix_achat": "1", "prix_vente": "2", "stock_min": "0", "stock_max": "",
        "emplacement": "", "code_barres": "", "description": "", "stock_initial": "0",
    }

    result = page._submit_form(None, values)

    assert result is False
    assert len(stack.articles.list_articles(search="ART-DUP")) == 1


def test_submit_form_shows_error_on_invalid_price(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "reference": "ART-BADPRICE", "designation": "Article", "category_id": category.id,
        "fournisseur_principal_id": None, "unite": "unité",
        "prix_achat": "pas un nombre", "prix_vente": "2", "stock_min": "0", "stock_max": "",
        "emplacement": "", "code_barres": "", "description": "", "stock_initial": "0",
    }

    result = page._submit_form(None, values)

    assert result is False
    assert stack.articles.list_articles(search="ART-BADPRICE") == []


def test_submit_form_requires_category_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "reference": "ART-NOCAT", "designation": "Article", "category_id": None,
        "fournisseur_principal_id": None, "unite": "unité",
        "prix_achat": "1", "prix_vente": "2", "stock_min": "0", "stock_max": "",
        "emplacement": "", "code_barres": "", "description": "", "stock_initial": "0",
    }

    result = page._submit_form(None, values)

    assert result is False


def test_submit_form_updates_existing_article_without_touching_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    created = stack.articles.create_article(
        "ART-EDIT", "Ancien", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        stock_initial=Decimal("30"),
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "reference": "ART-EDIT", "designation": "Nouveau", "category_id": category.id,
        "fournisseur_principal_id": None, "unite": "carton",
        "prix_achat": "12", "prix_vente": "22", "stock_min": "1", "stock_max": "",
        "emplacement": "", "code_barres": "", "description": "", "stock_initial": "999",
    }

    result = page._submit_form(created.id, values)

    assert result is True
    updated = stack.articles.get_article(created.id)
    assert updated.designation == "Nouveau"
    assert updated.stock_actuel == Decimal("30")  # stock_initial du formulaire ignoré en modification


def test_load_edit_initial_returns_full_article_details(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    created = stack.articles.create_article(
        "ART-LOAD", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        emplacement="Rayon Z9",
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(created.id)

    assert initial is not None
    assert initial["reference"] == "ART-LOAD"
    assert initial["emplacement"] == "Rayon Z9"
    assert initial["stock_actuel"] == Decimal("0")


def test_load_edit_initial_returns_none_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(999999)

    assert initial is None


def test_load_article_for_detail_returns_summary(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    created = stack.articles.create_article(
        "ART-DETAIL", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0")
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    article = page._load_article_for_detail(created.id)

    assert article is not None
    assert article.reference == "ART-DETAIL"


def test_toggle_status_deactivates_and_reactivates(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    created = stack.articles.create_article(
        "ART-TOGGLE", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0")
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._toggle_status(created.id, currently_active=True) is True
    assert stack.articles.get_article(created.id).actif is False

    assert page._toggle_status(created.id, currently_active=False) is True
    assert stack.articles.get_article(created.id).actif is True


def test_toggle_status_denied_without_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    category = admin_stack.categories.create_category("Boissons")
    created = admin_stack.articles.create_article(
        "ART-TOGGLEDENY", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0")
    )

    vendeur_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_stack)
    qtbot.addWidget(page)

    result = page._toggle_status(created.id, currently_active=True)

    assert result is False
    assert admin_stack.articles.get_article(created.id).actif is True


def test_confirmation_dialog_no_cancels_toggle(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    created = stack.articles.create_article(
        "ART-CONFIRM1", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0")
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "ART-CONFIRM1")
    page.table.selectRow(row)
    page._on_toggle_clicked()

    assert stack.articles.get_article(created.id).actif is True


def test_load_categories_for_form_includes_inactive_current_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Catégorie à désactiver")
    stack.categories.deactivate_category(category.id)
    page = _build_page(stack)
    qtbot.addWidget(page)

    options = page._load_categories_for_form(include_category_id=category.id)

    ids = {option[0] for option in options}
    assert category.id in ids


def test_load_suppliers_for_form_includes_inactive_current_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur à désactiver")
    stack.suppliers.deactivate_supplier(supplier.id)
    page = _build_page(stack)
    qtbot.addWidget(page)

    options = page._load_suppliers_for_form(include_supplier_id=supplier.id)

    ids = {option[0] for option in options}
    assert supplier.id in ids


# -- mode de gestion (module Locations, lot dédié) -----------------------------


def test_mode_gestion_button_enabled_with_article_update_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.mode_gestion_button.isEnabled() is True


def test_mode_gestion_button_disabled_for_consultation(qtbot, login_as) -> None:
    stack, _ = login_as("Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.mode_gestion_button.isEnabled() is False


def test_submit_mode_gestion_switches_article_to_location(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    article = stack.articles.create_article(
        "ART-SWITCH", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("10"), tarif_location_jour=Decimal("500"),
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_mode_gestion(article.id, ModeGestionArticle.LOCATION)

    assert result is True
    assert stack.articles.get_article(article.id).mode_gestion == ModeGestionArticle.LOCATION


def test_submit_mode_gestion_refused_if_already_in_target_mode(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    article = stack.articles.create_article(
        "ART-SAME", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("10"),
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_mode_gestion(article.id, ModeGestionArticle.VENTE)

    assert result is False


def test_create_article_accepts_tarif_location_jour(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")

    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "reference": "ART-TARIF", "designation": "Article", "category_id": category.id,
        "fournisseur_principal_id": None, "unite": "unité", "prix_achat": "100", "prix_vente": "150",
        "stock_min": "0", "stock_max": "", "emplacement": "", "code_barres": "", "description": "",
        "stock_initial": "5", "tarif_location_jour": "500",
    }

    result = page._submit_form(None, values)

    assert result is True
    created = next(a for a in stack.articles.list_articles() if a.reference == "ART-TARIF")
    assert created.tarif_location_jour == Decimal("500")


# -- Lot 12 : mode de gestion exposé dans les formulaires création/modif ----

def _base_values(category_id, **overrides) -> dict:
    values = {
        "reference": "ART-MODE", "designation": "Article", "category_id": category_id,
        "fournisseur_principal_id": None, "unite": "unité", "prix_achat": "100", "prix_vente": "150",
        "stock_min": "0", "stock_max": "", "emplacement": "", "code_barres": "", "description": "",
        "stock_initial": "0", "tarif_location_jour": "",
    }
    values.update(overrides)
    return values


def test_submit_form_creates_article_in_vente_mode_by_default(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(category.id, mode_gestion=ModeGestionArticle.VENTE)

    result = page._submit_form(None, values)

    assert result is True
    created = next(a for a in stack.articles.list_articles() if a.reference == "ART-MODE")
    assert created.mode_gestion == ModeGestionArticle.VENTE


def test_submit_form_creates_article_directly_in_location_mode(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(category.id, mode_gestion=ModeGestionArticle.LOCATION, tarif_location_jour="500")

    result = page._submit_form(None, values)

    assert result is True
    created = next(a for a in stack.articles.list_articles() if a.reference == "ART-MODE")
    assert created.mode_gestion == ModeGestionArticle.LOCATION
    assert created.tarif_location_jour == Decimal("500")


def test_submit_form_rejects_missing_tarif_for_location_mode_without_creating(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(category.id, mode_gestion=ModeGestionArticle.LOCATION, tarif_location_jour="")

    result = page._submit_form(None, values)

    assert result is False
    assert stack.articles.list_articles(search="ART-MODE") == []


def test_submit_form_rejects_zero_tarif_for_location_mode(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(category.id, mode_gestion=ModeGestionArticle.LOCATION, tarif_location_jour="0")

    result = page._submit_form(None, values)

    assert result is False
    assert stack.articles.list_articles(search="ART-MODE") == []


def test_submit_form_rejects_negative_tarif_for_location_mode(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(category.id, mode_gestion=ModeGestionArticle.LOCATION, tarif_location_jour="-10")

    result = page._submit_form(None, values)

    assert result is False
    assert stack.articles.list_articles(search="ART-MODE") == []


def test_load_edit_initial_includes_mode_gestion(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    article = stack.articles.create_article(
        "ART-EDIT-MODE", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        tarif_location_jour=Decimal("500"),
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(article.id)

    assert initial is not None
    assert initial["mode_gestion"] == ModeGestionArticle.LOCATION
    assert initial["tarif_location_jour"] == Decimal("500")


def test_submit_form_switches_existing_article_from_vente_to_location(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    article = stack.articles.create_article(
        "ART-V2L", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(
        category.id, reference="ART-V2L", mode_gestion=ModeGestionArticle.LOCATION, tarif_location_jour="500",
    )

    result = page._submit_form(article.id, values)

    assert result is True
    updated = stack.articles.get_article(article.id)
    assert updated.mode_gestion == ModeGestionArticle.LOCATION
    assert updated.tarif_location_jour == Decimal("500")


def test_submit_form_switches_existing_article_from_location_to_vente(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    article = stack.articles.create_article(
        "ART-L2V", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        tarif_location_jour=Decimal("500"),
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(
        category.id, reference="ART-L2V", mode_gestion=ModeGestionArticle.VENTE, tarif_location_jour="500",
    )

    result = page._submit_form(article.id, values)

    assert result is True
    updated = stack.articles.get_article(article.id)
    assert updated.mode_gestion == ModeGestionArticle.VENTE


def test_submit_form_refuses_switch_to_vente_while_location_in_progress(qtbot, login_as) -> None:
    """§6.9 du lot : une location physiquement en cours (qte_en_location
    non nulle) doit toujours bloquer le passage en mode Vente — même
    déclenché depuis ce formulaire — exactement comme le ferait le bouton
    « Mode de gestion… », puisque c'est le même service qui est appelé."""
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    client = stack.clients.create_client("Client Test")
    article = stack.articles.create_article(
        "ART-BLOQUE", "Article", category.id, "unité", Decimal("100"), Decimal("0"), Decimal("0"),
        stock_initial=Decimal("10"), tarif_location_jour=Decimal("500"),
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    from app.services.rentals.location_service import LocationLigneInput
    from datetime import date
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.confirm_location(location.id)
    stack.rentals.depart_location(location.id, date(2026, 1, 1))

    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(
        category.id, reference="ART-BLOQUE", mode_gestion=ModeGestionArticle.VENTE, tarif_location_jour="500",
    )

    result = page._submit_form(article.id, values)

    assert result is True  # les autres champs sont tout de même enregistrés
    updated = stack.articles.get_article(article.id)
    assert updated.mode_gestion == ModeGestionArticle.LOCATION  # la bascule elle-même a été refusée


def test_submit_form_preserves_data_after_update_without_mode_key(qtbot, login_as) -> None:
    """Non-régression explicite : un appel sans la clé ``mode_gestion``
    (comme les appels existants avant ce lot) ne doit jamais déclencher de
    bascule, même si l'article est en mode Location."""
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    article = stack.articles.create_article(
        "ART-NOKEY", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        tarif_location_jour=Decimal("500"),
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(category.id, reference="ART-NOKEY", tarif_location_jour="500")
    assert "mode_gestion" not in values  # absent, comme avant ce lot (clé jamais ajoutée)

    result = page._submit_form(article.id, values)

    assert result is True
    assert stack.articles.get_article(article.id).mode_gestion == ModeGestionArticle.LOCATION


def test_submit_form_history_records_switch_triggered_from_form(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    article = stack.articles.create_article(
        "ART-HIST", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = _base_values(
        category.id, reference="ART-HIST", mode_gestion=ModeGestionArticle.LOCATION, tarif_location_jour="500",
    )
    page._submit_form(article.id, values)

    from app.config.settings import get_settings
    from app.db.session import session_scope
    from app.models.catalog import ArticleModeGestionChangement
    with session_scope(get_settings()) as session:
        changements = (
            session.query(ArticleModeGestionChangement)
            .filter(ArticleModeGestionChangement.article_id == article.id)
            .all()
        )
        assert len(changements) == 1
        assert changements[0].nouveau_mode == ModeGestionArticle.LOCATION


# -- bouton « Mode de gestion… » existant : comportement inchangé ------------

def test_submit_mode_gestion_still_allows_switch_without_tarif(qtbot, login_as) -> None:
    """Non-régression explicite (§4D/§6.3 du lot) : le parcours existant
    « Mode de gestion… » reste aussi permissif qu'avant ce lot — seul le
    nouveau formulaire exige un tarif positif avant d'appeler ce même
    service."""
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Matériel")
    article = stack.articles.create_article(
        "ART-SANS-TARIF-BTN", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
    )
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_mode_gestion(article.id, ModeGestionArticle.LOCATION)

    assert result is True
    assert stack.articles.get_article(article.id).mode_gestion == ModeGestionArticle.LOCATION


def test_table_shows_most_recently_created_article_first(qtbot, login_as) -> None:
    """Chantier B : voir le test équivalent dans tests/test_categories_page.py
    — jamais l'ordre par référence de ArticleService.list_articles, réutilisé
    tel quel comme sélecteur ailleurs (Ventes, Locations, Entrées, Sorties...)."""
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Cat")
    older = stack.articles.create_article(
        "ART-Z-ANCIEN", "Ancien", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0")
    )
    newer = stack.articles.create_article(
        "ART-A-RECENT", "Récent", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0")
    )

    with session_scope(get_settings()) as session:
        session.query(Article).filter_by(id=older.id).update({"date_creation": datetime(2026, 1, 1, 8, 0, 0)})
        session.query(Article).filter_by(id=newer.id).update({"date_creation": datetime(2026, 6, 1, 8, 0, 0)})

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.item(0, 0).text() == "ART-A-RECENT"
    assert page.table.item(1, 0).text() == "ART-Z-ANCIEN"


# -- Mission 3, §7.2 : bouton Activer/Désactiver dynamique --------------------------


def test_toggle_button_neutral_label_without_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.selectionModel().selectedRows() == []
    assert page.toggle_button.text() == "Activer / désactiver"
    assert page.toggle_button.property("variant") is None


def test_toggle_button_shows_disable_in_orange_for_active_article(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.table.selectRow(0)

    assert page.toggle_button.text() == "Désactiver"
    assert page.toggle_button.property("variant") == "warning"


def test_toggle_button_shows_enable_in_green_for_inactive_article(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.articles.deactivate_article(article.id)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page.status_filter_combo.setCurrentIndex(0)  # "Tous" : l'article inactif doit apparaître

    page.table.selectRow(0)

    assert page.toggle_button.text() == "Activer"
    assert page.toggle_button.property("variant") == "success"


def test_toggle_button_updates_after_the_action_it_performs(qtbot, login_as) -> None:
    """Après désactivation, le bouton propose désormais Activer — jamais
    l'inverse (toujours l'action réellement possible, Mission 3, §7.2)."""
    stack, _ = login_as("Administrateur")
    _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page.table.selectRow(0)
    assert page.toggle_button.text() == "Désactiver"

    article_id = page.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
    assert page._toggle_status(article_id, currently_active=True) is True
    page.status_filter_combo.setCurrentIndex(0)  # "Tous" : l'article désormais inactif doit rester visible
    page.table.selectRow(0)

    assert page.toggle_button.text() == "Activer"
    assert page.toggle_button.property("variant") == "success"
