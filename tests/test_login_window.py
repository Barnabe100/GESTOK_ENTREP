from typing import Optional

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.security.remembered_login import get_remembered_username
from app.services.auth.account_recovery_service import AccountRecoveryService
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import CredentialVaultUnavailableError
from app.views.login_window import LoginWindow


def _build_login_window(initialized_db, parent=None) -> tuple[LoginWindow, AuthService]:
    auth_service = AuthService(initialized_db)
    permission_service = PermissionService(auth_service)
    account_recovery_service = AccountRecoveryService(permission_service, initialized_db)
    return (
        LoginWindow(auth_service, account_recovery_service, initialized_db.data_dir, parent),
        auth_service,
    )


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


# -- « Se souvenir de moi » (phase amélioration UX, point 1) --------------------------
#
# Coffre réel inaccessible dans ce sandbox Linux (``get_login_credential_vault``
# lève toujours ``CredentialVaultUnavailableError`` hors Windows, par
# construction — voir app.security.credential_vault). Un substitut contrôlé
# (``_FakeLoginCredentialVault``) prouve le comportement attendu côté
# application sans jamais dépendre de Windows Credential Manager ; la
# validation réelle du coffre Windows reste à faire sur un poste Windows
# (voir le rapport de ce lot).


class _FakeLoginCredentialVault:
    """Substitut contrôlé — même interface que ``CredentialVault``, jamais
    partagé avec le coffre PostgreSQL (voir
    ``app.security.credential_vault``)."""

    def __init__(self) -> None:
        self.passwords: dict[str, str] = {}

    def get_password(self, profile_id: str) -> Optional[str]:
        return self.passwords.get(profile_id)

    def set_password(self, profile_id: str, password: str) -> None:
        self.passwords[profile_id] = password

    def delete_password(self, profile_id: str) -> None:
        self.passwords.pop(profile_id, None)


@pytest.fixture()
def fake_login_vault(monkeypatch: pytest.MonkeyPatch) -> _FakeLoginCredentialVault:
    vault = _FakeLoginCredentialVault()
    monkeypatch.setattr("app.security.remembered_login.get_login_credential_vault", lambda: vault)
    return vault


def test_remember_me_checked_saves_username_and_password(
    qtbot, make_user, initialized_db, fake_login_vault
) -> None:
    make_user("Vendeur", "rememberuser", "Password!23")
    window, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("rememberuser")
    window.password_edit.setText("Password!23")
    window.remember_me_checkbox.setChecked(True)
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert window.result() == QDialog.DialogCode.Accepted
    assert fake_login_vault.passwords.get("rememberuser") == "Password!23"
    assert (initialized_db.data_dir / "remembered_login.json").exists()

    # Prochaine ouverture (même poste) : identifiant ET mot de passe
    # préremplis, jamais besoin de ressaisir.
    window2, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window2)
    assert window2.username_edit.text() == "rememberuser"
    assert window2.password_edit.text() == "Password!23"
    assert window2.remember_me_checkbox.isChecked() is True


def test_remember_me_unchecked_never_saves_anything(
    qtbot, make_user, initialized_db, fake_login_vault
) -> None:
    make_user("Vendeur", "nosaveuser", "Password!23")
    window, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("nosaveuser")
    window.password_edit.setText("Password!23")
    window.remember_me_checkbox.setChecked(False)
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert window.result() == QDialog.DialogCode.Accepted
    assert "nosaveuser" not in fake_login_vault.passwords
    assert not (initialized_db.data_dir / "remembered_login.json").exists()


def test_disabling_remember_me_clears_previously_saved_credentials(
    qtbot, make_user, initialized_db, fake_login_vault
) -> None:
    make_user("Vendeur", "togglinguser", "Password!23")

    window1, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window1)
    window1.username_edit.setText("togglinguser")
    window1.password_edit.setText("Password!23")
    window1.remember_me_checkbox.setChecked(True)
    qtbot.mouseClick(window1.login_button, Qt.MouseButton.LeftButton)
    assert fake_login_vault.passwords.get("togglinguser") == "Password!23"

    window2, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window2)
    window2.remember_me_checkbox.setChecked(False)
    qtbot.mouseClick(window2.login_button, Qt.MouseButton.LeftButton)

    assert "togglinguser" not in fake_login_vault.passwords
    assert not (initialized_db.data_dir / "remembered_login.json").exists()


def test_forget_remembered_button_clears_credentials_without_logging_in(
    qtbot, make_user, initialized_db, fake_login_vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user("Vendeur", "forgetuser", "Password!23")
    monkeypatch.setattr("app.views.login_window.confirm_action", lambda *a, **k: True)

    window1, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window1)
    window1.username_edit.setText("forgetuser")
    window1.password_edit.setText("Password!23")
    window1.remember_me_checkbox.setChecked(True)
    qtbot.mouseClick(window1.login_button, Qt.MouseButton.LeftButton)
    assert fake_login_vault.passwords.get("forgetuser") == "Password!23"

    window2, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window2)
    assert window2.forget_remembered_button.isEnabled() is True

    qtbot.mouseClick(window2.forget_remembered_button, Qt.MouseButton.LeftButton)

    assert "forgetuser" not in fake_login_vault.passwords
    assert window2.remember_me_checkbox.isChecked() is False
    assert window2.forget_remembered_button.isEnabled() is False
    assert window2.result() != QDialog.DialogCode.Accepted  # jamais une connexion déclenchée.


def test_forget_remembered_button_disabled_when_nothing_is_remembered(
    qtbot, initialized_db, fake_login_vault
) -> None:
    window, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window)
    assert window.forget_remembered_button.isEnabled() is False


def test_vault_unavailable_does_not_block_an_already_successful_login(
    qtbot, make_user, initialized_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hors Windows (ce sandbox), le coffre dédié est réellement
    indisponible (``get_login_credential_vault`` lève, par construction,
    sans substitut ici) — la connexion, déjà réussie, ne doit jamais être
    bloquée par cet échec de mémorisation."""
    make_user("Vendeur", "novaultuser", "Password!23")
    window, auth_service = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("novaultuser")
    window.password_edit.setText("Password!23")
    window.remember_me_checkbox.setChecked(True)

    monkeypatch.setattr("app.views.login_window.QMessageBox.warning", lambda *a, **k: None)
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert window.result() == QDialog.DialogCode.Accepted
    assert auth_service.is_authenticated is True


def test_remembered_login_vault_unavailable_error_message_is_shown(
    qtbot, make_user, initialized_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def _capture_warning(_parent, title, message) -> None:
        captured["title"] = title
        captured["message"] = message

    make_user("Vendeur", "warnuser", "Password!23")
    window, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window)
    window.username_edit.setText("warnuser")
    window.password_edit.setText("Password!23")
    window.remember_me_checkbox.setChecked(True)

    monkeypatch.setattr("app.views.login_window.QMessageBox.warning", _capture_warning)
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    assert "Mémorisation impossible" in captured.get("title", "")
    assert "Password!23" not in captured.get("message", "")


def test_no_plaintext_password_ever_written_to_the_remembered_login_file(
    qtbot, make_user, initialized_db, fake_login_vault
) -> None:
    make_user("Vendeur", "plaintextcheckuser", "Password!23")
    window, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window)

    window.username_edit.setText("plaintextcheckuser")
    window.password_edit.setText("Password!23")
    window.remember_me_checkbox.setChecked(True)
    qtbot.mouseClick(window.login_button, Qt.MouseButton.LeftButton)

    remembered_file = initialized_db.data_dir / "remembered_login.json"
    assert remembered_file.exists()
    assert "Password!23" not in remembered_file.read_text(encoding="utf-8")


def test_user_b_remembering_login_removes_user_a_orphaned_vault_entry(
    qtbot, make_user, initialized_db, fake_login_vault
) -> None:
    """Correctif revue finale (Point 1) — reproduction explicite du
    scénario signalé : l'utilisateur A active « Se souvenir de moi » et se
    connecte (son mot de passe est conservé dans le coffre) ; puis
    l'utilisateur B fait de même sur ce même poste, SANS cliquer
    « Oublier » au préalable. Le mot de passe de A ne doit plus être
    présent dans le coffre une fois B mémorisé — sinon il y resterait
    indéfiniment, orphelin (plus jamais référencé par
    ``remembered_login.json``, donc plus jamais retrouvable ni effaçable
    depuis l'IHM)."""
    make_user("Vendeur", "userA", "PasswordA!23")
    make_user("Vendeur", "userB", "PasswordB!45")

    window_a, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window_a)
    window_a.username_edit.setText("userA")
    window_a.password_edit.setText("PasswordA!23")
    window_a.remember_me_checkbox.setChecked(True)
    qtbot.mouseClick(window_a.login_button, Qt.MouseButton.LeftButton)
    assert fake_login_vault.passwords.get("userA") == "PasswordA!23"

    window_b, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window_b)
    window_b.username_edit.setText("userB")
    window_b.password_edit.setText("PasswordB!45")
    window_b.remember_me_checkbox.setChecked(True)
    qtbot.mouseClick(window_b.login_button, Qt.MouseButton.LeftButton)

    assert "userA" not in fake_login_vault.passwords, "le mot de passe de A est resté orphelin dans le coffre."
    assert fake_login_vault.passwords.get("userB") == "PasswordB!45"
    assert get_remembered_username(initialized_db.data_dir) == "userB"

    # Troisième fenêtre de connexion sur ce poste : seul B est désormais
    # proposé, jamais A (déjà remplacé), et le mot de passe de B reste
    # correctement préempli.
    window_c, _ = _build_login_window(initialized_db)
    qtbot.addWidget(window_c)
    assert window_c.username_edit.text() == "userB"
    assert window_c.password_edit.text() == "PasswordB!45"
