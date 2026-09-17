from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from app.views.pages.users_page import UsersPage


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
