from decimal import Decimal

import pytest

from app.config.settings import get_settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.services.backups import archive_manifest
from app.services.backups.external_backup_service import MAX_RETENTION, MIN_RETENTION
from app.utils.exceptions import PermissionDeniedError, ValidationError


def _audit_rows(action: str) -> list[AuditLog]:
    with session_scope(get_settings()) as session:
        return session.query(AuditLog).filter_by(action=action).all()


def _make_article(stack, reference="ART-1", stock_initial=Decimal("10")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def _configure_local_backups(stack, tmp_path):
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(tmp_path / "local_backups"), retention=30,
    )


# -- configuration --------------------------------------------------------------


def test_get_config_returns_safe_defaults(login_as) -> None:
    stack, _ = login_as("Administrateur")

    config = stack.external_backups.get_config()

    assert config.enabled is False
    assert config.is_configured is False
    assert config.retention == 30


def test_configure_media_writes_marker_and_persists_identity(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()

    config = stack.external_backups.configure_media(drive, "Clé USB de Jean")

    assert config.is_configured is True
    assert config.label == "Clé USB de Jean"
    assert config.marker_id


def test_configure_media_rejects_empty_label(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()

    with pytest.raises(ValidationError):
        stack.external_backups.configure_media(drive, "   ")


def test_update_config_rejects_retention_below_minimum(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.external_backups.configure_media(tmp_path / "usb", "Support")

    with pytest.raises(ValidationError):
        stack.external_backups.update_config(enabled=False, retention=MIN_RETENTION - 1)


def test_update_config_rejects_retention_above_maximum(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.external_backups.configure_media(tmp_path / "usb", "Support")

    with pytest.raises(ValidationError):
        stack.external_backups.update_config(enabled=False, retention=MAX_RETENTION + 1)


def test_update_config_accepts_boundary_retention_values(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.external_backups.configure_media(tmp_path / "usb", "Support")

    low = stack.external_backups.update_config(enabled=False, retention=MIN_RETENTION)
    high = stack.external_backups.update_config(enabled=False, retention=MAX_RETENTION)

    assert low.retention == MIN_RETENTION
    assert high.retention == MAX_RETENTION


def test_update_config_rejects_enabling_without_configured_media(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.external_backups.update_config(enabled=True, retention=30)


def test_update_config_succeeds_after_media_configured(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.external_backups.configure_media(tmp_path / "usb", "Support")

    config = stack.external_backups.update_config(enabled=True, retention=40)

    assert config.enabled is True
    assert config.retention == 40


def test_non_admin_cannot_configure_media(login_as, tmp_path) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.external_backups.configure_media(tmp_path / "usb", "Support")


# -- accessibilité du support (racines simulées, jamais de vraie lettre Windows) --


def test_media_accessible_when_drive_present_among_candidates(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups._media_roots_provider = lambda: [unrelated, drive]

    assert stack.external_backups.test_media_accessible() is True


def test_media_not_accessible_when_drive_absent_from_candidates(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups._media_roots_provider = lambda: []  # support débranché

    assert stack.external_backups.test_media_accessible() is False


def test_media_not_accessible_when_not_configured(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.external_backups.test_media_accessible() is False


# -- copie ------------------------------------------------------------------------


def test_copy_now_fails_cleanly_when_not_configured(login_as) -> None:
    stack, _ = login_as("Administrateur")

    result = stack.external_backups.copy_now()

    assert result.success is False
    assert "support" in result.message.lower()


def test_copy_now_fails_when_media_absent(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: []  # support débranché

    result = stack.external_backups.copy_now()

    assert result.success is False


def test_copy_now_fails_when_no_local_backup_exists(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)

    result = stack.external_backups.copy_now()

    assert result.success is False
    assert "aucune sauvegarde" in result.message.lower()


def test_copy_now_succeeds_and_copies_the_latest_validated_backup(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, stock_initial=Decimal("55"))
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)

    local_result = stack.backups.create_manual_backup()
    assert local_result.success is True

    copy_result = stack.external_backups.copy_now()

    assert copy_result.success is True
    assert copy_result.file_path.exists()
    assert copy_result.file_path.name == local_result.file_path.name
    assert copy_result.file_path.read_bytes() == local_result.file_path.read_bytes()


def test_copy_now_also_copies_the_manifest_sidecar(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()

    copy_result = stack.external_backups.copy_now()

    copied_manifest = archive_manifest.read_manifest_for(copy_result.file_path)
    assert copied_manifest is not None
    assert copied_manifest.sha256 == archive_manifest.compute_sha256(copy_result.file_path)


def test_copy_now_updates_last_run_at_and_last_result(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()

    stack.external_backups.copy_now()

    config = stack.external_backups.get_config()
    assert config.last_run_at is not None
    assert config.last_result == "Copie externe réussie."


def test_copy_respects_external_retention(login_as, tmp_path) -> None:
    import time

    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=MIN_RETENTION)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)

    for _ in range(MIN_RETENTION + 3):
        stack.backups.create_manual_backup()
        time.sleep(1.1)
        stack.external_backups.copy_now()

    external_entries = stack.external_backups.list_external_backups()

    assert len(external_entries) == MIN_RETENTION


def test_copy_never_deletes_anything_when_copy_verification_would_fail(login_as, tmp_path, monkeypatch) -> None:
    """Simule une copie altérée (empreinte différente après coup) — la
    rotation externe ne doit jamais s'exécuter dans ce cas (§4, point 10)."""
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()

    real_copy = stack.external_backups._copy_file_atomically

    def _corrupting_copy(source, destination):
        result_path = real_copy(source, destination)
        if result_path.suffix != ".json":  # corrompt uniquement l'archive, pas le manifeste copié
            result_path.write_bytes(result_path.read_bytes() + b"corruption")
        return result_path

    monkeypatch.setattr(stack.external_backups, "_copy_file_atomically", staticmethod(_corrupting_copy))

    result = stack.external_backups.copy_now()

    assert result.success is False
    assert stack.external_backups.list_external_backups() == []


# -- déclenchement planifié ---------------------------------------------------------


def test_scheduled_copy_does_nothing_when_disabled(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups._media_roots_provider = lambda: [drive]

    result = stack.external_backups.run_scheduled_external_copy_if_due()

    assert result is None


def test_scheduled_copy_does_nothing_when_not_configured(login_as) -> None:
    stack, _ = login_as("Administrateur")

    result = stack.external_backups.run_scheduled_external_copy_if_due()

    assert result is None


def test_scheduled_copy_runs_once_per_day(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()

    first = stack.external_backups.run_scheduled_external_copy_if_due()
    second = stack.external_backups.run_scheduled_external_copy_if_due()

    assert first is not None
    assert first.success is True
    assert second is None


# -- historique ---------------------------------------------------------------------


def test_list_external_backups_empty_when_media_absent(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups._media_roots_provider = lambda: []

    assert stack.external_backups.list_external_backups() == []


def test_list_external_backups_empty_when_not_configured(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.external_backups.list_external_backups() == []


# -- tâche planifiée Windows : refus explicite hors Windows + permissions --------
#
# Ces tests s'exécutent sur Linux : ils prouvent le refus explicite et la
# vérification de permission, jamais le comportement réel de schtasks.exe
# (voir tests/test_scheduled_task_manager_windows_integration.py).


def test_configure_scheduled_task_translates_unsupported_platform_to_validation_error(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.external_backups.configure_scheduled_task("20:00")


def test_configure_scheduled_task_requires_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.external_backups.configure_scheduled_task("20:00")


def test_remove_scheduled_task_translates_unsupported_platform_to_validation_error(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.external_backups.remove_scheduled_task()


def test_remove_scheduled_task_requires_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.external_backups.remove_scheduled_task()


def test_scheduled_task_status_requires_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.external_backups.scheduled_task_status()


def test_scheduled_task_status_raises_outside_windows(login_as) -> None:
    from app.utils.exceptions import UnsupportedPlatformError

    stack, _ = login_as("Administrateur")

    with pytest.raises(UnsupportedPlatformError):
        stack.external_backups.scheduled_task_status()


# -- tâche planifiée Windows : échec réel (ex. droits insuffisants) ---------------
#
# Simule directement un échec de ``schtasks.exe`` (ex. accès refusé) en
# substituant ``scheduled_task_manager.create_or_repair_task``/``delete_task``
# — jamais le garde ``_ensure_windows`` lui-même (voir
# test_scheduled_task_manager.py::TestErrorTranslation pour cette logique de
# traduction isolée) — afin de vérifier que le service traduit bien
# ``ScheduledTaskError`` en ``ValidationError`` ET journalise l'échec dans
# l'audit (§8 du mandat : gestion des erreurs de permission).


def test_configure_scheduled_task_translates_permission_error_and_audits_failure(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")

    def _raise_permission_denied(*args, **kwargs):
        raise scheduled_task_manager.ScheduledTaskError("Accès refusé (droits insuffisants).")

    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", _raise_permission_denied)

    with pytest.raises(ValidationError):
        stack.external_backups.configure_scheduled_task("20:00")

    rows = _audit_rows("BACKUP_SCHEDULED_TASK_CONFIGURE_FAILURE")
    assert len(rows) == 1
    assert rows[0].resultat == ResultatAudit.ECHEC


def test_remove_scheduled_task_translates_permission_error_and_audits_failure(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")

    def _raise_permission_denied(*args, **kwargs):
        raise scheduled_task_manager.ScheduledTaskError("Accès refusé (droits insuffisants).")

    monkeypatch.setattr(scheduled_task_manager, "delete_task", _raise_permission_denied)

    with pytest.raises(ValidationError):
        stack.external_backups.remove_scheduled_task()

    rows = _audit_rows("BACKUP_SCHEDULED_TASK_REMOVE_FAILURE")
    assert len(rows) == 1
    assert rows[0].resultat == ResultatAudit.ECHEC


# -- bout en bout : restauration depuis une archive copiée sur le support --------
#
# Critère de réussite n°10 de la mission : « la restauration doit être
# possible... y compris sur un nouvel ordinateur, à partir d'une archive
# externe ». Ici le même ``BackupService`` sert les deux rôles (il n'existe
# qu'un moteur de restauration, voir BackupRestoreWizardDialog) ; le
# scénario réel (poste différent) change seulement d'où vient le chemin
# fourni à ``restore_backup`` — jamais sa logique de vérification.


def test_restore_from_externally_copied_archive_succeeds(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, stock_initial=Decimal("55"))
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()
    copy_result = stack.external_backups.copy_now()
    assert copy_result.success is True

    restore_result = stack.backups.restore_backup(copy_result.file_path)

    assert restore_result.success is True
