from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.services.auth.auth_service import AuthService
from app.views.change_password_dialog import ChangePasswordDialog


def test_change_password_dialog_success(qtbot, make_user, initialized_db) -> None:
    make_user("Vendeur", "pwuser", "AncienMotDePasse1")
    auth_service = AuthService(initialized_db)
    auth_service.login("pwuser", "AncienMotDePasse1")

    dialog = ChangePasswordDialog(auth_service)
    qtbot.addWidget(dialog)
    dialog.old_password_edit.setText("AncienMotDePasse1")
    dialog.new_password_edit.setText("NouveauMotDePasse1")
    dialog.confirm_password_edit.setText("NouveauMotDePasse1")

    qtbot.mouseClick(dialog.submit_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert auth_service.current_user.must_change_password is False


def test_change_password_dialog_shows_error_on_mismatch(qtbot, make_user, initialized_db) -> None:
    make_user("Vendeur", "pwuser2", "AncienMotDePasse1")
    auth_service = AuthService(initialized_db)
    auth_service.login("pwuser2", "AncienMotDePasse1")

    dialog = ChangePasswordDialog(auth_service)
    qtbot.addWidget(dialog)
    dialog.old_password_edit.setText("AncienMotDePasse1")
    dialog.new_password_edit.setText("NouveauMotDePasse1")
    dialog.confirm_password_edit.setText("Different123456")

    qtbot.mouseClick(dialog.submit_button, Qt.MouseButton.LeftButton)

    assert "correspondent" in dialog.error_label.text().lower()


def test_change_password_dialog_shows_error_on_wrong_current_password(
    qtbot, make_user, initialized_db
) -> None:
    make_user("Vendeur", "pwuser3", "AncienMotDePasse1")
    auth_service = AuthService(initialized_db)
    auth_service.login("pwuser3", "AncienMotDePasse1")

    dialog = ChangePasswordDialog(auth_service)
    qtbot.addWidget(dialog)
    dialog.old_password_edit.setText("MauvaisAncien")
    dialog.new_password_edit.setText("NouveauMotDePasse1")
    dialog.confirm_password_edit.setText("NouveauMotDePasse1")

    qtbot.mouseClick(dialog.submit_button, Qt.MouseButton.LeftButton)

    assert dialog.error_label.text() != ""


def test_change_password_dialog_forced_mode_hides_close_button(qtbot, make_user, initialized_db) -> None:
    make_user("Vendeur", "pwuser4", "AncienMotDePasse1")
    auth_service = AuthService(initialized_db)
    auth_service.login("pwuser4", "AncienMotDePasse1")

    dialog = ChangePasswordDialog(auth_service, forced=True)
    qtbot.addWidget(dialog)

    assert not (dialog.windowFlags() & Qt.WindowType.WindowCloseButtonHint)
