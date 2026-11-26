from decimal import Decimal

import pytest

from app.config.settings import get_settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.services.backups import archive_manifest, external_media
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


# -- mission corrective §1/§3.1/§2.4 : pipeline robuste de configuration -------


def test_configure_media_rejects_a_root_that_does_not_exist(login_as, tmp_path) -> None:
    """Scénario exact diagnostiqué dans son principe (jamais une
    confirmation de succès pour un support qui ne peut pas réellement
    être retrouvé ensuite) : un support absent au moment de la
    configuration doit être refusé explicitement, jamais accepté avec un
    message générique de succès."""
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError, match="n'existe pas"):
        stack.external_backups.configure_media(tmp_path / "support_absent", "Support")


def test_configure_media_rejects_a_root_that_refuses_writes(login_as, tmp_path, monkeypatch) -> None:
    drive = tmp_path / "usb"
    drive.mkdir()
    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(
        "app.services.backups.external_backup_service.check_root_accessible",
        lambda root: "simulation : accès en écriture refusé.",
    )

    with pytest.raises(ValidationError, match="accès en écriture refusé"):
        stack.external_backups.configure_media(drive, "Support")


def test_configure_media_refuses_success_when_the_marker_cannot_be_reread(
    login_as, tmp_path, monkeypatch
) -> None:
    """Mission corrective, §1/§3.1 : le défaut diagnostiqué était « succès
    affiché, test d'accessibilité en échec immédiat ensuite » — même si
    ``create_marker`` n'a levé aucune exception, une relecture qui ne
    retrouve pas exactement ce qui vient d'être écrit doit faire échouer
    la configuration elle-même, jamais seulement le test ultérieur."""
    drive = tmp_path / "usb"
    drive.mkdir()
    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(
        "app.services.backups.external_backup_service.read_marker", lambda root: None,
    )

    with pytest.raises(ValidationError, match="relu"):
        stack.external_backups.configure_media(drive, "Support")

    # Rien n'a été persisté : aucune configuration partielle.
    config = stack.external_backups.get_config()
    assert config.is_configured is False


def test_a_failed_reconfiguration_attempt_never_erases_the_previous_working_configuration(
    login_as, tmp_path,
) -> None:
    """Un support déjà configuré avec succès reste la configuration
    active si une TENTATIVE ultérieure de reconfiguration échoue (racine
    inexistante, support retiré avant validation, etc.) — jamais une
    perte silencieuse de la configuration précédente qui fonctionnait
    (même principe que la protection des archives : configure_media
    n'écrit la nouvelle configuration qu'après son pipeline de
    vérifications complet, voir §1/§3.1 du mandat correctif)."""
    stack, _ = login_as("Administrateur")
    working_drive = tmp_path / "usb"
    working_drive.mkdir()
    stack.external_backups.configure_media(working_drive, "Support fonctionnel")

    with pytest.raises(ValidationError, match="n'existe pas"):
        stack.external_backups.configure_media(tmp_path / "support-inexistant", "Nouveau support")

    config = stack.external_backups.get_config()
    assert config.is_configured is True
    assert config.label == "Support fonctionnel"


def test_configure_media_normalizes_a_bare_drive_letter_before_writing_the_marker(
    login_as, tmp_path, monkeypatch
) -> None:
    """Reproduit directement la cause racine diagnostiquée : une forme
    ``« E: »`` sans barre finale (chemin relatif au lecteur en
    pathlib/Windows, jamais sa racine) doit être normalisée AVANT toute
    écriture — vérifié ici en interceptant l'appel à ``create_marker`` et
    en confirmant qu'il reçoit bien la racine canonique, jamais la forme
    brute reçue."""
    from app.services.backups import external_backup_service as ebs

    drive = tmp_path / "usb"
    drive.mkdir()
    stack, _ = login_as("Administrateur")
    received_roots = []
    original_create_marker = ebs.create_marker

    def _spy_create_marker(root, label):
        received_roots.append(root)
        return original_create_marker(root, label)

    monkeypatch.setattr(ebs, "normalize_drive_root", lambda path: drive)
    monkeypatch.setattr(ebs, "create_marker", _spy_create_marker)

    stack.external_backups.configure_media("E:", "Support")

    assert received_roots == [drive]


def test_reconfiguring_the_same_media_never_deletes_its_existing_archives(login_as, tmp_path) -> None:
    """§2.4 du mandat : « ne jamais supprimer ses archives existantes lors
    de sa configuration » — reconfigurer (ré-associer) le même support,
    ou un nouveau, ne doit jamais toucher aux fichiers déjà présents sur
    le support physique lui-même."""
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    existing_archive = drive / "StockManager_Sauvegardes" / "stockmanager_backup_20200101_020000.db"
    existing_archive.parent.mkdir(parents=True)
    existing_archive.write_bytes(b"ancienne archive")

    stack.external_backups.configure_media(drive, "Premier nom")
    stack.external_backups.configure_media(drive, "Nouveau nom")

    assert existing_archive.exists()
    assert existing_archive.read_bytes() == b"ancienne archive"


def test_list_available_drives_requires_permission(login_as) -> None:
    from app.utils.exceptions import PermissionDeniedError

    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.external_backups.list_available_drives()


def test_list_available_drives_delegates_to_external_media(login_as, tmp_path, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups._media_roots_provider = lambda: [drive]
    monkeypatch.setattr(
        external_media, "list_drives_with_info",
        lambda **kwargs: [
            external_media.DriveInfo(root=drive, drive_type="removable", volume_label="USB", marker=None)
        ],
    )

    drives = stack.external_backups.list_available_drives()

    assert len(drives) == 1
    assert drives[0].root == drive


def test_update_config_rejects_retention_below_minimum(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    (tmp_path / "usb").mkdir()
    stack.external_backups.configure_media(tmp_path / "usb", "Support")

    with pytest.raises(ValidationError):
        stack.external_backups.update_config(enabled=False, retention=MIN_RETENTION - 1)


def test_update_config_rejects_retention_above_maximum(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    (tmp_path / "usb").mkdir()
    stack.external_backups.configure_media(tmp_path / "usb", "Support")

    with pytest.raises(ValidationError):
        stack.external_backups.update_config(enabled=False, retention=MAX_RETENTION + 1)


def test_update_config_accepts_boundary_retention_values(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    (tmp_path / "usb").mkdir()
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
    (tmp_path / "usb").mkdir()
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


def test_media_still_recognized_after_a_simulated_drive_letter_change(login_as, tmp_path) -> None:
    """§3.4 du mandat : le support doit rester reconnu même si Windows lui
    attribue une lettre différente — jamais une lettre mémorisée, toujours
    l'identifiant du marqueur retrouvé parmi les lecteurs actuellement
    montés, quelle que soit leur lettre."""
    stack, _ = login_as("Administrateur")
    first_root = tmp_path / "e_drive"
    first_root.mkdir()
    stack.external_backups.configure_media(first_root, "Support")

    # Simule un rebranchement sous une lettre différente : le même disque
    # physique (même marqueur, donc même identité) apparaît maintenant à
    # un chemin différent — jamais le même objet Path que la configuration
    # initiale.
    second_root = tmp_path / "f_drive"
    second_root.mkdir()
    import shutil

    shutil.move(str(first_root / external_media.MARKER_DIRNAME), str(second_root / external_media.MARKER_DIRNAME))
    stack.external_backups._media_roots_provider = lambda: [second_root]

    assert stack.external_backups.test_media_accessible() is True
    assert stack.external_backups.find_current_media_root() == second_root


def test_reformatted_media_is_never_silently_recognized(login_as, tmp_path) -> None:
    """§3.4/§2.4 du mandat : un support reformaté (marqueur disparu) ne
    doit jamais être reconnu à tort — ``marker_id`` reste enregistré côté
    StockManager, mais le support doit être signalé inaccessible tant
    qu'une nouvelle configuration explicite n'a pas été faite, jamais une
    correspondance approximative sur le seul chemin ou le seul libellé."""
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")

    # Reformatage simulé : le marqueur disparaît, le support (même chemin,
    # même lettre) reste physiquement présent.
    import shutil

    shutil.rmtree(drive / external_media.MARKER_DIRNAME)

    config = stack.external_backups.get_config()
    assert config.is_configured is True  # toujours "configuré" du point de vue de StockManager
    assert stack.external_backups.test_media_accessible() is False
    assert stack.external_backups.find_current_media_root() is None


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


def test_copy_rejected_on_hash_mismatch_preserves_an_already_valid_older_external_backup(
    login_as, tmp_path, monkeypatch
) -> None:
    """Mission « Audit, correction et fiabilisation du système de
    sauvegarde », Partie C, §7 : « Les anciennes archives valides ne
    doivent jamais être supprimées pour compenser un échec » — vérifié
    ici avec une VRAIE ancienne copie externe déjà réussie, pas seulement
    l'absence de rotation sur un premier échec (voir le test précédent)."""
    import time

    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)

    stack.backups.create_manual_backup()
    first_copy = stack.external_backups.copy_now()
    assert first_copy.success is True

    time.sleep(1.1)
    stack.backups.create_manual_backup()

    real_copy = stack.external_backups._copy_file_atomically

    def _corrupting_copy(source, destination):
        result_path = real_copy(source, destination)
        if result_path.suffix != ".json":
            result_path.write_bytes(result_path.read_bytes() + b"corruption")
        return result_path

    monkeypatch.setattr(stack.external_backups, "_copy_file_atomically", staticmethod(_corrupting_copy))

    second_copy = stack.external_backups.copy_now()

    assert second_copy.success is False
    external_entries = stack.external_backups.list_external_backups()
    assert len(external_entries) == 1
    assert external_entries[0].info.path == first_copy.file_path
    assert external_entries[0].info.path.exists()


def test_copy_now_refuses_cleanly_when_the_only_local_backup_failed_verification(login_as, tmp_path) -> None:
    """Partie B, §5, point 5 : une archive locale invalide (ici, échec de
    vérification constaté à la création — jamais de manifeste écrit, voir
    ``BackupService._create_backup``) ne doit jamais pouvoir être
    proposée à la copie externe — ``copy_now`` doit alors refuser
    proprement, sans exception, avec une cause explicite."""
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)

    local_result = stack.backups.create_manual_backup()
    assert local_result.success is True
    # Simule une archive locale qui a échoué sa vérification après coup
    # (ex. altérée depuis) : son manifeste est donc supprimé, exactement
    # comme une archive qui n'en aurait jamais eu (voir
    # ``_latest_validated_local_backup``).
    archive_manifest.delete_manifest_for(local_result.file_path)

    result = stack.external_backups.copy_now()

    assert result.success is False
    assert "Aucune sauvegarde locale validée" in result.message
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
        stack.external_backups.configure_scheduled_task(time_of_day="20:00")


def test_configure_scheduled_task_requires_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.external_backups.configure_scheduled_task(time_of_day="20:00")


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
        stack.external_backups.configure_scheduled_task(time_of_day="20:00")

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


# -- mission corrective §3.6 : nouvelle tentative après un échec le même jour ---


def test_scheduled_copy_retries_the_same_day_after_media_absent_failure(login_as, tmp_path) -> None:
    """Scénario du mandat correctif : support absent à la première
    tentative (échec), puis reconnecté — une seconde tentative le même
    jour calendaire doit réussir, jamais bloquée par le seul échec
    précédent."""
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()

    stack.external_backups._media_roots_provider = lambda: []  # support débranché
    first = stack.external_backups.run_scheduled_external_copy_if_due()

    stack.external_backups._media_roots_provider = lambda: [drive]  # reconnecté
    second = stack.external_backups.run_scheduled_external_copy_if_due()

    assert first is not None
    assert first.success is False
    assert second is not None
    assert second.success is True


def test_scheduled_copy_does_not_retry_again_after_a_success_the_same_day(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()

    first = stack.external_backups.run_scheduled_external_copy_if_due()
    assert first is not None
    assert first.success is True

    stack.external_backups._media_roots_provider = lambda: []  # sans incidence : déjà réussi aujourd'hui
    second = stack.external_backups.run_scheduled_external_copy_if_due()

    assert second is None


def test_scheduled_copy_repeated_failures_never_delete_existing_external_backups(login_as, tmp_path) -> None:
    """§3.6 : plusieurs tentatives échouées le même jour ne doivent jamais
    supprimer les anciennes archives externes déjà présentes (rotation
    jamais appliquée sur un échec, garantie déjà existante — vérifiée ici
    en combinaison avec la nouvelle tentative)."""
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()
    # Copie manuelle (jamais soumise à la contrainte « une seule par jour »,
    # voir copy_now) pour simuler une archive externe déjà présente d'une
    # précédente échéance — sans quoi la toute première tentative
    # planifiée réussie du test interdirait elle-même toute nouvelle
    # tentative le même jour (comportement correct, mais pas ce que ce
    # test veut vérifier ici).
    first = stack.external_backups.copy_now()
    assert first.success is True
    existing_external_backups = stack.external_backups.list_external_backups()
    assert len(existing_external_backups) == 1

    stack.external_backups._media_roots_provider = lambda: []
    for _ in range(3):
        retry_result = stack.external_backups.run_scheduled_external_copy_if_due()
        assert retry_result is not None
        assert retry_result.success is False

    stack.external_backups._media_roots_provider = lambda: [drive]
    assert len(stack.external_backups.list_external_backups()) == 1


# -- mission corrective §3.5 : tâche onlogon + synchronisation de l'heure -------


def test_configure_scheduled_task_creates_both_daily_and_onlogon_tasks(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    calls = []
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(
        scheduled_task_manager, "create_or_repair_task",
        lambda name, exe, args, time_of_day, **kw: calls.append((name, kw.get("schedule"))),
    )

    stack.external_backups.configure_scheduled_task(time_of_day="20:00")

    names_and_schedules = {name: schedule for name, schedule in calls}
    assert "StockManager - Sauvegarde automatique" in names_and_schedules
    assert "StockManager - Sauvegarde automatique (ouverture de session)" in names_and_schedules
    assert names_and_schedules["StockManager - Sauvegarde automatique (ouverture de session)"] == (
        scheduled_task_manager.SCHEDULE_ONLOGON
    )


def test_configure_scheduled_task_fails_entirely_if_onlogon_task_fails(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())

    def _fake_create(name, exe, args, time_of_day, **kw):
        if kw.get("schedule") == scheduled_task_manager.SCHEDULE_ONLOGON:
            raise scheduled_task_manager.ScheduledTaskError("échec simulé")

    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", _fake_create)

    with pytest.raises(ValidationError):
        stack.external_backups.configure_scheduled_task(time_of_day="20:00")


def test_remove_scheduled_task_removes_both_tasks(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    removed = []
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(scheduled_task_manager, "delete_task", lambda name: removed.append(name))

    stack.external_backups.remove_scheduled_task()

    assert "StockManager - Sauvegarde automatique" in removed
    assert "StockManager - Sauvegarde automatique (ouverture de session)" in removed


def test_is_scheduled_task_time_synchronized_none_when_task_absent(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_status",
        lambda name: scheduled_task_manager.ScheduledTaskStatus(exists=False),
    )

    assert stack.external_backups.is_scheduled_task_time_synchronized() is None


def test_is_scheduled_task_time_synchronized_true_right_after_configuration(login_as, tmp_path, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="20:00",
        destination=str(tmp_path / "backups"), retention=10,
    )
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", lambda *a, **k: None)
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_status",
        lambda name: scheduled_task_manager.ScheduledTaskStatus(exists=True),
    )
    stack.external_backups.configure_scheduled_task(time_of_day="20:00")

    assert stack.external_backups.is_scheduled_task_time_synchronized() is True


def test_is_scheduled_task_time_synchronized_false_after_time_changed_without_reconfiguring(
    login_as, tmp_path, monkeypatch
) -> None:
    """Scénario exact du mandat correctif : l'heure est changée dans la
    configuration locale (« Enregistrer »), sans jamais recliquer sur
    « Configurer/réparer la tâche planifiée Windows… » — la détection doit
    signaler la désynchronisation plutôt que de laisser croire, à tort,
    que la tâche suit toujours la nouvelle heure."""
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="20:00", destination=str(destination), retention=10,
    )
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", lambda *a, **k: None)
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_status",
        lambda name: scheduled_task_manager.ScheduledTaskStatus(exists=True),
    )
    stack.external_backups.configure_scheduled_task(time_of_day="20:00")

    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="23:00", destination=str(destination), retention=10,
    )

    assert stack.external_backups.is_scheduled_task_time_synchronized() is False


# -- mission « Gestion complète de la planification des sauvegardes Windows » --


def test_is_onlogon_enabled_defaults_to_true_for_a_fresh_install(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.external_backups.is_onlogon_enabled() is True


def test_is_onlogon_enabled_respects_an_explicit_false(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", lambda *a, **k: None)
    monkeypatch.setattr(scheduled_task_manager, "delete_task", lambda name: None)

    stack.external_backups.configure_scheduled_task(time_of_day="20:00", onlogon_enabled=False)

    assert stack.external_backups.is_onlogon_enabled() is False


def test_configure_scheduled_task_reads_frequency_from_backup_service_when_omitted(
    login_as, tmp_path, monkeypatch
) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="weekly", time_of_day="21:00", destination=str(tmp_path / "backups"),
        retention=10, weekly_days=frozenset({2, 4}),
    )
    captured = {}
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())

    def _fake_create(name, exe, args, time_of_day, **kw):
        if name == "StockManager - Sauvegarde automatique":
            captured.update(kw)
            captured["time_of_day"] = time_of_day

    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", _fake_create)

    stack.external_backups.configure_scheduled_task()

    assert captured["schedule"] == "weekly"
    assert captured["time_of_day"] == "21:00"
    assert captured["weekly_days"] == frozenset({2, 4})


def test_configure_scheduled_task_uses_explicit_candidate_values_over_persisted_config(
    login_as, tmp_path, monkeypatch
) -> None:
    """Mission §5 : permet de valider une NOUVELLE configuration candidate
    auprès de Windows — ici une fréquence mensuelle jamais enregistrée
    dans StockManager (qui reste en « daily »)."""
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="20:00", destination=str(tmp_path / "backups"),
        retention=10,
    )
    captured = {}
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())

    def _fake_create(name, exe, args, time_of_day, **kw):
        if name == "StockManager - Sauvegarde automatique":
            captured.update(kw)
            captured["time_of_day"] = time_of_day

    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", _fake_create)

    stack.external_backups.configure_scheduled_task(
        frequency="monthly", time_of_day="22:00", monthly_day=15, monthly_last_day=False,
    )

    assert captured["schedule"] == "monthly"
    assert captured["time_of_day"] == "22:00"
    assert captured["monthly_day"] == 15
    assert captured["monthly_last_day"] is False
    # La configuration locale n'a jamais été modifiée par cet appel seul.
    assert stack.backups.get_config().frequency == "daily"


def test_configure_scheduled_task_deletes_onlogon_task_when_disabled(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    deleted = []
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", lambda *a, **k: None)
    monkeypatch.setattr(scheduled_task_manager, "delete_task", lambda name: deleted.append(name))

    stack.external_backups.configure_scheduled_task(time_of_day="20:00", onlogon_enabled=False)

    assert "StockManager - Sauvegarde automatique (ouverture de session)" in deleted
    assert "StockManager - Sauvegarde automatique" not in deleted


def test_scheduled_task_details_reports_absent_when_task_does_not_exist(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_status",
        lambda name: scheduled_task_manager.ScheduledTaskStatus(exists=False),
    )

    details = stack.external_backups.scheduled_task_details()

    assert details.exists is False
    assert details.name == "StockManager - Sauvegarde automatique"


def test_scheduled_task_details_reports_full_definition_when_present(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())

    def _fake_query_status(name):
        if name == "StockManager - Sauvegarde automatique":
            return scheduled_task_manager.ScheduledTaskStatus(
                exists=True, status="Ready", last_run_time="24/11/2026 20:00:00",
                next_run_time="25/11/2026 20:00:00", last_result="0",
            )
        return scheduled_task_manager.ScheduledTaskStatus(exists=True)

    monkeypatch.setattr(scheduled_task_manager, "query_task_status", _fake_query_status)
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_definition",
        lambda name: scheduled_task_manager.ScheduledTaskDefinition(
            command="C:/StockManager/StockManager.exe", arguments="--run-backup-agent",
            user_id="DESKTOP-TEST\\jdupont", schedule_kind="weekly", time_of_day="20:00",
            weekly_days=frozenset({0, 3}),
        ),
    )

    details = stack.external_backups.scheduled_task_details()

    assert details.exists is True
    assert details.status == "Ready"
    assert details.schedule_kind == "weekly"
    assert details.weekly_days == frozenset({0, 3})
    assert details.user_id == "DESKTOP-TEST\\jdupont"
    assert details.executable == "C:/StockManager/StockManager.exe"
    assert details.onlogon_task_exists is True


def test_scheduled_task_sync_warnings_empty_when_task_absent(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_status",
        lambda name: scheduled_task_manager.ScheduledTaskStatus(exists=False),
    )

    assert stack.external_backups.scheduled_task_sync_warnings() == []


def test_scheduled_task_sync_warnings_reports_frequency_mismatch(login_as, tmp_path, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="20:00", destination=str(tmp_path / "backups"),
        retention=10,
    )
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_status",
        lambda name: scheduled_task_manager.ScheduledTaskStatus(exists=True),
    )
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_definition",
        lambda name: scheduled_task_manager.ScheduledTaskDefinition(schedule_kind="weekly", time_of_day="20:00"),
    )
    monkeypatch.setattr(scheduled_task_manager, "resolve_current_user_id", lambda: "DESKTOP-TEST\\jdupont")

    warnings = stack.external_backups.scheduled_task_sync_warnings()

    assert any("fréquence" in warning for warning in warnings)


def test_scheduled_task_sync_warnings_reports_onlogon_mismatch(login_as, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())

    def _fake_query_status(name):
        return scheduled_task_manager.ScheduledTaskStatus(exists=name == "StockManager - Sauvegarde automatique")

    monkeypatch.setattr(scheduled_task_manager, "query_task_status", _fake_query_status)
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_definition",
        lambda name: scheduled_task_manager.ScheduledTaskDefinition(schedule_kind="daily", time_of_day="20:00"),
    )
    monkeypatch.setattr(scheduled_task_manager, "resolve_current_user_id", lambda: "DESKTOP-TEST\\jdupont")

    warnings = stack.external_backups.scheduled_task_sync_warnings()

    assert any("ouverture de session" in warning for warning in warnings)


def test_scheduled_task_sync_warnings_reports_account_mismatch(login_as, tmp_path, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="20:00", destination=str(tmp_path / "backups"),
        retention=10,
    )
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_status",
        lambda name: scheduled_task_manager.ScheduledTaskStatus(exists=True, run_as_user="DESKTOP-TEST\\autreCompte"),
    )
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_definition",
        lambda name: scheduled_task_manager.ScheduledTaskDefinition(schedule_kind="daily", time_of_day="20:00"),
    )
    monkeypatch.setattr(scheduled_task_manager, "resolve_current_user_id", lambda: "DESKTOP-TEST\\jdupont")

    warnings = stack.external_backups.scheduled_task_sync_warnings()

    assert any("autre compte" in warning for warning in warnings)


def test_scheduled_task_sync_warnings_empty_when_everything_matches(login_as, tmp_path, monkeypatch) -> None:
    from app.services.backups import scheduled_task_manager

    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="20:00", destination=str(tmp_path / "backups"),
        retention=10,
    )
    monkeypatch.setattr(scheduled_task_manager, "sys", type("_Sys", (), {"platform": "win32"})())
    monkeypatch.setattr(scheduled_task_manager, "create_or_repair_task", lambda *a, **k: None)
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_status",
        lambda name: scheduled_task_manager.ScheduledTaskStatus(exists=True, run_as_user="DESKTOP-TEST\\jdupont"),
    )
    monkeypatch.setattr(
        scheduled_task_manager, "query_task_definition",
        lambda name: scheduled_task_manager.ScheduledTaskDefinition(
            command=None, schedule_kind="daily", time_of_day="20:00",
        ),
    )
    monkeypatch.setattr(scheduled_task_manager, "resolve_current_user_id", lambda: "DESKTOP-TEST\\jdupont")
    stack.external_backups.configure_scheduled_task(time_of_day="20:00")

    warnings = stack.external_backups.scheduled_task_sync_warnings()

    assert warnings == []


def test_is_scheduled_task_time_synchronized_requires_view_permission(login_as) -> None:
    from app.utils.exceptions import PermissionDeniedError

    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.external_backups.is_scheduled_task_time_synchronized()


# -- mission corrective §3.7 : verrou partagé avec BackupService ---------------


def test_copy_now_refuses_cleanly_when_another_process_holds_the_shared_lock(login_as, tmp_path) -> None:
    """Une copie externe manuelle ne doit jamais s'exécuter en même temps
    qu'une autre opération de sauvegarde/restauration déjà en cours sur ce
    poste (§4, point « éviter les exécutions simultanées ») — y compris
    quand cette autre opération est détenue par un AUTRE processus (voir
    ``tests/test_process_lock.py`` pour la distinction réentrance
    intra-processus / refus inter-processus)."""
    import subprocess
    import sys
    import time

    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups.update_config(enabled=True, retention=30)
    stack.external_backups._media_roots_provider = lambda: [drive]
    _configure_local_backups(stack, tmp_path)
    stack.backups.create_manual_backup()

    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    time.sleep(0.2)
    lock_path = stack.external_backups._backup_lock()._lock_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(other.pid), encoding="utf-8")
    try:
        result = stack.external_backups.copy_now()
    finally:
        other.terminate()
        other.wait(timeout=5)
        lock_path.unlink(missing_ok=True)

    assert result.success is False
    assert "en cours" in result.message


def test_backup_service_and_external_backup_service_share_the_same_lock_file(login_as, tmp_path) -> None:
    """Preuve directe que les deux services protègent bien la MÊME
    ressource (exigence du mandat correctif : « une opération planifiée et
    une opération manuelle incompatible ne doivent jamais manipuler
    simultanément les mêmes fichiers ») : ``BackupService`` et
    ``ExternalBackupService`` construisent leur verrou à partir du même
    chemin résolu — un verrou acquis par l'un est donc vu par l'autre,
    sans qu'aucun appel réel de sauvegarde/copie ne soit nécessaire pour
    le démontrer."""
    stack, _ = login_as("Administrateur")

    backups_lock_path = stack.backups._backup_lock()._lock_path.resolve()
    external_lock_path = stack.external_backups._backup_lock()._lock_path.resolve()

    assert backups_lock_path == external_lock_path


# -- mission corrective §3.13 : nettoyage des fichiers temporaires orphelins ---


def test_cleanup_orphaned_temp_files_removes_old_orphans_on_the_external_media(login_as, tmp_path) -> None:
    import os
    import time

    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups._media_roots_provider = lambda: [drive]

    external_destination = stack.external_backups._external_destination(drive)
    external_destination.mkdir(parents=True, exist_ok=True)
    orphan = external_destination / ".stockmanager_backup_20200101_020000.db_abcdef.tmp"
    orphan.write_bytes(b"orphelin")
    old_time = time.time() - 7200
    os.utime(orphan, (old_time, old_time))

    removed = stack.external_backups.cleanup_orphaned_temp_files()

    assert removed == [orphan]
    assert not orphan.exists()


def test_cleanup_orphaned_temp_files_does_nothing_when_no_media_is_configured(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.external_backups.cleanup_orphaned_temp_files() == []


def test_cleanup_orphaned_temp_files_does_nothing_when_media_is_absent(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    drive = tmp_path / "usb"
    drive.mkdir()
    stack.external_backups.configure_media(drive, "Support")
    stack.external_backups._media_roots_provider = lambda: []

    assert stack.external_backups.cleanup_orphaned_temp_files() == []
