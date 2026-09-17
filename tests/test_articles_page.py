from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from app.views.pages.articles_page import ArticlesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.articles_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.articles_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> ArticlesPage:
    return ArticlesPage(stack.articles, stack.categories, stack.suppliers, stack.permissions)


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
