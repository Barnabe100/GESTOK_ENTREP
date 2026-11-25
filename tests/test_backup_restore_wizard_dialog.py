from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from app.services.backups import archive_manifest
from app.services.backups.backup_service import BackupConfig, RestoreResult
from app.utils.exceptions import ValidationError
from app.views.backup_restore_wizard_dialog import BackupRestoreWizardDialog


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.backup_restore_wizard_dialog.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.backup_restore_wizard_dialog.QMessageBox.warning", lambda *a, **k: None)
    monkeypatch.setattr("app.views.backup_restore_wizard_dialog.QMessageBox.critical", lambda *a, **k: None)


class _Verification:
    def __init__(self, valid: bool = True, errors=None) -> None:
        self.valid = valid
        self.errors = errors or []


class _FakeBackupService:
    def __init__(self, *, active_engine="sqlite", verification=None, restore_result=None, restore_error=None):
        self._active_engine = active_engine
        self._verification = verification or _Verification(True)
        self._restore_result = restore_result
        self._restore_error = restore_error
        self.restore_calls: list[str] = []
        self.update_config_calls: list[dict] = []
        self._config = BackupConfig(
            auto_enabled=False, frequency="daily", time_of_day="02:00",
            destination=Path("/ancien/dossier"), retention=30,
        )

    def active_engine(self) -> str:
        return self._active_engine

    def verify_backup_file(self, path):
        return self._verification

    def restore_backup(self, path):
        self.restore_calls.append(str(path))
        if self._restore_error is not None:
            raise self._restore_error
        return self._restore_result

    def get_config(self) -> BackupConfig:
        return self._config

    def update_config(self, **kwargs):
        self.update_config_calls.append(kwargs)
        self._config = BackupConfig(
            auto_enabled=kwargs["auto_enabled"], frequency=kwargs["frequency"], time_of_day=kwargs["time_of_day"],
            destination=Path(kwargs["destination"]), retention=kwargs["retention"],
            encryption_enabled=kwargs.get("encryption_enabled", False),
        )


def _make_archive(tmp_path, *, engine="sqlite", with_manifest=True):
    suffix = ".dump" if engine == "postgresql" else ".db"
    archive = tmp_path / f"stockmanager_backup_20260101_020000{suffix}"
    archive.write_bytes(b"contenu de sauvegarde")
    if with_manifest:
        archive_manifest.write_manifest_for(
            archive, db_engine=engine, schema_version="0018",
            backup_type=archive_manifest.BACKUP_TYPE_LOCAL,
        )
    return archive


def test_no_selection_shows_no_preview(qtbot) -> None:
    dialog = BackupRestoreWizardDialog(_FakeBackupService(), parent=None)
    qtbot.addWidget(dialog)

    assert dialog.info_group.isVisible() is False
    assert dialog.restore_button.isEnabled() is False


def test_selecting_valid_matching_archive_enables_restore(qtbot, tmp_path) -> None:
    archive = _make_archive(tmp_path)
    dialog = BackupRestoreWizardDialog(_FakeBackupService(active_engine="sqlite"), parent=None)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.select_file(archive)

    assert dialog.restore_button.isEnabled() is True
    assert "compatible" in dialog.compatibility_label.text()
    assert dialog.info_group.isVisible() is True


def test_shows_manifest_fields(qtbot, tmp_path) -> None:
    archive = _make_archive(tmp_path)
    dialog = BackupRestoreWizardDialog(_FakeBackupService(), parent=None)
    qtbot.addWidget(dialog)

    dialog.select_file(archive)

    from PySide6.QtWidgets import QLabel
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "0018" in labels


def test_invalid_archive_disables_restore(qtbot, tmp_path) -> None:
    archive = _make_archive(tmp_path)
    service = _FakeBackupService(verification=_Verification(False, ["corrompu"]))
    dialog = BackupRestoreWizardDialog(service, parent=None)
    qtbot.addWidget(dialog)

    dialog.select_file(archive)

    assert dialog.restore_button.isEnabled() is False
    assert "invalide" in dialog.compatibility_label.text().lower()


def test_mismatched_engine_disables_restore(qtbot, tmp_path) -> None:
    archive = _make_archive(tmp_path, engine="postgresql")
    service = _FakeBackupService(active_engine="sqlite")
    dialog = BackupRestoreWizardDialog(service, parent=None)
    qtbot.addWidget(dialog)

    dialog.select_file(archive)

    assert dialog.restore_button.isEnabled() is False
    assert "PostgreSQL" in dialog.compatibility_label.text()


def test_missing_file_shows_not_found(qtbot, tmp_path) -> None:
    dialog = BackupRestoreWizardDialog(_FakeBackupService(), parent=None)
    qtbot.addWidget(dialog)

    dialog.select_file(tmp_path / "absent.db")

    assert dialog.restore_button.isEnabled() is False
    assert "introuvable" in dialog.compatibility_label.text().lower()


def test_verification_error_is_reported(qtbot, tmp_path) -> None:
    archive = _make_archive(tmp_path)

    class _RaisingService(_FakeBackupService):
        def verify_backup_file(self, path):
            raise ValidationError("fichier verrouillé")

    dialog = BackupRestoreWizardDialog(_RaisingService(), parent=None)
    qtbot.addWidget(dialog)

    dialog.select_file(archive)

    assert dialog.restore_button.isEnabled() is False
    assert "Vérification impossible" in dialog.compatibility_label.text()


def test_restore_selected_success_accepts_dialog(qtbot, tmp_path) -> None:
    archive = _make_archive(tmp_path)
    service = _FakeBackupService(restore_result=RestoreResult(True, "Restauration réussie."))
    dialog = BackupRestoreWizardDialog(service, parent=None)
    qtbot.addWidget(dialog)
    dialog.select_file(archive)

    success = dialog._restore_selected()

    assert success is True
    assert service.restore_calls == [str(archive)]
    from PySide6.QtWidgets import QDialog
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_restore_offers_to_reconfigure_destination_when_warning_is_present(qtbot, tmp_path, monkeypatch) -> None:
    """Mission corrective §3.11 : même comportement que
    ``BackupsPage._offer_to_reconfigure_destination`` — ici aussi, jamais
    une notification silencieuse du dossier de destination inaccessible,
    toujours une proposition immédiate d'en choisir un nouveau."""
    archive = _make_archive(tmp_path)
    service = _FakeBackupService(
        restore_result=RestoreResult(
            True, "Restauration réussie.",
            destination_warning="Le dossier de destination des sauvegardes (« /ancien/poste ») n'existe pas.",
        ),
    )
    dialog = BackupRestoreWizardDialog(service, parent=None)
    qtbot.addWidget(dialog)
    dialog.select_file(archive)

    new_destination = tmp_path / "nouveau_dossier"
    new_destination.mkdir()
    monkeypatch.setattr(
        "app.views.backup_restore_wizard_dialog.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "app.views.backup_restore_wizard_dialog.QFileDialog.getExistingDirectory",
        lambda *a, **k: str(new_destination),
    )

    success = dialog._restore_selected()

    assert success is True
    assert service.get_config().destination == new_destination


def test_restore_destination_warning_declined_leaves_config_untouched(qtbot, tmp_path, monkeypatch) -> None:
    archive = _make_archive(tmp_path)
    service = _FakeBackupService(
        restore_result=RestoreResult(
            True, "Restauration réussie.", destination_warning="Dossier de destination introuvable.",
        ),
    )
    dialog = BackupRestoreWizardDialog(service, parent=None)
    qtbot.addWidget(dialog)
    dialog.select_file(archive)
    original_destination = service.get_config().destination

    monkeypatch.setattr(
        "app.views.backup_restore_wizard_dialog.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )

    dialog._restore_selected()

    assert service.get_config().destination == original_destination
    assert service.update_config_calls == []


def test_restore_without_destination_warning_never_prompts(qtbot, tmp_path, monkeypatch) -> None:
    archive = _make_archive(tmp_path)
    service = _FakeBackupService(restore_result=RestoreResult(True, "Restauration réussie."))
    dialog = BackupRestoreWizardDialog(service, parent=None)
    qtbot.addWidget(dialog)
    dialog.select_file(archive)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("confirm_action n'aurait jamais dû être sollicité sans avertissement.")

    monkeypatch.setattr("app.views.backup_restore_wizard_dialog.QMessageBox.question", _fail_if_called)

    success = dialog._restore_selected()

    assert success is True


def test_restore_selected_failure_does_not_accept(qtbot, tmp_path) -> None:
    archive = _make_archive(tmp_path)
    service = _FakeBackupService(restore_result=RestoreResult(False, "Échec."))
    dialog = BackupRestoreWizardDialog(service, parent=None)
    qtbot.addWidget(dialog)
    dialog.select_file(archive)

    success = dialog._restore_selected()

    assert success is False


def test_restore_selected_app_error_is_caught(qtbot, tmp_path) -> None:
    archive = _make_archive(tmp_path)
    service = _FakeBackupService(restore_error=ValidationError("refusé"))
    dialog = BackupRestoreWizardDialog(service, parent=None)
    qtbot.addWidget(dialog)
    dialog.select_file(archive)

    success = dialog._restore_selected()

    assert success is False


def test_has_active_background_task_false_by_default(qtbot) -> None:
    dialog = BackupRestoreWizardDialog(_FakeBackupService(), parent=None)
    qtbot.addWidget(dialog)

    assert dialog.has_active_background_task() is False


def test_browse_starts_at_configured_external_media_root(qtbot, tmp_path, monkeypatch) -> None:
    class _FakeExternalService:
        def find_current_media_root(self):
            return tmp_path / "cle_usb"

    dialog = BackupRestoreWizardDialog(
        _FakeBackupService(), parent=None, external_backup_service=_FakeExternalService(),
    )
    qtbot.addWidget(dialog)

    captured = {}

    def _fake_get_open_file_name(*args, **kwargs):
        captured["start_dir"] = args[2] if len(args) > 2 else kwargs.get("dir")
        return "", ""

    monkeypatch.setattr(
        "app.views.backup_restore_wizard_dialog.QFileDialog.getOpenFileName", _fake_get_open_file_name,
    )

    dialog._on_browse_clicked()

    assert captured["start_dir"] == str(tmp_path / "cle_usb")


def test_browse_uses_empty_start_dir_when_media_absent(qtbot, monkeypatch) -> None:
    class _FakeExternalService:
        def find_current_media_root(self):
            return None

    dialog = BackupRestoreWizardDialog(
        _FakeBackupService(), parent=None, external_backup_service=_FakeExternalService(),
    )
    qtbot.addWidget(dialog)

    captured = {}

    def _fake_get_open_file_name(*args, **kwargs):
        captured["start_dir"] = args[2] if len(args) > 2 else kwargs.get("dir")
        return "", ""

    monkeypatch.setattr(
        "app.views.backup_restore_wizard_dialog.QFileDialog.getOpenFileName", _fake_get_open_file_name,
    )

    dialog._on_browse_clicked()

    assert captured["start_dir"] == ""
