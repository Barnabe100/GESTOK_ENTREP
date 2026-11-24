import threading

import pytest
from PySide6.QtWidgets import QMessageBox

from app.utils.exceptions import AppError
from app.views.pages.backups_page import BackupsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.backups_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.backups_page.QMessageBox.warning", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.backups_page.QMessageBox.critical", lambda *a, **k: None)


def _build_page(stack) -> BackupsPage:
    return BackupsPage(stack.backups, stack.permissions, external_backup_service=stack.external_backups)


def test_sqlite_mode_shows_no_postgresql_target_line(qtbot, login_as) -> None:
    """Lot E.7, §E.7.2 : la ligne d'identification de cible (hôte/port/base)
    ne concerne que PostgreSQL — en SQLite, comportement historique
    inchangé, aucune ligne de cible ajoutée."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.active_engine_label.text() == "SQLite"
    assert page.active_target_label.text() == ""


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
    # Lot E : colonne "Moteur" ajoutée en tête (§E.3) -> Statut passe de l'index 3 à 4.
    assert page.history_table.item(0, 5).text() == "Valide"  # Statut (Type/Moteur ajoutés en tête, §3.3)


def test_history_shows_name_and_size(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    backup_result = stack.backups.create_manual_backup()

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.history_table.rowCount() == 1
    # Lot E : colonne "Moteur" ajoutée en tête (§E.3) -> Nom/Taille passent des index 1/2 à 2/3.
    assert page.history_table.item(0, 3).text() == backup_result.file_path.name  # Nom
    assert page.history_table.item(0, 4).text() != ""  # Taille
    assert page.history_table.item(0, 1).text() == "SQLite"  # Moteur


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

    # Extension à tous les menus en lecture seule : Consultation a
    # désormais BACKUP_VIEW, l'historique est donc visible — mais jamais
    # BACKUP_RESTORE, le bouton Restaurer reste désactivé même une ligne
    # sélectionnée.
    assert page.history_table.rowCount() == 1
    page.history_table.selectRow(0)
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


# -- réinitialisation des données métier (§3 du lot) ----------------------------------


def _build_page_with_reset(stack) -> BackupsPage:
    return BackupsPage(stack.backups, stack.permissions, stack.data_reset)


def test_reset_button_disabled_without_data_reset_service(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)  # sans data_reset_service (signature historique)
    qtbot.addWidget(page)

    assert page.reset_business_data_button.isEnabled() is False


def test_reset_button_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page_with_reset(stack)
    qtbot.addWidget(page)

    assert page.reset_business_data_button.isEnabled() is True


def test_reset_button_disabled_for_non_administrateur_roles(qtbot, login_as) -> None:
    for role_name in ("Gestionnaire de stock", "Vendeur", "Consultation"):
        stack, _ = login_as(role_name)
        page = _build_page_with_reset(stack)
        qtbot.addWidget(page)
        assert page.reset_business_data_button.isEnabled() is False


def test_run_reset_business_data_succeeds_and_refreshes_history(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page_with_reset(stack)
    qtbot.addWidget(page)

    result = page._run_reset_business_data()

    assert result is True


def test_run_reset_business_data_shows_error_on_backup_failure(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page_with_reset(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.services.backups.backup_engine.create_backup_file",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disque plein (simulé)")),
    )

    result = page._run_reset_business_data()

    assert result is False


# -- indicateur de chargement (phase amélioration UX, point 4) --------------------
#
# Correctif revue finale (Point 3) : ``_on_backup_now_clicked``/``_on_restore_clicked``
# exécutent désormais l'appel au service dans un thread d'arrière-plan (voir
# ``BackgroundTask``) — l'affichage du voile et la désactivation du bouton
# restent synchrones (vérifiables immédiatement après l'appel), mais la
# disparition du voile et le résultat n'arrivent qu'après la fin du thread,
# d'où l'usage de ``qtbot.waitUntil`` ci-dessous plutôt qu'une assertion
# immédiate.


def test_backup_now_shows_overlay_immediately_then_hides_it_after_completion(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    page = _build_page(stack)
    qtbot.addWidget(page)

    calls = []
    page._loading_overlay.show_with_message = lambda message: calls.append(("show", message))
    page._loading_overlay.hide_overlay = lambda: calls.append(("hide",))

    page._on_backup_now_clicked()

    # Le voile et la désactivation du bouton sont immédiats, avant même que
    # le thread d'arrière-plan ait eu l'occasion de s'exécuter.
    assert calls == [("show", "Sauvegarde en cours…")]
    assert page.backup_now_button.isEnabled() is False

    qtbot.waitUntil(lambda: ("hide",) in calls, timeout=5000)

    assert calls == [("show", "Sauvegarde en cours…"), ("hide",)]
    assert page.backup_now_button.isEnabled() is True
    assert page.history_table.rowCount() == 1


def test_backup_now_overlay_is_hidden_and_button_reenabled_even_on_failure(qtbot, login_as, monkeypatch) -> None:
    """Le voile ne doit jamais masquer un échec, même levé depuis le thread
    d'arrière-plan : il disparaît et le bouton redevient utilisable."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(stack.backups, "create_manual_backup", lambda: (_ for _ in ()).throw(AppError("échec simulé")))

    calls = []
    page._loading_overlay.show_with_message = lambda message: calls.append(("show", message))
    page._loading_overlay.hide_overlay = lambda: calls.append(("hide",))

    page._on_backup_now_clicked()
    qtbot.waitUntil(lambda: ("hide",) in calls, timeout=5000)

    assert calls == [("show", "Sauvegarde en cours…"), ("hide",)]
    assert page.backup_now_button.isEnabled() is True


def test_backup_now_overlay_is_hidden_on_unexpected_non_app_error(qtbot, login_as, monkeypatch) -> None:
    """Une exception inattendue (pas une ``AppError``) levée dans le thread
    d'arrière-plan doit, elle aussi, toujours refermer le voile et
    réactiver le bouton — jamais un voile bloqué indéfiniment."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(stack.backups, "create_manual_backup", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    calls = []
    page._loading_overlay.show_with_message = lambda message: calls.append(("show", message))
    page._loading_overlay.hide_overlay = lambda: calls.append(("hide",))

    page._on_backup_now_clicked()
    qtbot.waitUntil(lambda: ("hide",) in calls, timeout=5000)

    assert calls == [("show", "Sauvegarde en cours…"), ("hide",)]
    assert page.backup_now_button.isEnabled() is True


def test_backup_now_second_click_while_in_progress_is_ignored(qtbot, login_as, tmp_path, monkeypatch) -> None:
    """Empêche un double lancement : un second clic pendant qu'une
    sauvegarde est déjà en cours dans le thread d'arrière-plan ne doit
    jamais démarrer une seconde opération."""
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    page = _build_page(stack)
    qtbot.addWidget(page)

    calls = []
    page._loading_overlay.show_with_message = lambda message: calls.append(("show", message))
    page._loading_overlay.hide_overlay = lambda: calls.append(("hide",))

    release = threading.Event()
    call_count = {"n": 0}
    original_create_backup = stack.backups.create_manual_backup

    def _slow_backup():
        call_count["n"] += 1
        release.wait(timeout=5)
        return original_create_backup()

    monkeypatch.setattr(stack.backups, "create_manual_backup", _slow_backup)

    page._on_backup_now_clicked()
    assert page.backup_now_button.isEnabled() is False

    page._on_backup_now_clicked()  # second clic pendant l'opération en cours : doit être un no-op.

    release.set()
    qtbot.waitUntil(lambda: ("hide",) in calls, timeout=5000)

    assert call_count["n"] == 1
    assert page.backup_now_button.isEnabled() is True


def test_restore_shows_overlay_immediately_then_hides_it_after_completion(qtbot, login_as, tmp_path, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    stack.backups.create_manual_backup()

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.history_table.selectRow(0)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    calls = []
    page._loading_overlay.show_with_message = lambda message: calls.append(("show", message))
    page._loading_overlay.hide_overlay = lambda: calls.append(("hide",))

    page._on_restore_clicked()

    assert calls == [("show", "Restauration en cours…")]
    assert page.restore_button.isEnabled() is False

    qtbot.waitUntil(lambda: ("hide",) in calls, timeout=5000)

    assert calls == [("show", "Restauration en cours…"), ("hide",)]
    assert page.restore_button.isEnabled() is True


def test_restore_second_click_while_in_progress_is_ignored(qtbot, login_as, tmp_path, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    stack.backups.create_manual_backup()

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.history_table.selectRow(0)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    calls = []
    page._loading_overlay.show_with_message = lambda message: calls.append(("show", message))
    page._loading_overlay.hide_overlay = lambda: calls.append(("hide",))

    release = threading.Event()
    call_count = {"n": 0}
    original_restore = stack.backups.restore_backup

    def _slow_restore(path):
        call_count["n"] += 1
        release.wait(timeout=5)
        return original_restore(path)

    monkeypatch.setattr(stack.backups, "restore_backup", _slow_restore)

    page._on_restore_clicked()
    assert page.restore_button.isEnabled() is False

    page._on_restore_clicked()  # second clic pendant l'opération en cours : doit être un no-op.

    release.set()
    qtbot.waitUntil(lambda: ("hide",) in calls, timeout=5000)

    assert call_count["n"] == 1


# -- Mission « Sauvegarde automatique et restauration » : protection externe -----


def test_external_group_shows_unavailable_when_service_absent(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = BackupsPage(stack.backups, stack.permissions)  # pas de external_backup_service
    qtbot.addWidget(page)

    assert page.external_status_label.text() == "Protection externe non disponible."
    assert page.choose_media_button.isEnabled() is False
    assert page.copy_now_button.isEnabled() is False


def test_external_group_shows_safe_defaults(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page.show()

    assert page.external_enabled_checkbox.isChecked() is False
    assert page.external_media_label.text() == "Aucun support configuré."
    assert page.external_reminder_label.isVisible() is True


def test_configure_media_updates_form_and_hides_reminder(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    drive = tmp_path / "usb"
    drive.mkdir()

    result = page._configure_media(str(drive), "Clé USB de test")

    assert result is True
    assert page.external_media_label.text() == "« Clé USB de test »"


def test_save_external_config_rejects_enabling_without_media(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page.external_enabled_checkbox.setChecked(True)

    result = page._save_external_config()

    assert result is False


def test_save_external_config_succeeds_after_media_configured(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    drive = tmp_path / "usb"
    drive.mkdir()
    page._configure_media(str(drive), "Support")
    page.external_enabled_checkbox.setChecked(True)
    page.external_retention_spin.setValue(40)

    result = page._save_external_config()

    assert result is True
    assert stack.external_backups.get_config().enabled is True
    assert stack.external_backups.get_config().retention == 40


def test_test_media_accessible_reports_true_when_configured_and_present(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    drive = tmp_path / "usb"
    drive.mkdir()
    page._configure_media(str(drive), "Support")
    stack.external_backups._media_roots_provider = lambda: [drive]

    assert page._test_media_accessible() is True


def test_test_media_accessible_reports_false_when_not_configured(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._test_media_accessible() is False


def test_run_external_copy_now_succeeds_and_refreshes(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(tmp_path / "backups"), retention=30,
    )
    stack.backups.create_manual_backup()
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._run_external_copy_now()

    assert result is True
    assert any(source == "Externe" for source, _entry in page._history_entries)


def test_configure_and_remove_scheduled_task_translate_unsupported_platform(qtbot, login_as) -> None:
    """Hors Windows (ce sandbox), ces opérations échouent explicitement —
    l'écran doit afficher un message, jamais lever une exception non
    gérée (voir ExternalBackupService, qui traduit en ValidationError)."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._configure_scheduled_task() is False
    assert page._remove_scheduled_task() is False


# -- historique combiné (Type locale/externe, Emplacement) -----------------------


def test_history_combines_local_and_external_entries(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(tmp_path / "backups"), retention=30,
    )
    stack.backups.create_manual_backup()
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    stack.external_backups.copy_now()

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.history_table.rowCount() == 2
    types = {page.history_table.item(row, 0).text() for row in range(page.history_table.rowCount())}
    assert types == {"Locale", "Externe"}


def test_history_shows_location_column(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    stack.backups.create_manual_backup()

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.history_table.item(0, 6).text() == str(destination)


# -- consulter les détails / exporter --------------------------------------------


def test_history_action_buttons_disabled_without_selection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.view_details_button.isEnabled() is False
    assert page.export_button.isEnabled() is False


def test_history_action_buttons_enabled_with_selection(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    stack.backups.create_manual_backup()
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.history_table.selectRow(0)

    assert page.view_details_button.isEnabled() is True
    assert page.export_button.isEnabled() is True


def test_view_details_opens_backup_details_dialog(qtbot, login_as, tmp_path, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"), retention=10)
    stack.backups.create_manual_backup()
    page = _build_page(stack)
    qtbot.addWidget(page)
    page.history_table.selectRow(0)

    captured = {}

    def _fake_dialog(*args, **kwargs):
        captured["called"] = True
        return type("_FakeDialog", (), {"exec": lambda self: None})()

    monkeypatch.setattr("app.views.pages.backups_page.BackupDetailsDialog", _fake_dialog)

    page._on_view_details_clicked()

    assert captured.get("called") is True


def test_export_entry_copies_archive_and_manifest(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    backup_result = stack.backups.create_manual_backup()
    page = _build_page(stack)
    qtbot.addWidget(page)

    export_target = tmp_path / "export" / "copie.db"
    export_target.parent.mkdir()
    entry = next(entry for source, entry in page._history_entries if source == "Locale")

    result = page._export_entry_to(entry, str(export_target))

    assert result is True
    assert export_target.read_bytes() == backup_result.file_path.read_bytes()
    from app.services.backups import archive_manifest

    assert archive_manifest.manifest_path_for(export_target).is_file()


def test_export_entry_reports_failure_on_os_error(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    stack.backups.create_manual_backup()
    page = _build_page(stack)
    qtbot.addWidget(page)

    entry = next(entry for source, entry in page._history_entries if source == "Locale")

    result = page._export_entry_to(entry, "/chemin/inexistant/copie.db")

    assert result is False


def test_restore_wizard_button_enabled_with_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.restore_wizard_button.isEnabled() is True


def test_restore_wizard_button_disabled_without_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.restore_wizard_button.isEnabled() is False


def test_open_restore_wizard_refreshes_history_on_accept(qtbot, login_as, monkeypatch) -> None:
    from PySide6.QtWidgets import QDialog

    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    captured = {}
    refresh_calls = []
    monkeypatch.setattr(page, "refresh_history", lambda: refresh_calls.append(True))

    def _fake_wizard(*args, **kwargs):
        captured["args"] = args
        return type(
            "_FakeWizard", (),
            {
                "exec": lambda self: None,
                "result": lambda self: QDialog.DialogCode.Accepted,
                "has_active_background_task": lambda self: False,
            },
        )()

    monkeypatch.setattr("app.views.pages.backups_page.BackupRestoreWizardDialog", _fake_wizard)

    page._on_open_restore_wizard_clicked()

    assert captured.get("args") is not None
    assert refresh_calls == [True]
    assert page._restore_wizard_dialog is None


def test_open_restore_wizard_does_not_refresh_on_reject(qtbot, login_as, monkeypatch) -> None:
    from PySide6.QtWidgets import QDialog

    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    refresh_calls = []
    monkeypatch.setattr(page, "refresh_history", lambda: refresh_calls.append(True))

    def _fake_wizard(*args, **kwargs):
        return type(
            "_FakeWizard", (),
            {
                "exec": lambda self: None,
                "result": lambda self: QDialog.DialogCode.Rejected,
                "has_active_background_task": lambda self: False,
            },
        )()

    monkeypatch.setattr("app.views.pages.backups_page.BackupRestoreWizardDialog", _fake_wizard)

    page._on_open_restore_wizard_clicked()

    assert refresh_calls == []


def test_has_active_background_task_delegates_to_open_wizard(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    class _BusyWizard:
        def exec(self):
            # Simule une restauration encore en cours au moment de l'appel.
            assert page.has_active_background_task() is True

        def result(self):
            from PySide6.QtWidgets import QDialog
            return QDialog.DialogCode.Rejected

        def has_active_background_task(self):
            return True

    monkeypatch.setattr("app.views.pages.backups_page.BackupRestoreWizardDialog", lambda *a, **k: _BusyWizard())

    page._on_open_restore_wizard_clicked()

    assert page.has_active_background_task() is False
