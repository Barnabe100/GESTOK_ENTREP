import pytest
from PySide6.QtWidgets import QMessageBox

from app.views.pages.categories_page import CategoriesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise les boîtes modales (information/warning/question) pour des
    tests automatisés non interactifs — voir la note équivalente dans
    test_users_page.py."""
    monkeypatch.setattr("app.views.pages.categories_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.categories_page.QMessageBox.warning", lambda *a, **k: None)


def test_categories_page_lists_categories_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.categories.create_category("Boissons")

    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "Boissons" in names


def test_categories_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.categories.create_category("Boissons")
    stack.categories.create_category("Épicerie")

    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    page.search_edit.setText("bois")

    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert names == {"Boissons"}


def test_categories_page_shows_status_column(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.categories.create_category("Boissons")
    stack.categories.deactivate_category(created.id)

    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "Boissons")
    assert page.table.item(row, 1).text() == "Inactif"


def test_categories_page_buttons_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True
    assert page.edit_button.isEnabled() is True
    assert page.toggle_button.isEnabled() is True


def test_categories_page_buttons_disabled_for_consultation(qtbot, login_as) -> None:
    """Consultation a CATEGORY_VIEW (la table se remplit) mais aucune permission d'écriture."""
    stack, _ = login_as("Administrateur")
    stack.categories.create_category("Boissons")

    consultation_stack, _ = login_as("Consultation")
    page = CategoriesPage(consultation_stack.categories, consultation_stack.permissions)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 1  # CATEGORY_VIEW accordé : la liste s'affiche
    assert page.add_button.isEnabled() is False
    assert page.edit_button.isEnabled() is False
    assert page.toggle_button.isEnabled() is False


def test_categories_page_table_empty_for_vendeur(qtbot, login_as) -> None:
    """Le Vendeur n'a pas CATEGORY_VIEW : la page ne doit rien afficher."""
    stack, _ = login_as("Administrateur")
    stack.categories.create_category("Boissons")

    vendeur_stack, _ = login_as("Vendeur")
    page = CategoriesPage(vendeur_stack.categories, vendeur_stack.permissions)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0


def test_submit_form_creates_category_and_refreshes(qtbot, login_as) -> None:
    """``_submit_form`` effectue l'appel service ; le rafraîchissement de la table est
    à la charge de l'appelant (``_open_form_dialog``), reproduit ici explicitement."""
    stack, _ = login_as("Administrateur")
    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(None, "Nouvelle catégorie")
    page.refresh()

    assert result is True
    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "Nouvelle catégorie" in names


def test_submit_form_shows_error_on_duplicate_and_does_not_crash(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.categories.create_category("Boissons")
    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(None, "Boissons")

    assert result is False
    # Une seule catégorie "Boissons" doit exister (pas de doublon créé).
    assert len(stack.categories.list_categories(search="Boissons")) == 1


def test_submit_form_updates_existing_category(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.categories.create_category("Boissons")
    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(created.id, "Boissons fraîches")

    assert result is True
    updated = stack.categories.get_category(created.id)
    assert updated.nom == "Boissons fraîches"


def test_toggle_status_deactivates_and_reactivates(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.categories.create_category("Boissons")
    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    assert page._toggle_status(created.id, currently_active=True) is True
    assert stack.categories.get_category(created.id).actif is False

    assert page._toggle_status(created.id, currently_active=False) is True
    assert stack.categories.get_category(created.id).actif is True


def test_toggle_status_denied_without_permission(qtbot, login_as, make_user) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.categories.create_category("Boissons")

    consultation_stack, _ = login_as("Consultation")
    page = CategoriesPage(consultation_stack.categories, consultation_stack.permissions)
    qtbot.addWidget(page)

    result = page._toggle_status(created.id, currently_active=True)

    assert result is False
    assert admin_stack.categories.get_category(created.id).actif is True


def test_confirmation_dialog_no_cancels_toggle(qtbot, login_as, monkeypatch) -> None:
    """La confirmation avant une opération sensible peut être refusée par l'utilisateur."""
    stack, _ = login_as("Administrateur")
    created = stack.categories.create_category("Boissons")
    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.pages.categories_page.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "Boissons")
    page.table.selectRow(row)
    page._on_toggle_clicked()

    assert stack.categories.get_category(created.id).actif is True


def test_confirmation_dialog_yes_proceeds_with_toggle(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.categories.create_category("Boissons")
    page = CategoriesPage(stack.categories, stack.permissions)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.pages.categories_page.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "Boissons")
    page.table.selectRow(row)
    page._on_toggle_clicked()

    assert stack.categories.get_category(created.id).actif is False
