import pytest
from PySide6.QtWidgets import QMessageBox

from app.views.pages.backups_page import BackupsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.backups_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.backups_page.QMessageBox.warning", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.backups_page.QMessageBox.critical", lambda *a, **k: None)


def _build_page(stack) -> BackupsPage:
    return BackupsPage(stack.backups, stack.permissions)


def test_form_prefilled_with_current_config(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=True, frequency="weekly", time_of_day="03:15", destination=str(destination), retention=7)

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.auto_enabled_checkbox.isChecked() is True
    assert page.frequency_combo.currentText() == "Hebdomadaire"
    assert page.time_edit.text() == "03:15"
    assert page.destination_edit.text() == str(destination)
    assert page.retention_spin.value() == 7


def test_save_config_persists_form_values(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    destination = tmp_path / "backups"
    page.auto_enabled_checkbox.setChecked(True)
    page.frequency_combo.setCurrentText("Hebdomadaire")
    page.time_edit.setText("04:00")
    page.destination_edit.setText(str(destination))
    page.retention_spin.setValue(3)

    result = page._save_config()

    assert result is True
    config = stack.backups.get_config()
    assert config.auto_enabled is True
    assert config.frequency == "weekly"
    assert config.time_of_day == "04:00"
    assert config.retention == 3


def test_save_config_shows_error_on_invalid_time(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.destination_edit.setText(str(tmp_path / "backups"))
    page.time_edit.setText("pas une heure")

    result = page._save_config()

    assert result is False


def test_config_fields_disabled_without_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.save_config_button.isEnabled() is False
    assert page.destination_edit.isEnabled() is False
    assert page.backup_now_button.isEnabled() is False


def test_backup_now_creates_backup_and_refreshes_history(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._run_manual_backup()
    page.refresh_history()

    assert result is True
    assert page.history_table.rowCount() == 1
    assert page.history_table.item(0, 3).text() == "Valide"


def test_history_shows_name_and_size(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    backup_result = stack.backups.create_manual_backup()

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.history_table.rowCount() == 1
    assert page.history_table.item(0, 1).text() == backup_result.file_path.name
    assert page.history_table.item(0, 2).text() != ""


def test_restore_button_disabled_until_row_selected(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    stack.backups.create_manual_backup()

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.restore_button.isEnabled() is False

    page.history_table.selectRow(0)

    assert page.restore_button.isEnabled() is True


def test_restore_button_disabled_without_permission(qtbot, login_as, tmp_path) -> None:
    admin_stack, _ = login_as("Administrateur")
    admin_stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    admin_stack.backups.create_manual_backup()

    stack, _ = login_as("Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    # Consultation n'a pas BACKUP_VIEW : l'historique reste vide (AppError
    # capturée par refresh_history), et le bouton Restaurer désactivé de toute façon.
    assert page.history_table.rowCount() == 0
    assert page.restore_button.isEnabled() is False


def test_restore_selected_restores_and_shows_success(qtbot, login_as, tmp_path) -> None:
    from decimal import Decimal

    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "carton", Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("10")
    )
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    backup_result = stack.backups.create_manual_backup()

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._restore_selected(str(backup_result.file_path))

    assert result is True


def test_restore_selected_shows_error_on_invalid_backup(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    fake = tmp_path / "fake.db"
    fake.write_bytes(b"pas sqlite")

    result = page._restore_selected(str(fake))

    assert result is False


def test_confirmation_dialog_no_cancels_restore(qtbot, login_as, tmp_path, monkeypatch) -> None:
    from decimal import Decimal

    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "carton", Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("10")
    )
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    stack.backups.create_manual_backup()

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.history_table.selectRow(0)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    page._on_restore_clicked()

    # L'article créé après la sauvegarde initiale doit toujours exister
    # (aucune restauration n'a eu lieu, l'utilisateur a annulé).
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")
