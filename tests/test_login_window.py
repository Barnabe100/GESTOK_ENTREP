from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.services.auth.auth_service import AuthService
from app.views.login_window import LoginWindow


def test_login_window_accepts_on_valid_credentials(qtbot, make_user, initialized_db) -> None:
    make_user("Administrateur", "loginuser", "Password!23")
    auth_service = AuthService(initialized_db)
    window = LoginWindow(auth_service)
    qtbot.addWidget(window)

    window.username_edit.setText("loginuser")
    window.password_edit.setText("Password!23")

    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert window.result() == QDialog.DialogCode.Accepted
    assert auth_service.is_authenticated is True


def test_login_window_shows_error_on_wrong_password(qtbot, make_user, initialized_db) -> None:
    make_user("Vendeur", "wronguser", "Password!23")
    auth_service = AuthService(initialized_db)
    window = LoginWindow(auth_service)
    qtbot.addWidget(window)

    window.username_edit.setText("wronguser")
    window.password_edit.setText("MauvaisMotDePasse")
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert "incorrect" in window.error_label.text().lower()
    assert auth_service.is_authenticated is False


def test_login_window_shows_error_on_unknown_user(qtbot, initialized_db) -> None:
    auth_service = AuthService(initialized_db)
    window = LoginWindow(auth_service)
    qtbot.addWidget(window)

    window.username_edit.setText("personne")
    window.password_edit.setText("peu importe")
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert "incorrect" in window.error_label.text().lower()


def test_login_window_shows_specific_message_for_disabled_account(qtbot, make_user, initialized_db) -> None:
    make_user("Vendeur", "disableduser", "Password!23", actif=False)
    auth_service = AuthService(initialized_db)
    window = LoginWindow(auth_service)
    qtbot.addWidget(window)

    window.username_edit.setText("disableduser")
    window.password_edit.setText("Password!23")
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert "désactivé" in window.error_label.text().lower()
    assert auth_service.is_authenticated is False


def test_login_window_requires_both_fields(qtbot, initialized_db) -> None:
    auth_service = AuthService(initialized_db)
    window = LoginWindow(auth_service)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert window.error_label.text() != ""
    assert auth_service.is_authenticated is False


def test_login_window_enter_key_submits(qtbot, make_user, initialized_db) -> None:
    make_user("Administrateur", "enteruser", "Password!23")
    auth_service = AuthService(initialized_db)
    window = LoginWindow(auth_service)
    qtbot.addWidget(window)

    window.username_edit.setText("enteruser")
    window.password_edit.setText("Password!23")

    qtbot.keyClick(window.password_edit, Qt.Key.Key_Return)

    assert window.result() == QDialog.DialogCode.Accepted
    assert auth_service.is_authenticated is True
