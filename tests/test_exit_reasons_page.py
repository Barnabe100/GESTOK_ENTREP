import pytest
from PySide6.QtWidgets import QMessageBox

from app.views.pages.exit_reasons_page import ExitReasonsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise les boîtes modales (information/warning) pour des tests
    automatisés non interactifs — voir la note équivalente dans test_users_page.py."""
    monkeypatch.setattr("app.views.pages.exit_reasons_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.exit_reasons_page.QMessageBox.warning", lambda *a, **k: None)


def test_exit_reasons_page_lists_reasons_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")

    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    labels = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "Perte" in labels


def test_exit_reasons_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")
    stack.exit_reasons.create_exit_reason("Casse")

    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    page.search_edit.setText("per")

    labels = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert labels == {"Perte"}


def test_exit_reasons_page_shows_status_column(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")
    stack.exit_reasons.deactivate_exit_reason(created.id)

    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == "Perte")
    assert page.table.item(row, 2).text() == "Inactif"


def test_exit_reasons_page_buttons_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True
    assert page.edit_button.isEnabled() is True
    assert page.toggle_button.isEnabled() is True


def test_exit_reasons_page_buttons_disabled_and_table_empty_for_gestionnaire(qtbot, login_as) -> None:
    """Décision métier : même le Gestionnaire de stock n'a aucune permission
    STOCK_REASON_* — la gestion des motifs est strictement réservée à l'Administrateur."""
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    page = ExitReasonsPage(gestionnaire_stack.exit_reasons, gestionnaire_stack.permissions)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0
    assert page.add_button.isEnabled() is False
    assert page.edit_button.isEnabled() is False
    assert page.toggle_button.isEnabled() is False


def test_exit_reasons_page_table_empty_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")

    vendeur_stack, _ = login_as("Vendeur")
    page = ExitReasonsPage(vendeur_stack.exit_reasons, vendeur_stack.permissions)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0


def test_submit_form_creates_reason_and_refreshes(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(None, "Nouveau motif", "")
    page.refresh()

    assert result is True
    labels = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "Nouveau motif" in labels


def test_submit_form_shows_error_on_duplicate_ignoring_case_and_space(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")
    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(None, "  PERTE  ", "")

    assert result is False
    assert len(stack.exit_reasons.list_exit_reasons()) == 1


def test_submit_form_updates_existing_reason(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")
    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_form(created.id, "Perte constatée", "Suite à inventaire")

    assert result is True
    updated = stack.exit_reasons.get_exit_reason(created.id)
    assert updated.libelle == "Perte constatée"
    assert updated.description == "Suite à inventaire"


def test_toggle_status_deactivates_and_reactivates(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")
    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    assert page._toggle_status(created.id, currently_active=True) is True
    assert stack.exit_reasons.get_exit_reason(created.id).actif is False

    assert page._toggle_status(created.id, currently_active=False) is True
    assert stack.exit_reasons.get_exit_reason(created.id).actif is True


def test_toggle_status_denied_without_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.exit_reasons.create_exit_reason("Perte")

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    page = ExitReasonsPage(gestionnaire_stack.exit_reasons, gestionnaire_stack.permissions)
    qtbot.addWidget(page)

    result = page._toggle_status(created.id, currently_active=True)

    assert result is False
    assert admin_stack.exit_reasons.get_exit_reason(created.id).actif is True


def test_confirmation_dialog_no_cancels_toggle(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")
    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    page.table.selectRow(0)
    page._on_toggle_clicked()

    assert stack.exit_reasons.get_exit_reason(created.id).actif is True


def test_confirmation_dialog_yes_proceeds_with_toggle(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")
    page = ExitReasonsPage(stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    page.table.selectRow(0)
    page._on_toggle_clicked()

    assert stack.exit_reasons.get_exit_reason(created.id).actif is False
