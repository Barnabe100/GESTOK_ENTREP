"""Vérifie app.views.key_password_dialog — mission corrective « Correction
et validation du module de sauvegarde sous Windows », §3.4/§6.2."""
from PySide6.QtWidgets import QLineEdit

from app.views.key_password_dialog import MODE_EXPORT, MODE_IMPORT, KeyPasswordDialog


def test_import_mode_has_no_confirmation_field(qtbot) -> None:
    dialog = KeyPasswordDialog(MODE_IMPORT)
    qtbot.addWidget(dialog)

    assert dialog.confirm_edit is None


def test_export_mode_has_a_confirmation_field(qtbot) -> None:
    dialog = KeyPasswordDialog(MODE_EXPORT)
    qtbot.addWidget(dialog)

    assert dialog.confirm_edit is not None


def test_password_is_masked_by_default(qtbot) -> None:
    dialog = KeyPasswordDialog(MODE_EXPORT)
    qtbot.addWidget(dialog)

    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.confirm_edit.echoMode() == QLineEdit.EchoMode.Password


def test_show_password_checkbox_reveals_both_fields(qtbot) -> None:
    dialog = KeyPasswordDialog(MODE_EXPORT)
    qtbot.addWidget(dialog)

    dialog.show_password_checkbox.setChecked(True)

    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Normal
    assert dialog.confirm_edit.echoMode() == QLineEdit.EchoMode.Normal

    dialog.show_password_checkbox.setChecked(False)

    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.confirm_edit.echoMode() == QLineEdit.EchoMode.Password


def test_show_password_checkbox_works_for_import_mode_too(qtbot) -> None:
    dialog = KeyPasswordDialog(MODE_IMPORT)
    qtbot.addWidget(dialog)

    dialog.show_password_checkbox.setChecked(True)

    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Normal


def test_export_rejects_empty_password(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = KeyPasswordDialog(MODE_EXPORT)
    qtbot.addWidget(dialog)

    dialog._on_ok_clicked()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "obligatoire" in dialog.error_label.text()


def test_export_rejects_a_password_shorter_than_the_minimum(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = KeyPasswordDialog(MODE_EXPORT)
    qtbot.addWidget(dialog)
    dialog.password_edit.setText("court")
    dialog.confirm_edit.setText("court")

    dialog._on_ok_clicked()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "8 caractères" in dialog.error_label.text()


def test_export_rejects_mismatched_confirmation(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = KeyPasswordDialog(MODE_EXPORT)
    qtbot.addWidget(dialog)
    dialog.password_edit.setText("mot-de-passe-solide")
    dialog.confirm_edit.setText("different-mot-de-passe")

    dialog._on_ok_clicked()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "ne correspondent pas" in dialog.error_label.text()


def test_export_accepts_a_matching_strong_password(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = KeyPasswordDialog(MODE_EXPORT)
    qtbot.addWidget(dialog)
    dialog.password_edit.setText("mot-de-passe-solide")
    dialog.confirm_edit.setText("mot-de-passe-solide")

    dialog._on_ok_clicked()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.password() == "mot-de-passe-solide"


def test_import_accepts_any_non_empty_password_without_a_minimum_length(qtbot) -> None:
    """L'import ne doit jamais imposer une nouvelle exigence de
    robustesse : le mot de passe doit simplement correspondre à celui
    déjà choisi lors de l'export, quelle que soit sa longueur."""
    from PySide6.QtWidgets import QDialog

    dialog = KeyPasswordDialog(MODE_IMPORT)
    qtbot.addWidget(dialog)
    dialog.password_edit.setText("court")

    dialog._on_ok_clicked()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.password() == "court"


def test_import_rejects_empty_password(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = KeyPasswordDialog(MODE_IMPORT)
    qtbot.addWidget(dialog)

    dialog._on_ok_clicked()

    assert dialog.result() != QDialog.DialogCode.Accepted


def test_invalid_mode_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        KeyPasswordDialog("mode-invalide")
