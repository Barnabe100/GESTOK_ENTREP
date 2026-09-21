"""Dialogue de création d'utilisateur — pure collecte de saisie, aucune
logique métier (voir app/views/create_user_dialog.py).

Un utilisateur peut avoir plusieurs rôles (lot multi-rôles) : le dialogue
propose une case à cocher par rôle plutôt qu'un ``QComboBox`` à sélection
unique — voir ``dialog.role_ids()``."""
from PySide6.QtWidgets import QDialog, QGroupBox

from app.views.create_user_dialog import CreateUserDialog
from tests.ui_test_helpers import assert_has_required_field_legend

_ROLES = [(1, "Administrateur"), (2, "Gestionnaire de stock"), (3, "Vendeur"), (4, "Consultation")]


def _roles_group(dialog: CreateUserDialog) -> QGroupBox:
    return dialog.findChild(QGroupBox)


def test_roles_group_is_marked_required(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    assert _roles_group(dialog).title().rstrip().endswith("*")


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_role_checkboxes_populated_from_given_roles(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    assert len(dialog._role_checkboxes) == len(_ROLES)
    assert dialog.role_ids() == []  # aucune case cochée par défaut


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


def test_matching_passwords_but_no_role_selected_do_not_accept(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    dialog.username_edit.setText("un_utilisateur")
    dialog.password_edit.setText("MotDePasse1")
    dialog.confirm_password_edit.setText("MotDePasse1")

    dialog.save_button.click()

    assert dialog.error_label.text() != ""
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_matching_passwords_and_role_selected_accept_dialog(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    dialog.username_edit.setText("un_utilisateur")
    dialog.password_edit.setText("MotDePasse1")
    dialog.confirm_password_edit.setText("MotDePasse1")
    _, first_checkbox = dialog._role_checkboxes[0]
    first_checkbox.setChecked(True)

    dialog.save_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.username() == "un_utilisateur"
    assert dialog.password() == "MotDePasse1"


def test_role_ids_reflects_single_checkbox_selection(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    _, checkbox = dialog._role_checkboxes[2]
    checkbox.setChecked(True)

    assert dialog.role_ids() == [_ROLES[2][0]]


def test_role_ids_reflects_multiple_checkbox_selection(qtbot) -> None:
    """Un utilisateur peut se voir attribuer plusieurs rôles simultanément
    (ex. Vendeur + Gestionnaire de stock) : toutes les cases cochées sont
    retournées, dans l'ordre de présentation."""
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    _, checkbox_gestionnaire = dialog._role_checkboxes[1]
    _, checkbox_vendeur = dialog._role_checkboxes[2]
    checkbox_gestionnaire.setChecked(True)
    checkbox_vendeur.setChecked(True)

    assert dialog.role_ids() == [_ROLES[1][0], _ROLES[2][0]]


def test_active_checkbox_can_be_unchecked(qtbot) -> None:
    dialog = CreateUserDialog(_ROLES)
    qtbot.addWidget(dialog)

    dialog.active_checkbox.setChecked(False)

    assert dialog.is_active() is False
