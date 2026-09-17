import pytest
from PySide6.QtWidgets import QMessageBox

from app.views.pages.suppliers_page import SuppliersPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise les boîtes modales (information/warning) pour des tests
    automatisés non interactifs — voir la note équivalente dans test_users_page.py."""
    monkeypatch.setattr("app.views.pages.suppliers_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.suppliers_page.QMessageBox.warning", lambda *a, **k: None)


def test_suppliers_page_lists_suppliers_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.suppliers.create_supplier("Fournisseur A")

    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "Fournisseur A" in names


def test_suppliers_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.suppliers.create_supplier("Martin SARL")
    stack.suppliers.create_supplier("Dupont SA")

    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    page.search_edit.setText("martin")

    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert names == {"Martin SARL"}


def test_suppliers_page_shows_status_and_contact_columns(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur", contact="Jean", ville="Lyon")
    stack.suppliers.deactivate_supplier(created.id)

    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "Fournisseur")
    assert page.table.item(row, 1).text() == "Jean"
    assert page.table.item(row, 4).text() == "Lyon"
    assert page.table.item(row, 5).text() == "Inactif"


def test_suppliers_page_buttons_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True
    assert page.edit_button.isEnabled() is True
    assert page.toggle_button.isEnabled() is True


def test_suppliers_page_buttons_disabled_for_consultation(qtbot, login_as) -> None:
    """Consultation a SUPPLIER_VIEW (la table se remplit) mais aucune permission d'écriture."""
    stack, _ = login_as("Administrateur")
    stack.suppliers.create_supplier("Fournisseur")

    consultation_stack, _ = login_as("Consultation")
    page = SuppliersPage(consultation_stack.suppliers, consultation_stack.permissions)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 1
    assert page.add_button.isEnabled() is False
    assert page.edit_button.isEnabled() is False
    assert page.toggle_button.isEnabled() is False


def test_suppliers_page_table_empty_for_vendeur(qtbot, login_as) -> None:
    """Le Vendeur n'a pas SUPPLIER_VIEW : la page ne doit rien afficher."""
    stack, _ = login_as("Administrateur")
    stack.suppliers.create_supplier("Fournisseur")

    vendeur_stack, _ = login_as("Vendeur")
    page = SuppliersPage(vendeur_stack.suppliers, vendeur_stack.permissions)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0


def test_submit_form_creates_supplier_and_refreshes(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(
        None,
        {"nom": "Nouveau fournisseur", "contact": "", "telephone": "", "email": "",
         "adresse": "", "ville": "", "pays": "", "observations": ""},
    )
    page.refresh()

    assert result is True
    names = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "Nouveau fournisseur" in names


def test_submit_form_shows_error_on_invalid_email_and_does_not_crash(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(
        None,
        {"nom": "Fournisseur", "contact": "", "telephone": "", "email": "invalide",
         "adresse": "", "ville": "", "pays": "", "observations": ""},
    )

    assert result is False
    assert stack.suppliers.list_suppliers(search="Fournisseur") == []


def test_submit_form_updates_existing_supplier(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur")
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(
        created.id,
        {"nom": "Fournisseur renommé", "contact": "", "telephone": "", "email": "",
         "adresse": "", "ville": "Nantes", "pays": "", "observations": ""},
    )

    assert result is True
    updated = stack.suppliers.get_supplier(created.id)
    assert updated.nom == "Fournisseur renommé"
    assert updated.ville == "Nantes"


def test_load_edit_initial_returns_full_supplier_details(qtbot, login_as) -> None:
    """La modification doit préserver les champs non affichés en colonnes
    (adresse, pays, observations)."""
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier(
        "Fournisseur", adresse="12 rue des Fleurs", pays="Belgique", observations="Confidentiel"
    )
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(created.id)

    assert initial is not None
    assert initial["nom"] == "Fournisseur"
    assert initial["adresse"] == "12 rue des Fleurs"
    assert initial["pays"] == "Belgique"
    assert initial["observations"] == "Confidentiel"


def test_load_edit_initial_returns_none_and_warns_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(999999)

    assert initial is None


def test_toggle_status_deactivates_and_reactivates(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur")
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    assert page._toggle_status(created.id, currently_active=True) is True
    assert stack.suppliers.get_supplier(created.id).actif is False

    assert page._toggle_status(created.id, currently_active=False) is True
    assert stack.suppliers.get_supplier(created.id).actif is True


def test_toggle_status_denied_without_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.suppliers.create_supplier("Fournisseur")

    consultation_stack, _ = login_as("Consultation")
    page = SuppliersPage(consultation_stack.suppliers, consultation_stack.permissions)
    qtbot.addWidget(page)

    result = page._toggle_status(created.id, currently_active=True)

    assert result is False
    assert admin_stack.suppliers.get_supplier(created.id).actif is True


def test_confirmation_dialog_no_cancels_toggle(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur")
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    page.table.selectRow(0)
    page._on_toggle_clicked()

    assert stack.suppliers.get_supplier(created.id).actif is True


def test_confirmation_dialog_yes_proceeds_with_toggle(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur")
    page = SuppliersPage(stack.suppliers, stack.permissions)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    page.table.selectRow(0)
    page._on_toggle_clicked()

    assert stack.suppliers.get_supplier(created.id).actif is False
