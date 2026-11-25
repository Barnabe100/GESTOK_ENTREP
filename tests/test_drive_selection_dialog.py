"""Vérifie app.views.drive_selection_dialog — mission corrective
« Correction et validation du module de sauvegarde sous Windows »,
§2.4/§3.1 : remplace le sélecteur de dossier générique par un choix
explicite parmi les lecteurs réellement détectés."""
from pathlib import Path

from app.services.backups.external_media import DriveInfo, ExternalMediaMarker
from app.views.drive_selection_dialog import DriveSelectionDialog


def test_empty_drive_list_shows_a_dedicated_message(qtbot) -> None:
    dialog = DriveSelectionDialog([])
    qtbot.addWidget(dialog)

    assert dialog.empty_label is not None
    assert dialog.list_widget.count() == 0


def test_non_empty_drive_list_shows_no_empty_message(qtbot) -> None:
    drives = [DriveInfo(root=Path("E:/"), drive_type="removable", volume_label="CLE_USB", marker=None)]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)

    assert dialog.empty_label is None
    assert dialog.list_widget.count() == 1


def test_choose_button_disabled_until_a_drive_is_selected(qtbot) -> None:
    drives = [DriveInfo(root=Path("E:/"), drive_type="removable", volume_label="", marker=None)]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)

    assert dialog.choose_button.isEnabled() is False

    dialog.list_widget.setCurrentRow(0)

    assert dialog.choose_button.isEnabled() is True


def test_selected_root_returns_none_without_a_selection(qtbot) -> None:
    drives = [DriveInfo(root=Path("E:/"), drive_type="removable", volume_label="", marker=None)]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)

    assert dialog.selected_root() is None


def test_selected_root_returns_the_chosen_drive(qtbot) -> None:
    drives = [
        DriveInfo(root=Path("D:/"), drive_type="fixed", volume_label="", marker=None),
        DriveInfo(root=Path("E:/"), drive_type="removable", volume_label="CLE_USB", marker=None),
    ]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)

    dialog.list_widget.setCurrentRow(1)

    assert dialog.selected_root() == Path("E:/")


def test_item_text_shows_volume_label_and_type(qtbot) -> None:
    drives = [DriveInfo(root=Path("E:/"), drive_type="removable", volume_label="CLE_USB", marker=None)]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)

    text = dialog.list_widget.item(0).text()

    assert "E:" in text
    assert "CLE_USB" in text
    assert "amovible" in text


def test_item_text_shows_fixed_disk_type_for_an_external_hard_drive(qtbot) -> None:
    """Mission corrective, ajustement #2 : un disque dur externe se
    déclare souvent ``DRIVE_FIXED`` — l'intitulé affiché doit rester
    compréhensible pour ce cas, jamais seulement « amovible »."""
    drives = [DriveInfo(root=Path("D:/"), drive_type="fixed", volume_label="", marker=None)]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)

    text = dialog.list_widget.item(0).text()

    assert "disque fixe" in text


def test_item_text_mentions_an_existing_marker(qtbot) -> None:
    marker = ExternalMediaMarker(marker_id="abc-123", label="Mon disque de sauvegarde", created_at="2026-01-01T00:00:00+00:00")
    drives = [DriveInfo(root=Path("E:/"), drive_type="removable", volume_label="", marker=marker)]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)

    text = dialog.list_widget.item(0).text()

    assert "déjà configuré" in text
    assert "Mon disque de sauvegarde" in text


def test_cancel_button_rejects_the_dialog(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    drives = [DriveInfo(root=Path("E:/"), drive_type="removable", volume_label="", marker=None)]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)

    dialog.cancel_button.click()

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_choose_button_accepts_the_dialog_once_enabled(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    drives = [DriveInfo(root=Path("E:/"), drive_type="removable", volume_label="", marker=None)]
    dialog = DriveSelectionDialog(drives)
    qtbot.addWidget(dialog)
    dialog.list_widget.setCurrentRow(0)

    dialog.choose_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
