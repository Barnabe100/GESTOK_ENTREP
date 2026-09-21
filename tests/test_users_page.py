import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from app.views.pages.users_page import UsersPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.users_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.users_page.QMessageBox.warning", lambda *a, **k: None)


def test_users_page_lists_users_for_administrateur(qtbot, login_as, make_user) -> None:
    make_user("Vendeur", "listed_user")
    stack, _ = login_as("Administrateur")

    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    usernames = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "listed_user" in usernames


def test_users_page_toggle_button_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    assert page.toggle_button.isEnabled() is True


def test_submit_create_user_rejects_missing_role(qtbot, login_as) -> None:
    """Garde explicite (audit champs obligatoires) : un role_id manquant est
    refusé avec un message clair, avant même l'appel au service — jamais un
    NotFoundError confus (« Rôle None introuvable »)."""
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_create_user("nouvel_utilisateur", "MotDePasse!23", None, True)

    assert result is False
    assert "nouvel_utilisateur" not in {u.username for u in stack.users.list_users()}


def test_submit_update_user_rejects_missing_role(qtbot, login_as) -> None:
    stack, current_user = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_update_user(current_user.id, None)

    assert result is False


def test_users_page_toggle_button_disabled_and_table_empty_for_vendeur(qtbot, login_as) -> None:
    """Un Vendeur n'a ni USER_VIEW ni USER_ACTIVATE : la page, si elle était atteinte,
    n'affiche rien et son bouton d'action est désactivé."""
    stack, _ = login_as("Vendeur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    assert page.toggle_button.isEnabled() is False
    assert page.table.rowCount() == 0


def test_users_page_action_is_blocked_even_if_button_force_enabled(
    qtbot, login_as, make_user, monkeypatch
) -> None:
    """Preuve de non-contournement : même si le bouton était réactivé de force
    (bug d'interface, manipulation via un débogueur, etc.), l'action reste
    refusée car la vérification réelle est effectuée par UserService, pas par
    l'état (enabled/disabled) du bouton."""
    # QMessageBox.warning() ouvre une boîte modale bloquante (attend un clic
    # utilisateur) : on la neutralise pour un test automatisé non interactif.
    monkeypatch.setattr(
        "app.views.pages.users_page.QMessageBox.warning", lambda *args, **kwargs: None
    )

    make_user("Vendeur", "victime_ui")

    admin_stack, _ = login_as("Administrateur")
    target_id = next(u.id for u in admin_stack.users.list_users() if u.username == "victime_ui")

    vendeur_stack, _ = login_as("Vendeur")

    page = UsersPage(vendeur_stack.users, vendeur_stack.permissions)
    qtbot.addWidget(page)

    # Manipulation simulée de l'interface : on force l'activation du bouton et on
    # peuple manuellement une ligne de table (contournement direct des vérifications d'UI).
    page.toggle_button.setEnabled(True)
    page.table.setRowCount(1)
    item = QTableWidgetItem("victime_ui")
    item.setData(Qt.ItemDataRole.UserRole, target_id)
    page.table.setItem(0, 0, item)
    page.table.setItem(0, 1, QTableWidgetItem("Vendeur"))
    page.table.setItem(0, 2, QTableWidgetItem("Actif"))
    page.table.setItem(0, 3, QTableWidgetItem("—"))
    page.table.selectRow(0)

    qtbot.mouseClick(page.toggle_button, Qt.MouseButton.LeftButton)

    # Le service doit avoir refusé l'action : le compte cible reste actif en base.
    target_summary = next(u for u in admin_stack.users.list_users() if u.username == "victime_ui")
    assert target_summary.actif is True


# -- création d'utilisateur ----------------------------------------------------------


def test_add_button_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True


def test_add_button_disabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is False


def test_submit_create_user_succeeds_and_refreshes_list(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)
    role_id = next(r.id for r in stack.users.list_roles() if r.nom == "Vendeur")

    result = page._submit_create_user("nouveau_via_ui", "MotDePasse!23", [role_id], True)
    page.refresh()

    assert result is True
    usernames = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "nouveau_via_ui" in usernames


def test_submit_create_user_shows_error_on_duplicate_username(qtbot, login_as, make_user) -> None:
    make_user("Vendeur", "existe_deja")
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)
    role_id = next(r.id for r in stack.users.list_roles() if r.nom == "Vendeur")

    result = page._submit_create_user("existe_deja", "MotDePasse!23", [role_id], True)

    assert result is False


def test_submit_create_user_denied_for_role_without_permission(qtbot, login_as) -> None:
    """Contournement de l'interface : même en appelant directement la
    méthode de soumission (sans passer par le bouton désactivé), la
    création reste refusée côté service pour un rôle non autorisé."""
    stack, _ = login_as("Vendeur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_create_user("intrus_ui", "MotDePasse!23", [1], True)

    assert result is False
    admin_stack, _ = login_as("Administrateur")
    usernames = {u.username for u in admin_stack.users.list_users()}
    assert "intrus_ui" not in usernames


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_submit_create_user_succeeds_for_each_role_via_ui(qtbot, login_as, role_name: str) -> None:
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)
    role_id = next(r.id for r in stack.users.list_roles() if r.nom == role_name)
    username = f"ui_{role_name.split()[0].lower()}"

    result = page._submit_create_user(username, "MotDePasse!23", [role_id], True)

    assert result is True
    created = next(u for u in stack.users.list_users() if u.username == username)
    assert created.role_names == (role_name,)


# -- modification du rôle -------------------------------------------------------------


def test_edit_button_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    assert page.edit_button.isEnabled() is True


def test_edit_button_disabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    assert page.edit_button.isEnabled() is False


def test_submit_update_user_succeeds_and_refreshes_list(qtbot, login_as, make_user) -> None:
    make_user("Vendeur", "cible_ui_edit")
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_ui_edit")
    role_id = next(r.id for r in stack.users.list_roles() if r.nom == "Gestionnaire de stock")

    result = page._submit_update_user(target_id, [role_id])
    page.refresh()

    assert result is True
    updated = next(u for u in stack.users.list_users() if u.username == "cible_ui_edit")
    assert updated.role_names == ("Gestionnaire de stock",)


def test_submit_update_user_shows_error_when_blocked_by_admin_guard(qtbot, login_as) -> None:
    """Contournement de l'interface : même via l'appel direct de soumission,
    l'auto-retrait du rôle Administrateur reste refusé côté service."""
    stack, current_user = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)
    role_id = next(r.id for r in stack.users.list_roles() if r.nom == "Vendeur")

    result = page._submit_update_user(current_user.id, [role_id])

    assert result is False
    unchanged = next(u for u in stack.users.list_users() if u.id == current_user.id)
    assert unchanged.role_names == ("Administrateur",)


def test_submit_update_user_denied_for_role_without_permission(qtbot, login_as, make_user) -> None:
    make_user("Vendeur", "cible_ui_refus")
    stack, _ = login_as("Vendeur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_update_user(1, [1])

    assert result is False


# -- réinitialisation du mot de passe --------------------------------------------------


def test_reset_password_button_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    assert page.reset_password_button.isEnabled() is True


def test_reset_password_button_disabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    assert page.reset_password_button.isEnabled() is False


def test_submit_reset_password_succeeds(qtbot, login_as, make_user) -> None:
    make_user("Vendeur", "cible_ui_reset", "MotDePasseInitial1")
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_ui_reset")

    result = page._submit_reset_password(target_id, "NouveauMotDePasse99")

    assert result is True
    stack.auth.logout()
    reconnected = stack.auth.login("cible_ui_reset", "NouveauMotDePasse99")
    assert reconnected.must_change_password is True


def test_submit_reset_password_shows_error_on_too_short_password(qtbot, login_as, make_user) -> None:
    make_user("Vendeur", "cible_ui_reset_court")
    stack, _ = login_as("Administrateur")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_ui_reset_court")

    result = page._submit_reset_password(target_id, "court")

    assert result is False


def test_submit_reset_password_denied_for_role_without_permission(qtbot, login_as, make_user) -> None:
    make_user("Vendeur", "cible_ui_reset_refus")
    stack, _ = login_as("Consultation")
    page = UsersPage(stack.users, stack.permissions)
    qtbot.addWidget(page)

    result = page._submit_reset_password(1, "NouveauMotDePasse99")

    assert result is False
