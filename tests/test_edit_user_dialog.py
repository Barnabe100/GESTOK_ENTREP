"""Dialogue de modification du rôle — pure collecte de saisie, aucune
logique métier (voir app/views/edit_user_dialog.py)."""
from PySide6.QtWidgets import QDialog

from app.views.edit_user_dialog import EditUserDialog

_ROLES = [(1, "Administrateur"), (2, "Gestionnaire de stock"), (3, "Vendeur"), (4, "Consultation")]


def test_role_combo_preselects_current_role(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, current_role_id=3)
    qtbot.addWidget(dialog)

    assert dialog.role_id() == 3


def test_role_combo_populated_from_given_roles(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, current_role_id=1)
    qtbot.addWidget(dialog)

    assert dialog.role_combo.count() == len(_ROLES)


def test_changing_selection_updates_role_id(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, current_role_id=1)
    qtbot.addWidget(dialog)

    dialog.role_combo.setCurrentIndex(2)

    assert dialog.role_id() == _ROLES[2][0]


def test_save_button_accepts_dialog(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, current_role_id=1)
    qtbot.addWidget(dialog)

    dialog.save_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_cancel_button_rejects_dialog(qtbot) -> None:
    dialog = EditUserDialog(_ROLES, current_role_id=1)
    qtbot.addWidget(dialog)

    dialog.cancel_button.click()

    assert dialog.result() == QDialog.DialogCode.Rejected
