import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.services.auth.account_recovery_service import AccountRecoveryService
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.views.login_window import LoginWindow


def _build_login_window(initialized_db, parent=None) -> tuple[LoginWindow, AuthService]:
    auth_service = AuthService(initialized_db)
    permission_service = PermissionService(auth_service)
    account_recovery_service = AccountRecoveryService(permission_service, initialized_db)
    return LoginWindow(auth_service, account_recovery_service, parent), auth_service


def test_login_window_accepts_on_valid_credentials(qtbot, make_user, initialized_db) -> None:
    make_user("Administrateur", "loginuser", "Password!23")
    window, auth_service = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("loginuser")
    window.password_edit.setText("Password!23")

    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert window.result() == QDialog.DialogCode.Accepted
    assert auth_service.is_authenticated is True


def test_login_window_shows_error_on_wrong_password(qtbot, make_user, initialized_db) -> None:
    make_user("Vendeur", "wronguser", "Password!23")
    window, auth_service = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("wronguser")
    window.password_edit.setText("MauvaisMotDePasse")
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert "incorrect" in window.error_label.text().lower()
    assert auth_service.is_authenticated is False


def test_login_window_shows_error_on_unknown_user(qtbot, initialized_db) -> None:
    window, auth_service = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("personne")
    window.password_edit.setText("peu importe")
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert "incorrect" in window.error_label.text().lower()


def test_login_window_shows_specific_message_for_disabled_account(qtbot, make_user, initialized_db) -> None:
    make_user("Vendeur", "disableduser", "Password!23", actif=False)
    window, auth_service = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("disableduser")
    window.password_edit.setText("Password!23")
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert "désactivé" in window.error_label.text().lower()
    assert auth_service.is_authenticated is False


def test_login_window_requires_both_fields(qtbot, initialized_db) -> None:
    window, auth_service = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert window.error_label.text() != ""
    assert auth_service.is_authenticated is False


def test_login_window_enter_key_submits(qtbot, make_user, initialized_db) -> None:
    make_user("Administrateur", "enteruser", "Password!23")
    window, auth_service = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("enteruser")
    window.password_edit.setText("Password!23")

    qtbot.keyClick(window.password_edit, Qt.Key.Key_Return)

    assert window.result() == QDialog.DialogCode.Accepted
    assert auth_service.is_authenticated is True


# -- mot de passe oublié ----------------------------------------------------------


def test_forgot_password_button_present(qtbot, initialized_db) -> None:
    window, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    assert window.forgot_password_button.text() == "Mot de passe oublié ?"


def test_submit_account_recovery_with_valid_code_allows_relogin(
    qtbot, login_as, initialized_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.views.account_recovery_dialog import AccountRecoveryDialog

    monkeypatch.setattr("app.views.login_window.QMessageBox.information", lambda *a, **k: None)
    admin_stack, current_user = login_as("Administrateur")
    code = admin_stack.account_recovery.generate_code()

    window, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    dialog = AccountRecoveryDialog()
    dialog.username_edit.setText(current_user.username)
    dialog.code_edit.setText(code)
    dialog.new_password_edit.setText("ApresRecuperation!1")
    dialog.confirm_password_edit.setText("ApresRecuperation!1")

    result = window._submit_account_recovery(dialog)

    assert result is True
    # reset_password_with_code ne connecte jamais automatiquement : il faut
    # explicitement se reconnecter avec le nouveau mot de passe.
    new_login = window._auth_service.login(current_user.username, "ApresRecuperation!1")
    assert new_login.username == current_user.username


def test_submit_account_recovery_with_wrong_code_sets_dialog_error(qtbot, login_as, initialized_db) -> None:
    from app.views.account_recovery_dialog import AccountRecoveryDialog

    admin_stack, current_user = login_as("Administrateur")
    admin_stack.account_recovery.generate_code()

    window, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    dialog = AccountRecoveryDialog()
    dialog.username_edit.setText(current_user.username)
    dialog.code_edit.setText("code-invalide")
    dialog.new_password_edit.setText("ApresRecuperation!1")
    dialog.confirm_password_edit.setText("ApresRecuperation!1")

    result = window._submit_account_recovery(dialog)

    assert result is False
    assert dialog.error_label.text() != ""
