"""Dialogue de modification des rôles — pure collecte de saisie, aucune
logique métier (voir app/views/edit_user_dialog.py).

Un utilisateur peut avoir plusieurs rôles (lot multi-rôles) : le dialogue
propose une case à cocher par rôle, pré-cochée selon les rôles actuels —
voir ``dialog.role_ids()``."""
from PySide6.QtWidgets import QDialog, QGroupBox

from app.views.edit_user_dialog import EditUserDialog
from tests.ui_test_helpers import assert_has_required_field_legend

_ROLES = [(1, "Administrateur"), (2, "Gestionnaire de stock"), (3, "Vendeur"), (4, "Consultation")]


def _roles_group(dialog: EditUserDialog) -> QGroupBox:
    return dialog.findChild(QGroupBox)


def test_roles_group_is_marked_required(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [3])
    qtbot.addWidget(dialog)

    assert _roles_group(dialog).title().rstrip().endswith("*")


def test_dialog_shows_required_field_legend(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [3])
    qtbot.addWidget(dialog)

    assert_has_required_field_legend(dialog)


def test_checkboxes_preselect_current_single_role(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [3])
    qtbot.addWidget(dialog)

    assert dialog.role_ids() == [3]


def test_checkboxes_preselect_current_multiple_roles(qtbot) -> None:
    """Un utilisateur ayant déjà plusieurs rôles (ex. Vendeur + Gestionnaire
    de stock) voit toutes ses cases correspondantes pré-cochées à l'ouverture
    du dialogue de modification."""
    dialog = EditUserDialog(_ROLES, [2, 3])
    qtbot.addWidget(dialog)

    assert dialog.role_ids() == [2, 3]


def test_role_checkboxes_populated_from_given_roles(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [1])
    qtbot.addWidget(dialog)

    assert len(dialog._role_checkboxes) == len(_ROLES)


def test_checking_additional_box_adds_role_id(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [1])
    qtbot.addWidget(dialog)

    _, checkbox = dialog._role_checkboxes[2]
    checkbox.setChecked(True)

    assert dialog.role_ids() == [1, _ROLES[2][0]]


def test_unchecking_only_box_leaves_no_role_selected(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [1])
    qtbot.addWidget(dialog)

    _, checkbox = dialog._role_checkboxes[0]
    checkbox.setChecked(False)

    assert dialog.role_ids() == []


def test_save_button_accepts_dialog_when_at_least_one_role_selected(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [1])
    qtbot.addWidget(dialog)

    dialog.save_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_save_button_rejects_when_no_role_selected(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [1])
    qtbot.addWidget(dialog)
    _, checkbox = dialog._role_checkboxes[0]
    checkbox.setChecked(False)

    dialog.save_button.click()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.text() != ""


def test_cancel_button_rejects_dialog(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, [1])
    qtbot.addWidget(dialog)

    dialog.cancel_button.click()

    assert dialog.result() == QDialog.DialogCode.Rejected
