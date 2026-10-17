from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QWidget

from app.views.password_line_edit import PasswordLineEdit


def test_default_echo_mode_is_password(qtbot) -> None:
    edit = PasswordLineEdit()
    qtbot.addWidget(edit)

    assert edit.echoMode() == QLineEdit.EchoMode.Password
    assert edit.is_password_visible() is False


def test_toggle_button_shows_password(qtbot) -> None:
    edit = PasswordLineEdit()
    qtbot.addWidget(edit)
    edit.setText("secret")

    qtbot.mouseClick(edit._toggle_button, Qt.MouseButton.LeftButton)

    assert edit.echoMode() == QLineEdit.EchoMode.Normal
    assert edit.is_password_visible() is True
    assert edit.text() == "secret"


def test_toggle_button_hides_password_again(qtbot) -> None:
    edit = PasswordLineEdit()
    qtbot.addWidget(edit)

    qtbot.mouseClick(edit._toggle_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(edit._toggle_button, Qt.MouseButton.LeftButton)

    assert edit.echoMode() == QLineEdit.EchoMode.Password
    assert edit.is_password_visible() is False


def test_hide_event_remasks_password(qtbot) -> None:
    """Fermer/masquer le widget remasque automatiquement, même si
    l'utilisateur avait cliqué sur « afficher » juste avant."""
    edit = PasswordLineEdit()
    qtbot.addWidget(edit)
    edit.show()
    qtbot.mouseClick(edit._toggle_button, Qt.MouseButton.LeftButton)
    assert edit.is_password_visible() is True

    edit.hide()

    assert edit.echoMode() == QLineEdit.EchoMode.Password
    assert edit.is_password_visible() is False


def test_focus_change_does_not_remask(qtbot) -> None:
    """Un simple changement de focus ne doit jamais remasquer le mot de
    passe — seule la fermeture/masquage du widget le fait."""
    container = QWidget()
    edit = PasswordLineEdit(container)
    other_field = QLineEdit(container)
    qtbot.addWidget(container)
    container.show()

    qtbot.mouseClick(edit._toggle_button, Qt.MouseButton.LeftButton)
    assert edit.is_password_visible() is True

    other_field.setFocus()

    assert edit.echoMode() == QLineEdit.EchoMode.Normal
    assert edit.is_password_visible() is True


def test_parent_dialog_closing_remasks_password(qtbot) -> None:
    """Le masquage automatique se propage bien depuis la fermeture du
    dialogue parent (cas réel d'usage), pas seulement un hide() direct."""
    from PySide6.QtWidgets import QDialog

    dialog = QDialog()
    edit = PasswordLineEdit(dialog)
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.mouseClick(edit._toggle_button, Qt.MouseButton.LeftButton)
    assert edit.is_password_visible() is True

    dialog.hide()

    assert edit.is_password_visible() is False
    assert edit.echoMode() == QLineEdit.EchoMode.Password
