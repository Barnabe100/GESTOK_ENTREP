"""Dialogue de création d'utilisateur — pure collecte de saisie, aucune
logique métier (voir app/views/create_user_dialog.py)."""
from PySide6.QtWidgets import QDialog

from app.views.create_user_dialog import CreateUserDialog
from tests.ui_test_helpers import assert_field_is_marked_required, assert_has_required_field_legend

_ROLES = [(1, "Administrateur"), (2, "Gestionnaire de stock"), (3, "Vendeur"), (4, "Consultation")]


def test_all_fields_are_marked_required(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    for field in (
        dialog.username_edit, dialog.password_edit, dialog.confirm_password_edit, dialog.role_combo,
    ):
        assert_field_is_marked_required(dialog, field)


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_role_combo_populated_from_given_roles(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    assert dialog.role_combo.count() == len(_ROLES)
    assert dialog.role_id() == _ROLES[0][0]


def test_initial_username_prefills_field(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES, initial_username="deja_saisi")
    qtbot.addWidget(dialog)

    assert dialog.username() == "deja_saisi"


def test_active_checkbox_defaults_to_checked(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    assert dialog.is_active() is True


def test_mismatched_passwords_show_error_and_do_not_accept(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    dialog.username_edit.setText("un_utilisateur")
    dialog.password_edit.setText("MotDePasse1")
    dialog.confirm_password_edit.setText("Different1")

    dialog.save_button.click()

    assert dialog.error_label.text() != ""
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_matching_passwords_accept_dialog(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    dialog.username_edit.setText("un_utilisateur")
    dialog.password_edit.setText("MotDePasse1")
    dialog.confirm_password_edit.setText("MotDePasse1")

    dialog.save_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.username() == "un_utilisateur"
    assert dialog.password() == "MotDePasse1"


def test_selected_role_id_reflects_combo_choice(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    dialog.role_combo.setCurrentIndex(2)

    assert dialog.role_id() == _ROLES[2][0]


def test_active_checkbox_can_be_unchecked(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    dialog.active_checkbox.setChecked(False)

    assert dialog.is_active() is False
