from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel

from app.services.backups import archive_manifest, backup_engine
from app.views.backup_details_dialog import BackupDetailsDialog


def _make_entry(tmp_path, engine="sqlite", with_manifest=True, encrypted=False):
    from app.services.backups.backup_service import BackupEntry

    archive = tmp_path / "stockmanager_backup_20260101_020000.db"
    archive.write_bytes(b"contenu de sauvegarde")
    if with_manifest:
        archive_manifest.write_manifest_for(
            archive, db_engine=engine, schema_version="0018",
            backup_type=archive_manifest.BACKUP_TYPE_LOCAL, encrypted=encrypted,
        )
    info = backup_engine.BackupFileInfo(
        path=archive, name=archive.name, size_bytes=archive.stat().st_size, modified_at=datetime.now(),
    )
    return BackupEntry(engine, info)


class _FakeBackupService:
    def __init__(self, valid: bool = True, errors: list[str] | None = None) -> None:
        self._valid = valid
        self._errors = errors or []

    def describe_backup_status(self, path):
        from app.services.backups.backup_service import STATUS_INVALID, STATUS_VALID, BackupStatusReport

        label = STATUS_VALID if self._valid else STATUS_INVALID
        return BackupStatusReport(
            valid=self._valid, label=label, errors=self._errors,
            manifest_present=False, manifest_hash_matches=None,
        )


def test_shows_name_type_and_engine(qtbot, tmp_path) -> None:
    entry = _make_entry(tmp_path)
    dialog = BackupDetailsDialog(entry, "Locale", _FakeBackupService(), parent=None)
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert entry.info.name in labels
    assert "Locale" in labels
    assert "SQLite" in labels


def test_shows_valid_status(qtbot, tmp_path) -> None:
    entry = _make_entry(tmp_path)
    dialog = BackupDetailsDialog(entry, "Locale", _FakeBackupService(valid=True), parent=None)
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Valide" in labels


def test_shows_invalid_status(qtbot, tmp_path) -> None:
    entry = _make_entry(tmp_path)
    dialog = BackupDetailsDialog(entry, "Locale", _FakeBackupService(valid=False), parent=None)
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Invalide" in labels


def test_shows_manifest_fields_when_present(qtbot, tmp_path) -> None:
    entry = _make_entry(tmp_path, with_manifest=True, encrypted=True)
    dialog = BackupDetailsDialog(entry, "Locale", _FakeBackupService(), parent=None)
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "0018" in labels
    assert "Oui" in labels  # Chiffrée


def test_shows_fallback_message_when_manifest_absent(qtbot, tmp_path) -> None:
    entry = _make_entry(tmp_path, with_manifest=False)
    dialog = BackupDetailsDialog(entry, "Locale", _FakeBackupService(), parent=None)
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("Aucun manifeste" in text for text in labels)


def test_shows_detailed_errors_when_invalid(qtbot, tmp_path) -> None:
    """Mission « Audit, correction et fiabilisation du système de
    sauvegarde », §10 : la cause exacte (``verification.errors``) doit
    rester consultable depuis cette fenêtre, jamais seulement un statut
    nu « Invalide » sans explication."""
    entry = _make_entry(tmp_path)
    dialog = BackupDetailsDialog(
        entry, "Locale",
        _FakeBackupService(valid=False, errors=["Table manquante dans l'archive : clients"]),
        parent=None,
    )
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert any("Table manquante dans l'archive : clients" in text for text in labels)


def test_close_button_accepts(qtbot, tmp_path) -> None:
    entry = _make_entry(tmp_path)
    dialog = BackupDetailsDialog(entry, "Locale", _FakeBackupService(), parent=None)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
