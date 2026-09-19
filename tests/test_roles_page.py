import pytest
from PySide6.QtWidgets import QCheckBox, QTableWidget

from app.views.edit_role_permissions_dialog import EditRolePermissionsDialog
from app.views.pages.roles_page import RolesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.roles_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.roles_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> RolesPage:
    return RolesPage(stack.roles, stack.permissions)


def _role_id(stack, role_name: str) -> int:
    return next(r.id for r in stack.roles.list_roles() if r.nom == role_name)


# -- affichage --------------------------------------------------------------------------


def test_page_lists_the_four_system_roles(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")

    page = _build_page(stack)
    qtbot.addWidget(page)

    noms = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert noms == {"Administrateur", "Gestionnaire de stock", "Vendeur", "Consultation"}


def test_columns_include_required_fields(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    assert headers == ["Rôle", "Description", "Utilisateurs actifs"]


def test_page_has_no_create_delete_or_rename_controls(qtbot, login_as) -> None:
    """V1 strictement A+B : ni création, ni suppression, ni renommage."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert not hasattr(page, "add_button")
    assert not hasattr(page, "delete_button")
    assert not hasattr(page, "rename_button")
    assert page.table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers


# -- permissions (accès page) ------------------------------------------------------------


def test_gestionnaire_stock_cannot_view_roles(qtbot, login_as) -> None:
    """Gestionnaire de stock n'a pas ROLE_VIEW (seule Administrateur l'a)."""
    stack, _ = login_as("Gestionnaire de stock")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0


# -- sélection / consultation des permissions --------------------------------------------


def test_selecting_a_role_shows_its_permissions(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    for row in range(page.table.rowCount()):
        if page.table.item(row, 0).text() == "Vendeur":
            page.table.selectRow(row)
            break

    assert "Vendeur" in page.role_title_label.text()
    checkboxes = page._permissions_container.findChildren(QCheckBox)
    assert any(cb.text().startswith("Créer une vente") or "vente" in cb.text().lower() for cb in checkboxes)


def test_permissions_panel_grouped_by_module(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QGroupBox

    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page.table.selectRow(0)

    groups = page._permissions_container.findChildren(QGroupBox)
    assert len(groups) > 1  # plusieurs modules distincts


def test_consultation_panel_checkboxes_are_never_directly_editable(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page.table.selectRow(0)

    checkboxes = page._permissions_container.findChildren(QCheckBox)
    assert len(checkboxes) > 0
    assert all(not cb.isEnabled() for cb in checkboxes)


# -- bouton Modifier selon ROLE_UPDATE ----------------------------------------------------


def test_edit_button_enabled_for_administrateur_after_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.table.selectRow(0)

    assert page.edit_button.isEnabled() is True


def test_edit_button_disabled_without_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.edit_button.isEnabled() is False


# -- sauvegarde / rafraîchissement --------------------------------------------------------


def test_submit_update_permissions_succeeds_and_refreshes(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_update_permissions(role_id, ["ARTICLE_VIEW"])
    page.refresh()

    assert result is True
    assert set(stack.roles.get_role_permissions(role_id)) == {"ARTICLE_VIEW"}


def test_submit_update_permissions_shows_error_on_admin_guard_violation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_update_permissions(role_id, [])

    assert result is False
    assert "ROLE_UPDATE" in stack.roles.get_role_permissions(role_id)


def test_submit_update_permissions_denied_for_role_without_role_update(qtbot, login_as, make_user) -> None:
    """Contournement de l'interface : même en appelant directement la
    méthode de soumission, la modification reste refusée côté service pour
    un rôle sans ROLE_UPDATE."""
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._submit_update_permissions(1, ["ARTICLE_VIEW"])

    assert result is False


# -- dialogue : protections Administrateur -------------------------------------------------


def test_dialog_locks_protected_checkboxes_for_administrateur_role(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Administrateur")
    current_codes = set(stack.roles.get_role_permissions(role_id))
    permissions = stack.roles.list_permissions()
    protected = {"ROLE_VIEW", "ROLE_UPDATE", "USER_VIEW", "USER_UPDATE"}

    dialog = EditRolePermissionsDialog("Administrateur", permissions, current_codes, protected)
    qtbot.addWidget(dialog)

    for code in protected:
        checkbox = dialog._checkboxes[code]
        assert checkbox.isChecked() is True
        assert checkbox.isEnabled() is False


def test_dialog_selected_codes_always_include_locked_protected_permissions(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Administrateur")
    current_codes = set(stack.roles.get_role_permissions(role_id))
    permissions = stack.roles.list_permissions()
    protected = {"ROLE_VIEW", "ROLE_UPDATE", "USER_VIEW", "USER_UPDATE"}

    dialog = EditRolePermissionsDialog("Administrateur", permissions, current_codes, protected)
    qtbot.addWidget(dialog)

    assert protected <= set(dialog.selected_codes())


def test_dialog_non_admin_role_has_no_locked_checkboxes(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Vendeur")
    current_codes = set(stack.roles.get_role_permissions(role_id))
    permissions = stack.roles.list_permissions()

    dialog = EditRolePermissionsDialog("Vendeur", permissions, current_codes, frozenset())
    qtbot.addWidget(dialog)

    assert all(cb.isEnabled() for cb in dialog._checkboxes.values())


def test_dialog_unchecking_a_permission_removes_it_from_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Vendeur")
    current_codes = set(stack.roles.get_role_permissions(role_id))
    permissions = stack.roles.list_permissions()

    dialog = EditRolePermissionsDialog("Vendeur", permissions, current_codes, frozenset())
    qtbot.addWidget(dialog)

    a_code = next(iter(current_codes))
    dialog._checkboxes[a_code].setChecked(False)

    assert a_code not in dialog.selected_codes()


# -- erreurs métier affichées --------------------------------------------------------------


def test_business_error_is_displayed_via_warning(qtbot, login_as, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    warnings: list[str] = []
    monkeypatch.setattr(
        "app.views.pages.roles_page.QMessageBox.warning",
        lambda parent, title, message: warnings.append(message),
    )

    page._submit_update_permissions(role_id, [])

    assert len(warnings) == 1
    assert "Administrateur" in warnings[0]
