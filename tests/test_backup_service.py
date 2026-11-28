import dataclasses
import shutil
import sqlite3
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory

from app.config.settings import get_settings
from app.db.init_db import _alembic_config
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.services.backups import archive_manifest, backup_engine
from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError


class _FakeEncryptionVault:
    """Coffre d'identifiants en mémoire, injecté dans ``BackupService``
    pour valider le cycle complet chiffrement/sauvegarde/restauration sans
    Windows Credential Manager (voir ``BackupService.__init__``,
    paramètre ``encryption_vault``) — jamais utilisé en dehors des tests."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get_password(self, profile_id: str):
        return self._store.get(profile_id)

    def set_password(self, profile_id: str, password: str) -> None:
        self._store[profile_id] = password

    def delete_password(self, profile_id: str) -> None:
        self._store.pop(profile_id, None)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("10")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def _audit_rows(action: str) -> list[AuditLog]:
    with session_scope(get_settings()) as session:
        return session.query(AuditLog).filter_by(action=action).all()


# -- configuration ----------------------------------------------------------------


def test_get_config_returns_autonomous_defaults_for_a_fresh_install(login_as) -> None:
    """Mission corrective « Correction et validation du module de
    sauvegarde sous Windows », §2.1 : un poste neuf (jamais configuré)
    démarre avec la sauvegarde locale quotidienne ACTIVE par défaut —
    l'architecture cible veut une protection autonome dès l'installation,
    sans geste supplémentaire de l'administrateur."""
    stack, _ = login_as("Administrateur")

    config = stack.backups.get_config()

    assert config.auto_enabled is True
    assert config.frequency == "daily"
    assert config.time_of_day == "20:00"
    assert config.retention == 30


def test_get_config_never_silently_re_enables_an_explicitly_disabled_installation(login_as, tmp_path) -> None:
    """Un poste déjà configuré — même explicitement désactivé par un
    enregistrement antérieur — ne doit jamais être réactivé
    silencieusement par ce nouveau défaut : seule l'ABSENCE totale de
    toute valeur enregistrée déclenche le défaut autonome ci-dessus."""
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="weekly", time_of_day="03:00",
        destination=str(tmp_path / "backups"), retention=15, weekly_days=frozenset({0}),
    )

    config = stack.backups.get_config()

    assert config.auto_enabled is False
    assert config.frequency == "weekly"


def test_update_config_persists_values(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"

    updated = stack.backups.update_config(
        auto_enabled=True, frequency="weekly", time_of_day="03:30",
        destination=str(destination), retention=5, weekly_days=frozenset({0}),
    )

    assert updated.auto_enabled is True
    assert updated.frequency == "weekly"
    assert updated.time_of_day == "03:30"
    assert updated.destination == destination
    assert updated.retention == 5

    reloaded = stack.backups.get_config()
    assert reloaded == updated


def test_update_config_rejects_invalid_frequency(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.backups.update_config(
            auto_enabled=False, frequency="yearly", time_of_day="02:00",
            destination=str(tmp_path / "backups"), retention=5,
        )


def test_update_config_rejects_invalid_time(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="pas une heure",
            destination=str(tmp_path / "backups"), retention=5,
        )


def test_update_config_rejects_retention_below_one(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="02:00",
            destination=str(tmp_path / "backups"), retention=0,
        )


def test_update_config_rejects_destination_that_is_a_file(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    blocked = tmp_path / "obstacle"
    blocked.write_text("fichier, pas dossier")

    with pytest.raises(ValidationError):
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="02:00",
            destination=str(blocked), retention=5,
        )


def test_update_config_creates_destination_directory(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "not_yet_created" / "backups"

    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=5,
    )

    assert destination.is_dir()


# -- sauvegarde manuelle ----------------------------------------------------------


def test_create_manual_backup_succeeds(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)

    result = stack.backups.create_manual_backup()

    assert result.success is True
    assert result.file_path.exists()


def test_create_manual_backup_file_is_valid_sqlite_with_integrity(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)

    result = stack.backups.create_manual_backup()

    verification = backup_engine.verify_backup_file(result.file_path)
    assert verification.valid is True
    assert verification.integrity_ok is True
    assert verification.tables_ok is True


def test_create_manual_backup_contains_current_data(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("42"))
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)

    result = stack.backups.create_manual_backup()

    conn = sqlite3.connect(str(result.file_path))
    row = conn.execute("SELECT stock_actuel FROM articles WHERE reference = ?", (article.reference,)).fetchone()
    conn.close()
    assert row is not None
    assert Decimal(row[0]) == Decimal("42")


def test_create_manual_backup_fails_on_unwritable_destination(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    blocked = tmp_path / "blocked_file"
    blocked.write_text("obstacle")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.backups.backup_engine.create_backup_file",
            lambda *a, **k: (_ for _ in ()).throw(OSError("disque plein (simulé)")),
        )
        result = stack.backups.create_manual_backup()

    assert result.success is False
    assert "disque plein" in result.message.lower() or "échec" in result.message.lower()


def test_create_manual_backup_requires_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.backups.create_manual_backup()


def test_consultation_can_list_backups_but_not_create_or_restore(login_as, tmp_path) -> None:
    """Extension à tous les menus en lecture seule : Consultation reçoit
    désormais BACKUP_VIEW, mais toujours ni BACKUP_CREATE ni
    BACKUP_RESTORE — ne peut ni créer ni restaurer une sauvegarde."""
    admin_stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    admin_stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10,
    )
    backup_result = admin_stack.backups.create_manual_backup()

    stack, _ = login_as("Consultation")

    assert stack.backups.list_backups() != []

    with pytest.raises(PermissionDeniedError):
        stack.backups.create_manual_backup()

    with pytest.raises(PermissionDeniedError):
        stack.backups.restore_backup(backup_result.file_path)


# -- rétention via le service -------------------------------------------------------


def test_manual_backups_respect_configured_retention(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=2)

    for _ in range(4):
        result = stack.backups.create_manual_backup()
        assert result.success
        time.sleep(1.1)  # noms de fichiers horodatés à la seconde

    backups = stack.backups.list_backups()
    assert len(backups) == 2


def test_retention_rotation_is_audited(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=1)

    stack.backups.create_manual_backup()
    time.sleep(1.1)
    stack.backups.create_manual_backup()

    rows = _audit_rows("BACKUP_ROTATION")
    assert len(rows) == 1


# -- historique --------------------------------------------------------------------


def test_list_backups_requires_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.backups.list_backups()


# -- restauration -------------------------------------------------------------------


def test_restore_backup_succeeds_and_restores_data(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)

    article = _make_article(stack, stock_initial=Decimal("10"))
    backup_result = stack.backups.create_manual_backup()
    assert backup_result.success

    # Modification après la sauvegarde : doit disparaître après restauration.
    _make_article(stack, reference="ART-APRES", stock_initial=Decimal("5"))
    assert len(stack.articles.list_articles()) == 2

    restore_result = stack.backups.restore_backup(backup_result.file_path)

    assert restore_result.success is True
    references = {a.reference for a in stack.articles.list_articles()}
    assert references == {article.reference}


def test_restore_reports_no_destination_warning_when_folder_is_still_valid(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    backup_result = stack.backups.create_manual_backup()

    restore_result = stack.backups.restore_backup(backup_result.file_path)

    assert restore_result.success is True
    assert restore_result.destination_warning is None


def test_restore_warns_when_restored_destination_folder_does_not_exist_on_this_computer(login_as, tmp_path) -> None:
    """Scénario exact du mandat correctif (§3.11) : la sauvegarde restaurée
    porte en elle la configuration de l'ANCIEN poste (ex. changement
    d'ordinateur) — si le dossier de destination qu'elle désigne n'existe
    plus sur CE poste, la restauration doit tout de même réussir (jamais
    bloquant), mais signaler clairement le problème pour que
    l'administrateur en reconfigure un nouveau avant la prochaine
    sauvegarde — jamais une panne silencieuse découverte seulement au
    prochain échec de sauvegarde planifiée."""
    stack, _ = login_as("Administrateur")
    old_destination = tmp_path / "ancien_poste" / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(old_destination), retention=10,
    )
    backup_result = stack.backups.create_manual_backup()
    assert backup_result.success is True

    # Le fichier de sauvegarde lui-même est apporté sur CE poste (ex. via
    # une clé USB) — seul l'ANCIEN dossier de destination, lui, n'existe
    # plus ici : on le copie donc ailleurs avant de simuler sa disparition.
    brought_backup_path = tmp_path / backup_result.file_path.name
    shutil.copy2(backup_result.file_path, brought_backup_path)
    shutil.rmtree(old_destination)
    new_destination = tmp_path / "ce_poste" / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(new_destination), retention=10,
    )

    restore_result = stack.backups.restore_backup(brought_backup_path)

    assert restore_result.success is True
    assert restore_result.destination_warning is not None
    assert str(old_destination) in restore_result.destination_warning


def test_check_destination_accessible_returns_none_for_a_writable_folder(tmp_path) -> None:
    from app.services.backups.backup_service import _check_destination_accessible

    folder = tmp_path / "ok"
    folder.mkdir()

    assert _check_destination_accessible(folder) is None


def test_check_destination_accessible_reports_a_missing_folder(tmp_path) -> None:
    from app.services.backups.backup_service import _check_destination_accessible

    message = _check_destination_accessible(tmp_path / "absent")

    assert message is not None
    assert "n'existe pas" in message


# -- mission corrective §3.13 : nettoyage des fichiers temporaires orphelins ---


def test_cleanup_orphaned_temp_files_removes_old_orphans_in_db_and_destination_folders(login_as, tmp_path) -> None:
    import os

    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)

    db_orphan = stack.backups._db_path().parent / ".stockmanager.db_restore_abcdef.tmp"
    db_orphan.write_bytes(b"orphelin")
    destination_orphan = destination / ".stockmanager_backup_20200101_020000.db_abcdef.creating.tmp"
    destination_orphan.write_bytes(b"orphelin")
    old_time = time.time() - 7200
    os.utime(db_orphan, (old_time, old_time))
    os.utime(destination_orphan, (old_time, old_time))

    removed = stack.backups.cleanup_orphaned_temp_files()

    assert set(removed) == {db_orphan, destination_orphan}
    assert not db_orphan.exists()
    assert not destination_orphan.exists()


def test_cleanup_orphaned_temp_files_never_removes_a_recent_temp_file(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    recent_orphan = destination / ".stockmanager_backup_20260101_020000.db_abcdef.creating.tmp"
    recent_orphan.write_bytes(b"operation en cours")

    removed = stack.backups.cleanup_orphaned_temp_files()

    assert removed == []
    assert recent_orphan.exists()


def test_cleanup_orphaned_temp_files_does_nothing_while_the_shared_lock_is_held(login_as, tmp_path) -> None:
    """§3.13/§3.7 : jamais de suppression tant qu'une autre opération
    pourrait être en cours — simulée ici en détenant le verrou partagé
    depuis un autre processus."""
    import os
    import subprocess
    import sys

    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    orphan = destination / ".stockmanager_backup_20200101_020000.db_abcdef.creating.tmp"
    orphan.write_bytes(b"orphelin")
    old_time = time.time() - 7200
    os.utime(orphan, (old_time, old_time))

    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    time.sleep(0.2)
    lock_path = stack.backups._backup_lock()._lock_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(other.pid), encoding="utf-8")
    try:
        removed = stack.backups.cleanup_orphaned_temp_files()
    finally:
        other.terminate()
        other.wait(timeout=5)
        lock_path.unlink(missing_ok=True)

    assert removed == []
    assert orphan.exists()


def test_restore_backup_creates_security_backup_first(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    backup_result = stack.backups.create_manual_backup()

    restore_result = stack.backups.restore_backup(backup_result.file_path)

    assert restore_result.security_backup_path is not None
    assert restore_result.security_backup_path.exists()
    assert restore_result.security_backup_path.name.startswith(backup_engine.PRERESTORE_PREFIX)


def test_restore_backup_rejects_invalid_file(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))
    fake = tmp_path / "fake.db"
    fake.write_bytes(b"pas une base sqlite valide")

    with pytest.raises(ValidationError):
        stack.backups.restore_backup(fake)

    # La base actuelle reste intacte.
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")


def test_restore_backup_rejects_incompatible_schema_version(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))

    # Base SQLite valide, tables attendues présentes, mais version de schéma
    # différente de la base actuelle : doit être refusée (§10).
    incompatible = tmp_path / "incompatible.db"
    from app.models import Base

    conn = sqlite3.connect(str(incompatible))
    for table in Base.metadata.sorted_tables:
        columns_sql = ", ".join(f'"{c.name}" TEXT' for c in table.columns) or "id INTEGER"
        conn.execute(f'CREATE TABLE "{table.name}" ({columns_sql})')
    conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
    conn.execute("INSERT INTO alembic_version (version_num) VALUES ('9999_ne_correspond_pas')")
    conn.commit()
    conn.close()

    with pytest.raises(ValidationError):
        stack.backups.restore_backup(incompatible)

    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")


def test_restore_backup_requires_permission(login_as, tmp_path) -> None:
    admin_stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    admin_stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    backup_result = admin_stack.backups.create_manual_backup()

    stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        stack.backups.restore_backup(backup_result.file_path)


def test_restore_failure_recovers_previous_database_from_security_backup(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    article = _make_article(stack, stock_initial=Decimal("77"))
    backup_result = stack.backups.create_manual_backup()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.backups.backup_engine.restore_database_from_backup",
            lambda *a, **k: (_ for _ in ()).throw(OSError("panne simulée pendant la restauration")),
        )
        restore_result = stack.backups.restore_backup(backup_result.file_path)

    assert restore_result.success is False
    # La base actuelle n'est pas corrompue : les données d'origine sont intactes.
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("77")


# -- mission corrective §3.10 : compatibilité de version assouplie -------------


def _build_old_schema_db(stack, tmp_path, revision: str):
    """Construit une sauvegarde réaliste d'une version ANTÉRIEURE (mais
    compatible) de StockManager : un instantané de la base active ACTUELLE
    (utilisateurs, données déjà créées comprises), puis migré en ARRIÈRE
    jusqu'à ``revision`` — jamais une base vide reconstruite depuis zéro,
    qui ne contiendrait ni l'utilisateur courant ni ses données, et ne
    simulerait donc pas fidèlement une vraie sauvegarde prise à cette
    époque."""
    old_db_path = tmp_path / f"old_schema_{revision}.db"
    shutil.copy2(stack.backups._db_path(), old_db_path)
    old_settings = dataclasses.replace(get_settings(), db_path=old_db_path)
    command.downgrade(_alembic_config(old_settings), revision)
    return old_db_path


def test_restore_from_an_older_ancestor_schema_version_auto_upgrades_to_head(login_as, tmp_path) -> None:
    """Scénario exact du mandat correctif (§3.10) : une sauvegarde plus
    ancienne mais compatible (révision 0017, juste avant l'ajout des
    tarifs vente/location en 0018 — migration purement additive, voir
    ``migrations/versions/0018_tarifs_vente_location.py``) doit être
    acceptée, puis le schéma mis à niveau automatiquement vers ``head`` —
    jamais refusée pour la seule raison qu'elle ne correspond pas
    exactement à la version actuelle. La restauration remplace bien le
    contenu (pas seulement le schéma) : un article créé après
    l'instantané disparaît, un article créé avant est conservé."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10,
    )
    article = _make_article(stack, stock_initial=Decimal("42"))
    old_db_path = _build_old_schema_db(stack, tmp_path, "0017")
    second_article = _make_article(stack, reference="ART-APRES-INSTANTANE", stock_initial=Decimal("5"))

    restore_result = stack.backups.restore_backup(old_db_path)

    assert restore_result.success is True
    script = ScriptDirectory.from_config(_alembic_config(get_settings()))
    assert backup_engine.get_alembic_version(stack.backups._db_path()) in script.get_heads()
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("42")
    with pytest.raises(NotFoundError):
        stack.articles.get_article(second_article.id)


def test_restore_rejects_a_schema_version_that_is_not_an_ancestor_of_head(login_as, tmp_path) -> None:
    """Toujours refusé : une version inconnue (ou plus récente que
    l'application actuelle) ne doit jamais être mise à niveau
    automatiquement — contrairement au cas ci-dessus."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))

    from app.models import Base

    incompatible = tmp_path / "incompatible_future.db"
    conn = sqlite3.connect(str(incompatible))
    for table in Base.metadata.sorted_tables:
        columns_sql = ", ".join(f'"{c.name}" TEXT' for c in table.columns) or "id INTEGER"
        conn.execute(f'CREATE TABLE "{table.name}" ({columns_sql})')
    conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32))")
    conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0099_version_future_inconnue')")
    conn.commit()
    conn.close()

    with pytest.raises(ValidationError):
        stack.backups.restore_backup(incompatible)

    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")


def test_restore_rolls_back_to_security_backup_when_schema_upgrade_fails(login_as, tmp_path, monkeypatch) -> None:
    """Si le fichier restauré est intact mais que la mise à niveau
    automatique du schéma vers ``head`` échoue (ex. migration qui lève une
    erreur), la base active ne doit jamais rester entre deux versions —
    elle doit être rétablie dans son état d'avant restauration grâce à la
    sauvegarde de sécurité, déjà à la version actuelle et connue bonne."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10,
    )
    article = _make_article(stack, stock_initial=Decimal("88"))
    old_db_path = _build_old_schema_db(stack, tmp_path, "0017")

    monkeypatch.setattr(
        "app.services.backups.backup_service.init_db.init_database",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("panne simulée pendant la mise à niveau du schéma")),
    )

    restore_result = stack.backups.restore_backup(old_db_path)

    assert restore_result.success is False
    assert "rétablie" in restore_result.message
    # Les données d'origine (avant la tentative de restauration) sont intactes.
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("88")


# -- audit --------------------------------------------------------------------------


def test_manual_backup_success_is_audited(login_as, tmp_path) -> None:
    stack, current_user = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)

    stack.backups.create_manual_backup()

    rows = _audit_rows("BACKUP_MANUAL_SUCCESS")
    assert len(rows) == 1
    assert rows[0].user_id == current_user.id
    assert rows[0].resultat == ResultatAudit.SUCCES


def test_manual_backup_failure_is_audited(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.backups.backup_engine.create_backup_file",
            lambda *a, **k: (_ for _ in ()).throw(OSError("erreur simulée")),
        )
        stack.backups.create_manual_backup()

    rows = _audit_rows("BACKUP_MANUAL_FAILURE")
    assert len(rows) == 1
    assert rows[0].resultat == ResultatAudit.ECHEC


def test_restore_attempt_is_traced_in_application_log(login_as, tmp_path, caplog) -> None:
    """L'événement « tentative » est tracé dans le journal applicatif, pas
    dans la table d'audit : une restauration réussie remplace la base
    entière — table d'audit comprise — par celle de la sauvegarde, ce qui
    effacerait systématiquement une ligne « tentative » écrite dans la base
    actuelle avant l'écrasement (voir docstring de ``BackupService.
    restore_backup``)."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    backup_result = stack.backups.create_manual_backup()

    import logging

    with caplog.at_level(logging.INFO, logger="stockmanager.services.backups"):
        stack.backups.restore_backup(backup_result.file_path)

    assert any("Tentative de restauration" in record.message for record in caplog.records)


def test_restore_success_is_durably_audited_in_the_restored_database(login_as, tmp_path) -> None:
    """Le résultat définitif (succès), lui, est écrit après coup dans la
    base désormais stabilisée : il survit donc bien à l'opération."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    backup_result = stack.backups.create_manual_backup()

    stack.backups.restore_backup(backup_result.file_path)

    assert len(_audit_rows("BACKUP_RESTORE_SUCCESS")) == 1


# -- planification ------------------------------------------------------------------


def test_scheduled_backup_does_nothing_when_disabled(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="00:00", destination=str(destination), retention=10)

    result = stack.backups.run_scheduled_backup_if_due()

    assert result is None


def test_scheduled_backup_runs_when_due(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=True, frequency="daily", time_of_day="00:00", destination=str(destination), retention=10)

    result = stack.backups.run_scheduled_backup_if_due()

    assert result is not None
    assert result.success is True


def test_scheduled_backup_does_not_run_twice_same_day(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=True, frequency="daily", time_of_day="00:00", destination=str(destination), retention=10)

    first = stack.backups.run_scheduled_backup_if_due()
    second = stack.backups.run_scheduled_backup_if_due()

    assert first is not None
    assert second is None


# -- Mission « Fiabilisation des sauvegardes automatiques » : backup.last_auto_run --
# n'est mis à jour que sur succès réel — un échec ou une archive invalide ne doit
# jamais empêcher une nouvelle tentative automatique le jour même.


def _read_last_auto_run(settings) -> str | None:
    from app.repositories.parameter_repository import ParameterRepository

    with session_scope(settings) as session:
        return ParameterRepository(session).get_value("backup.last_auto_run")


def test_scheduled_backup_success_updates_last_auto_run(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=True, frequency="daily", time_of_day="00:00", destination=str(destination), retention=10)

    result = stack.backups.run_scheduled_backup_if_due()

    assert result.success is True
    assert _read_last_auto_run(get_settings()) is not None


def test_scheduled_backup_failure_never_updates_last_auto_run(login_as, tmp_path, monkeypatch) -> None:
    """Correctif « Fiabilisation des sauvegardes automatiques », §1 : avant
    ce correctif, ``backup.last_auto_run`` était avancé même après un échec
    de création — empêchant toute nouvelle tentative automatique avant la
    prochaine échéance, sans qu'aucune archive n'existe pourtant pour le
    jour concerné."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=True, frequency="daily", time_of_day="00:00", destination=str(destination), retention=10)
    monkeypatch.setattr(
        backup_engine, "create_backup_file",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disque plein (simulé)")),
    )

    result = stack.backups.run_scheduled_backup_if_due()

    assert result.success is False
    assert _read_last_auto_run(get_settings()) is None


def test_scheduled_backup_invalid_archive_never_updates_last_auto_run(login_as, tmp_path, monkeypatch) -> None:
    """Même garantie que ci-dessus pour une archive créée mais déclarée
    invalide (échec de vérification) — scénario distinct d'une exception :
    ``_create_backup`` retourne un ``BackupResult(success=False, ...)``
    sans jamais lever, voir sa propre docstring."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=True, frequency="daily", time_of_day="00:00", destination=str(destination), retention=10)
    fake_invalid = backup_engine.BackupVerification(
        valid=False, integrity_ok=False, tables_ok=False, alembic_version=None,
        errors=["Intégrité SQLite invalide (simulée)."],
    )
    monkeypatch.setattr(backup_engine, "verify_backup_file", lambda path: fake_invalid)

    result = stack.backups.run_scheduled_backup_if_due()

    assert result.success is False
    assert _read_last_auto_run(get_settings()) is None


def test_scheduled_backup_retries_the_same_day_after_a_failure(login_as, tmp_path, monkeypatch) -> None:
    """Conséquence directe du correctif : puisque ``last_auto_run`` n'a pas
    avancé après un échec, un nouvel appel (prochain minuteur applicatif,
    ou prochain déclenchement de la tâche planifiée) retente la sauvegarde
    le jour même plutôt que d'attendre l'échéance suivante."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=True, frequency="daily", time_of_day="00:00", destination=str(destination), retention=10)
    monkeypatch.setattr(
        backup_engine, "create_backup_file",
        lambda *a, **k: (_ for _ in ()).throw(OSError("verrou transitoire (simulé)")),
    )

    first = stack.backups.run_scheduled_backup_if_due()
    assert first.success is False

    monkeypatch.undo()
    second = stack.backups.run_scheduled_backup_if_due()

    assert second is not None
    assert second.success is True
    assert _read_last_auto_run(get_settings()) is not None


def test_scheduled_backup_does_not_run_again_the_same_day_once_valid(login_as, tmp_path) -> None:
    """Pendant symétrique de la non-régression : une fois une sauvegarde du
    jour réellement réussie, aucune nouvelle tentative automatique
    (confirmé par taille d'historique, pas seulement par le retour
    ``None`` déjà couvert par ``test_scheduled_backup_does_not_run_twice_same_day``)."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=True, frequency="daily", time_of_day="00:00", destination=str(destination), retention=10)

    first = stack.backups.run_scheduled_backup_if_due()
    assert first.success is True
    entries_after_first = stack.backups.list_backups()

    second = stack.backups.run_scheduled_backup_if_due()

    assert second is None
    assert stack.backups.list_backups() == entries_after_first


# -- Mission « Sauvegarde automatique et restauration » : rétention par défaut,
# manifeste, chiffrement optionnel -------------------------------------------------


def test_default_retention_is_thirty(login_as) -> None:
    stack, _ = login_as("Administrateur")

    config = stack.backups.get_config()

    assert config.retention == 30


def test_default_encryption_is_disabled(login_as) -> None:
    stack, _ = login_as("Administrateur")

    config = stack.backups.get_config()

    assert config.encryption_enabled is False


def test_update_config_persists_encryption_enabled(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()

    updated = stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(tmp_path / "backups"), retention=30, encryption_enabled=True,
    )

    assert updated.encryption_enabled is True
    assert stack.backups.get_config().encryption_enabled is True


# -- mission corrective « Correction et validation sous Windows », point n°1 ---
# -- sécurité de la clé de chiffrement (empreinte persistée) -------------------


def _stored_fingerprint(settings):
    from app.repositories.parameter_repository import ParameterRepository

    with session_scope(settings) as session:
        return ParameterRepository(session).get_value("backup.encryption_key_fingerprint")


def test_activating_encryption_the_first_time_generates_a_key_and_stores_its_fingerprint(
    login_as, tmp_path
) -> None:
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    vault = _FakeEncryptionVault()
    stack.backups._encryption_vault = vault
    destination = tmp_path / "backups"

    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination),
        retention=10, encryption_enabled=True,
    )

    key = archive_encryption.require_existing_encryption_key(vault)
    assert _stored_fingerprint(get_settings()) == archive_encryption.fingerprint_of(key)


def test_activating_encryption_with_an_already_configured_key_never_regenerates_it(
    login_as, tmp_path
) -> None:
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    vault = _FakeEncryptionVault()
    stack.backups._encryption_vault = vault
    pre_existing_key = archive_encryption.ensure_encryption_key(vault)

    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"),
        retention=10, encryption_enabled=True,
    )

    assert archive_encryption.require_existing_encryption_key(vault) == pre_existing_key
    assert _stored_fingerprint(get_settings()) == archive_encryption.fingerprint_of(pre_existing_key)


def test_activating_encryption_refuses_to_generate_a_new_key_when_a_previous_one_is_known_lost(
    login_as, tmp_path
) -> None:
    """Scénario central de l'ajustement n°1 : la clé a existé sur ce poste
    (empreinte persistée), puis le coffre a été vidé/réinitialisé — jamais
    une nouvelle clé générée automatiquement dans ce cas, quel que soit le
    contenu (même vide) du dossier de destination actuellement configuré :
    les archives protégées par l'ancienne clé pourraient très bien avoir
    été déplacées ailleurs depuis."""
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination),
        retention=10, encryption_enabled=True,
    )
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination),
        retention=10, encryption_enabled=False,
    )
    # Simule un coffre réinitialisé (ex. changement d'ordinateur, profil
    # Windows recréé) : vide, alors que l'empreinte, elle, reste persistée
    # dans la base de données (jamais effacée par une simple désactivation
    # du chiffrement, voir ci-dessus).
    stack.backups._encryption_vault = _FakeEncryptionVault()

    with pytest.raises(ValidationError, match="déjà été utilisée"):
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination),
            retention=10, encryption_enabled=True,
        )
    # Refus explicite : jamais activé entre-temps.
    assert stack.backups.get_config().encryption_enabled is False


def test_activating_encryption_refuses_when_destination_already_holds_an_encrypted_archive(
    login_as, tmp_path
) -> None:
    """Défense en profondeur si l'empreinte elle-même a été perdue
    (ex. ligne supprimée manuellement de la table ``parametres``) : une
    archive déjà chiffrée visible dans le dossier de destination
    configuré doit, à elle seule, empêcher la génération automatique
    d'une nouvelle clé."""
    from app.services.backups import archive_manifest

    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    destination.mkdir()
    archive = destination / "stockmanager_backup_20200101_020000.db"
    archive.write_bytes(b"ancienne archive chiffree (contenu simule)")
    archive_manifest.write_manifest_for(
        archive, db_engine="sqlite", schema_version="0018",
        backup_type=archive_manifest.BACKUP_TYPE_LOCAL, encrypted=True,
    )
    stack.backups._encryption_vault = _FakeEncryptionVault()

    with pytest.raises(ValidationError, match="déjà été utilisée"):
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination),
            retention=10, encryption_enabled=True,
        )


def test_activating_encryption_fails_explicitly_when_the_vault_is_unavailable(login_as, tmp_path) -> None:
    from app.utils.exceptions import CredentialVaultUnavailableError

    class _UnavailableVault:
        def get_password(self, profile_id):
            raise CredentialVaultUnavailableError("coffre simulé indisponible")

        def set_password(self, profile_id, password):
            raise CredentialVaultUnavailableError("coffre simulé indisponible")

        def delete_password(self, profile_id):
            raise CredentialVaultUnavailableError("coffre simulé indisponible")

    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _UnavailableVault()

    with pytest.raises(ValidationError, match="coffre d'identifiants Windows"):
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"),
            retention=10, encryption_enabled=True,
        )
    assert stack.backups.get_config().encryption_enabled is False


def test_import_encryption_key_updates_the_stored_fingerprint(login_as, tmp_path) -> None:
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    old_vault = _FakeEncryptionVault()
    stack.backups._encryption_vault = old_vault
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"),
        retention=10, encryption_enabled=True,
    )
    transfer_file = tmp_path / "cle.json"
    stack.backups.export_encryption_key(str(transfer_file), "mot-de-passe-solide")

    new_vault = _FakeEncryptionVault()
    stack.backups._encryption_vault = new_vault
    stack.backups.import_encryption_key(str(transfer_file), "mot-de-passe-solide")

    imported_key = archive_encryption.require_existing_encryption_key(new_vault)
    assert _stored_fingerprint(get_settings()) == archive_encryption.fingerprint_of(imported_key)


class TestEncryptionStatus:
    """Mission corrective, §3.3/§5.4 : jamais confondre « chiffrement
    activé » (paramètre) et « clé réellement disponible » (coffre)."""

    def test_disabled_when_encryption_is_off(self, login_as) -> None:
        stack, _ = login_as("Administrateur")

        assert stack.backups.encryption_status() == "disabled"

    def test_ready_when_enabled_with_a_configured_key(self, login_as, tmp_path) -> None:
        stack, _ = login_as("Administrateur")
        stack.backups._encryption_vault = _FakeEncryptionVault()
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"),
            retention=10, encryption_enabled=True,
        )

        assert stack.backups.encryption_status() == "ready"

    def test_key_missing_when_enabled_but_vault_has_no_key(self, login_as, tmp_path, monkeypatch) -> None:
        stack, _ = login_as("Administrateur")
        stack.backups._encryption_vault = _FakeEncryptionVault()
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"),
            retention=10, encryption_enabled=True,
        )
        stack.backups._encryption_vault = _FakeEncryptionVault()  # coffre vidé après coup

        assert stack.backups.encryption_status() == "key_missing"

    def test_vault_unavailable_when_enabled_but_vault_raises(self, login_as, tmp_path) -> None:
        from app.utils.exceptions import CredentialVaultUnavailableError

        class _UnavailableVault:
            def get_password(self, profile_id):
                raise CredentialVaultUnavailableError("simulation")

            def set_password(self, profile_id, password):
                raise CredentialVaultUnavailableError("simulation")

            def delete_password(self, profile_id):
                raise CredentialVaultUnavailableError("simulation")

        stack, _ = login_as("Administrateur")
        stack.backups._encryption_vault = _FakeEncryptionVault()
        stack.backups.update_config(
            auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(tmp_path / "backups"),
            retention=10, encryption_enabled=True,
        )
        stack.backups._encryption_vault = _UnavailableVault()

        assert stack.backups.encryption_status() == "vault_unavailable"

    def test_requires_view_permission(self, login_as) -> None:
        stack, _ = login_as("Vendeur")

        with pytest.raises(PermissionDeniedError):
            stack.backups.encryption_status()


def test_create_manual_backup_writes_a_manifest(login_as, tmp_path) -> None:
    from app.services.backups import archive_manifest

    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=30)

    result = stack.backups.create_manual_backup()

    manifest = archive_manifest.read_manifest_for(result.file_path)
    assert manifest is not None
    assert manifest.db_engine == "sqlite"
    assert manifest.backup_type == archive_manifest.BACKUP_TYPE_LOCAL
    assert manifest.encrypted is False
    assert manifest.sha256 == archive_manifest.compute_sha256(result.file_path)


def test_rotation_also_deletes_the_manifest_of_removed_backups(login_as, tmp_path) -> None:
    from app.services.backups import archive_manifest

    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=1)

    first = stack.backups.create_manual_backup()
    time.sleep(1.1)  # noms de fichiers à la seconde près : garantit un second nom distinct
    stack.backups.create_manual_backup()

    assert not first.file_path.exists()
    assert not archive_manifest.manifest_path_for(first.file_path).exists()


def test_encrypted_backup_round_trips_through_restore(login_as, tmp_path) -> None:
    """Bout en bout avec chiffrement activé : la sauvegarde créée est bien
    chiffrée sur le disque (illisible tel quel par sqlite3), mais la
    restauration — qui doit déchiffrer avant de lire — réussit et restitue
    exactement les données d'origine."""
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    article = _make_article(stack, stock_initial=Decimal("77"))
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=30, encryption_enabled=True,
    )

    result = stack.backups.create_manual_backup()
    assert result.success is True

    # L'archive chiffrée n'est pas une base SQLite exploitable telle quelle.
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(f"file:{result.file_path.as_posix()}?mode=ro", uri=True).execute(
            "SELECT 1 FROM sqlite_master LIMIT 1;"
        ).fetchall()

    restore_result = stack.backups.restore_backup(result.file_path)

    assert restore_result.success is True
    with session_scope(get_settings()) as session:
        from app.models.catalog import Article

        restored = session.get(Article, article.id)
        assert restored.stock_actuel == Decimal("77")


def test_verify_backup_file_succeeds_on_encrypted_archive(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=30, encryption_enabled=True,
    )

    result = stack.backups.create_manual_backup()

    verification = stack.backups.verify_backup_file(result.file_path)

    assert verification.valid is True


# -- mission « Audit, correction et fiabilisation du système de sauvegarde », §10 --
# incident réel du 26/11/2026 : ``verification.errors`` calculé puis jamais lu par
# l'interface, et aucune détection d'une archive modifiée après une création valide
# pour les archives non chiffrées (la comparaison d'empreinte n'existait jusque-là
# que pour les archives chiffrées, voir ``_resolve_plaintext_path``).


def test_describe_backup_status_reports_valid_with_no_errors(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=30)
    result = stack.backups.create_manual_backup()

    report = stack.backups.describe_backup_status(result.file_path)

    assert report.valid is True
    assert report.label == "Valide"
    assert report.errors == []
    assert report.manifest_present is True
    assert report.manifest_hash_matches is True


def test_describe_backup_status_detects_unencrypted_archive_altered_after_creation(login_as, tmp_path) -> None:
    """Avant ce correctif, une archive NON chiffrée modifiée après coup
    n'était jamais détectée par ``verify_backup_file`` (seul le cas
    chiffré comparait l'empreinte) — elle pouvait rester « Valide » tant
    que sa structure restait lisible, ou échouer sans qu'on puisse
    distinguer une altération d'une corruption d'origine."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=30)
    result = stack.backups.create_manual_backup()

    with result.file_path.open("ab") as handle:
        handle.write(b"donnees ajoutees apres la creation")

    report = stack.backups.describe_backup_status(result.file_path)

    assert report.valid is False
    assert report.label == "Invalide"
    assert report.manifest_hash_matches is False
    assert any("changé depuis sa création" in error for error in report.errors)


def test_describe_backup_status_never_declares_a_manifestless_archive_corrupted_on_that_basis_alone(
    login_as, tmp_path
) -> None:
    """§4 du mandat, « compatibilité avec les anciennes archives » : une
    sauvegarde antérieure au mécanisme de manifeste, structurellement
    saine, reste « Valide » — l'absence de manifeste seule ne doit jamais
    la faire basculer en « Invalide »."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=30)
    result = stack.backups.create_manual_backup()
    archive_manifest.delete_manifest_for(result.file_path)

    report = stack.backups.describe_backup_status(result.file_path)

    assert report.valid is True
    assert report.label == "Valide"
    assert report.manifest_present is False


def test_describe_backup_status_reports_unverifiable_when_hash_unchanged_but_recheck_fails(
    login_as, tmp_path, monkeypatch
) -> None:
    """Reproduit précisément l'incident du 26/11/2026 : une archive dont
    l'empreinte PROUVE qu'elle n'a pas changé depuis une création jugée
    valide ne doit jamais être présentée comme « Invalide » (ce serait
    affirmer une corruption sans preuve technique) si la revérification
    structurelle échoue plus tard — seulement comme « Intégrité non
    vérifiable », avec le détail complet."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=30)
    result = stack.backups.create_manual_backup()

    fake_failure = backup_engine.BackupVerification(
        valid=False, integrity_ok=False, tables_ok=False, alembic_version=None,
        errors=["pg_restore introuvable avec cette version locale."],
    )
    monkeypatch.setattr(backup_engine, "verify_backup_file", lambda path: fake_failure)

    report = stack.backups.describe_backup_status(result.file_path)

    assert report.valid is False
    assert report.label == "Intégrité non vérifiable"
    assert report.manifest_hash_matches is True
    assert any("pg_restore introuvable" in error for error in report.errors)
    assert any("l'archive elle-même n'a donc pas changé" in error for error in report.errors)


def test_describe_backup_status_detects_encrypted_archive_altered_after_creation(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=30, encryption_enabled=True,
    )
    result = stack.backups.create_manual_backup()

    with result.file_path.open("ab") as handle:
        handle.write(b"donnees ajoutees apres chiffrement")

    report = stack.backups.describe_backup_status(result.file_path)

    assert report.valid is False
    assert report.label == "Invalide"
    assert report.manifest_hash_matches is False


def test_describe_backup_status_reports_valid_for_an_intact_encrypted_archive(login_as, tmp_path) -> None:
    """Confirme que le correctif du 28/11/2026 (voir ci-dessous) ne change
    rien au cas normal : une archive chiffrée intacte, dont l'empreinte et
    la vérification structurelle réussissent toutes les deux, reste
    « Valide » — une empreinte correcte ne suffit jamais seule (elle
    n'est ici qu'une des deux conditions)."""
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=30, encryption_enabled=True,
    )
    result = stack.backups.create_manual_backup()

    report = stack.backups.describe_backup_status(result.file_path)

    assert report.valid is True
    assert report.label == "Valide"
    assert report.errors == []
    assert report.manifest_present is True
    assert report.manifest_hash_matches is True


def test_describe_backup_status_reports_unverifiable_for_encrypted_archive_when_hash_unchanged_but_recheck_fails(
    login_as, tmp_path, monkeypatch
) -> None:
    """Correctif du 28/11/2026 : reproduit l'audit qui a montré que
    ``manifest_hash_matches`` restait toujours ``None`` pour une archive
    CHIFFRÉE (la condition ne calculait cette comparaison que pour les
    archives en clair), si bien qu'une archive chiffrée intacte dont la
    revérification structurelle échouait plus tard était annoncée
    « Invalide » au lieu de « Intégrité non vérifiable » — alors que
    cette même empreinte est pourtant bien vérifiée, avant tout
    déchiffrement, par ``_resolve_plaintext_path``. Mirroir exact de
    ``test_describe_backup_status_reports_unverifiable_when_hash_unchanged_but_recheck_fails``
    pour une archive chiffrée : c'est la régression directe du défaut
    corrigé."""
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=30, encryption_enabled=True,
    )
    result = stack.backups.create_manual_backup()

    fake_failure = backup_engine.BackupVerification(
        valid=False, integrity_ok=False, tables_ok=False, alembic_version=None,
        errors=["pg_restore introuvable avec cette version locale."],
    )
    monkeypatch.setattr(backup_engine, "verify_backup_file", lambda path: fake_failure)

    report = stack.backups.describe_backup_status(result.file_path)

    assert report.valid is False
    assert report.label == "Intégrité non vérifiable"
    assert report.manifest_hash_matches is True
    assert any("pg_restore introuvable" in error for error in report.errors)
    assert any("l'archive elle-même n'a donc pas changé" in error for error in report.errors)


def test_describe_backup_status_never_declares_valid_from_hash_alone_when_structure_fails_and_hash_is_wrong(
    login_as, tmp_path
) -> None:
    """Exigence explicite du mandat correctif (§2) : une empreinte
    correcte ne doit jamais, à elle seule, faire passer une archive pour
    « Valide » ; symétriquement, une empreinte incorrecte reste
    « Invalide » même si on ne tente jamais de vérification structurelle
    (celle-ci n'est alors pas pertinente, le défaut étant déjà prouvé par
    l'empreinte seule) — jamais confondue avec « Intégrité non
    vérifiable »."""
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=30, encryption_enabled=True,
    )
    result = stack.backups.create_manual_backup()
    with result.file_path.open("ab") as handle:
        handle.write(b"donnees ajoutees apres chiffrement")

    report = stack.backups.describe_backup_status(result.file_path)

    assert report.valid is False
    assert report.label == "Invalide"
    assert report.manifest_hash_matches is False


def test_describe_backup_status_propagates_missing_encryption_key_distinctly(login_as, tmp_path) -> None:
    """§5 du mandat correctif : une clé de chiffrement absente sur ce
    poste doit rester identifiable comme telle (jamais reclassée en
    « Invalide » ou « Intégrité non vérifiable », qui laisseraient croire
    à un problème avec l'archive elle-même plutôt qu'avec le poste) —
    ``NoEncryptionKeyConfiguredError`` n'est jamais intercepté par
    ``describe_backup_status``, qui ne gère que ``ValidationError``."""
    from app.services.backups.archive_encryption import NoEncryptionKeyConfiguredError

    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=30, encryption_enabled=True,
    )
    result = stack.backups.create_manual_backup()
    # Simule un autre poste, ou une clé perdue : le coffre ne contient plus
    # aucune clé (jamais régénérée automatiquement, voir §6 du mandat).
    stack.backups._encryption_vault = _FakeEncryptionVault()

    with pytest.raises(NoEncryptionKeyConfiguredError):
        stack.backups.describe_backup_status(result.file_path)


def test_describe_backup_status_propagates_decryption_error_distinctly(login_as, tmp_path) -> None:
    """§5 du mandat correctif : un jeton qui ne se déchiffre pas avec la
    clé localement configurée (mauvaise clé) doit rester une erreur de
    déchiffrement, jamais reclassée en « Invalide » (qui impliquerait une
    archive prouvée altérée par son empreinte, ce qui n'est pas le cas
    ici) ni en « Intégrité non vérifiable » — ``ArchiveEncryptionError``
    n'est jamais intercepté par ``describe_backup_status``."""
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00",
        destination=str(destination), retention=30, encryption_enabled=True,
    )
    result = stack.backups.create_manual_backup()
    # Simule une clé différente configurée sur ce poste (jamais régénérée
    # automatiquement) : le jeton existant ne lui correspond plus.
    wrong_key_vault = _FakeEncryptionVault()
    archive_encryption.ensure_encryption_key(wrong_key_vault)
    stack.backups._encryption_vault = wrong_key_vault

    with pytest.raises(archive_encryption.ArchiveEncryptionError):
        stack.backups.describe_backup_status(result.file_path)


# -- mission corrective §3.2/§3.9 : restauration atomique --------------------------


def test_restore_reports_recovered_path_and_keeps_current_data_when_replace_fails(login_as, tmp_path) -> None:
    """Simule l'échec du seul remplacement final (ex. verrou Windows
    transitoire) — en substituant directement l'appel de plus haut niveau
    (``backup_engine.restore_database_from_backup``), jamais
    ``os.replace`` globalement, qui affecterait aussi la création de la
    sauvegarde de sécurité préalable (celle-ci utilise désormais, elle
    aussi, un remplacement atomique — voir backup_engine.create_backup_file)
    et fausserait ce scénario. Le comportement précis de la nouvelle
    tentative/du remplacement atomique lui-même est déjà testé
    indépendamment dans tests/test_backup_engine.py."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    article = _make_article(stack, stock_initial=Decimal("77"))
    backup_result = stack.backups.create_manual_backup()

    recovered_path = tmp_path / ".stockmanager.db_restore_abcdef.tmp"
    recovered_path.write_text("copie déjà vérifiée")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.backups.backup_engine.restore_database_from_backup",
            lambda *a, **k: (_ for _ in ()).throw(
                backup_engine.AtomicReplaceError("verrou Windows simulé", recovered_path=recovered_path)
            ),
        )
        restore_result = stack.backups.restore_backup(backup_result.file_path)

    assert restore_result.success is False
    assert "n'a pas été modifiée" in restore_result.message
    # Le chemin de la copie déjà vérifiée est communiqué à l'utilisateur.
    assert str(recovered_path) in restore_result.message
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("77")
    rows = _audit_rows("BACKUP_RESTORE_FAILURE")
    assert len(rows) == 1


def test_restore_never_touches_active_database_when_internal_copy_verification_fails(login_as, tmp_path) -> None:
    """Simule l'échec interne de vérification d'intégrité pendant la copie
    de restauration elle-même (voir
    ``backup_engine.restore_database_from_backup``, qui lève
    ``RestoreValidationError`` dans ce cas, jamais un remplacement de la
    base active) — distinct de la validation initiale de l'archive source,
    déjà couverte par ``test_restore_backup_rejects_invalid_file``."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    article = _make_article(stack, stock_initial=Decimal("88"))
    backup_result = stack.backups.create_manual_backup()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.backups.backup_engine.restore_database_from_backup",
            lambda *a, **k: (_ for _ in ()).throw(
                backup_engine.RestoreValidationError("corruption simulée pendant la copie de restauration")
            ),
        )
        restore_result = stack.backups.restore_backup(backup_result.file_path)

    assert restore_result.success is False
    assert "n'a pas été modifiée" in restore_result.message
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("88")


# -- mission corrective §3.1 : transfert de la clé de chiffrement -----------------


def test_has_encryption_key_configured_false_by_default(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()

    assert stack.backups.has_encryption_key_configured() is False


def test_has_encryption_key_configured_true_after_a_key_exists(login_as) -> None:
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    vault = _FakeEncryptionVault()
    stack.backups._encryption_vault = vault
    archive_encryption.ensure_encryption_key(vault)

    assert stack.backups.has_encryption_key_configured() is True


def test_export_encryption_key_requires_permission(login_as, tmp_path) -> None:
    stack, _ = login_as("Vendeur")
    stack.backups._encryption_vault = _FakeEncryptionVault()

    with pytest.raises(PermissionDeniedError):
        stack.backups.export_encryption_key(tmp_path / "cle.json", "mot-de-passe")


def test_export_encryption_key_without_any_key_raises(login_as, tmp_path) -> None:
    from app.services.backups.archive_encryption import NoEncryptionKeyConfiguredError

    stack, _ = login_as("Administrateur")
    stack.backups._encryption_vault = _FakeEncryptionVault()

    with pytest.raises(NoEncryptionKeyConfiguredError):
        stack.backups.export_encryption_key(tmp_path / "cle.json", "mot-de-passe")

    rows = _audit_rows("BACKUP_ENCRYPTION_KEY_EXPORT_FAILURE")
    assert len(rows) == 1


def test_export_encryption_key_refuses_the_configured_backup_destination(login_as, tmp_path) -> None:
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10)
    vault = _FakeEncryptionVault()
    stack.backups._encryption_vault = vault
    archive_encryption.ensure_encryption_key(vault)

    with pytest.raises(archive_encryption.KeyTransferError):
        stack.backups.export_encryption_key(destination / "cle.json", "mot-de-passe")


def test_export_encryption_key_success_is_audited(login_as, tmp_path) -> None:
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    vault = _FakeEncryptionVault()
    stack.backups._encryption_vault = vault
    archive_encryption.ensure_encryption_key(vault)
    transfer_file = tmp_path / "cle.json"

    stack.backups.export_encryption_key(transfer_file, "mot-de-passe")

    assert transfer_file.exists()
    rows = _audit_rows("BACKUP_ENCRYPTION_KEY_EXPORT_SUCCESS")
    assert len(rows) == 1


def test_import_encryption_key_requires_permission(login_as, tmp_path) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.backups.import_encryption_key(tmp_path / "cle.json", "mot-de-passe")


def test_export_then_import_round_trip_allows_decrypting_on_a_second_vault(login_as, tmp_path) -> None:
    """Scénario central du mandat correctif, au niveau du service : une
    archive chiffrée avec la clé du premier coffre reste déchiffrable
    après export/import vers un second coffre totalement vide (simule un
    second ordinateur)."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups._encryption_vault = _FakeEncryptionVault()
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination),
        retention=10, encryption_enabled=True,
    )
    backup_result = stack.backups.create_manual_backup()
    assert backup_result.success is True

    transfer_file = tmp_path / "cle_de_transfert.json"
    stack.backups.export_encryption_key(transfer_file, "mot-de-passe-du-transfert")

    new_computer_vault = _FakeEncryptionVault()
    stack.backups._encryption_vault = new_computer_vault
    stack.backups.import_encryption_key(transfer_file, "mot-de-passe-du-transfert")

    assert stack.backups.test_encryption_key_against_archive(backup_result.file_path) is True


def test_import_encryption_key_without_confirmation_refuses_to_overwrite(login_as, tmp_path) -> None:
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    old_vault = _FakeEncryptionVault()
    archive_encryption.ensure_encryption_key(old_vault)
    stack.backups._encryption_vault = old_vault
    transfer_file = tmp_path / "cle.json"
    stack.backups.export_encryption_key(transfer_file, "mot-de-passe")

    destination_vault = _FakeEncryptionVault()
    archive_encryption.ensure_encryption_key(destination_vault)  # une clé existe déjà ici
    stack.backups._encryption_vault = destination_vault

    with pytest.raises(archive_encryption.EncryptionKeyAlreadyConfiguredError):
        stack.backups.import_encryption_key(transfer_file, "mot-de-passe")

    rows = _audit_rows("BACKUP_ENCRYPTION_KEY_IMPORT_FAILURE")
    assert len(rows) == 1


def test_import_encryption_key_overwrite_confirmed_is_audited(login_as, tmp_path) -> None:
    from app.services.backups import archive_encryption

    stack, _ = login_as("Administrateur")
    old_vault = _FakeEncryptionVault()
    archive_encryption.ensure_encryption_key(old_vault)
    stack.backups._encryption_vault = old_vault
    transfer_file = tmp_path / "cle.json"
    stack.backups.export_encryption_key(transfer_file, "mot-de-passe")

    destination_vault = _FakeEncryptionVault()
    archive_encryption.ensure_encryption_key(destination_vault)
    stack.backups._encryption_vault = destination_vault

    stack.backups.import_encryption_key(transfer_file, "mot-de-passe", overwrite=True)

    rows = _audit_rows("BACKUP_ENCRYPTION_KEY_IMPORT_SUCCESS")
    assert len(rows) == 1


def test_test_encryption_key_against_archive_only_requires_view_permission(login_as, tmp_path) -> None:
    from app.services.backups import archive_encryption

    admin_stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    vault = _FakeEncryptionVault()
    admin_stack.backups._encryption_vault = vault
    admin_stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination),
        retention=10, encryption_enabled=True,
    )
    backup_result = admin_stack.backups.create_manual_backup()

    consultation_stack, _ = login_as("Consultation")
    consultation_stack.backups._encryption_vault = vault

    assert consultation_stack.backups.test_encryption_key_against_archive(backup_result.file_path) is True


# -- mission corrective §3.4/§3.8 : rattrapage + heure par défaut 20:00 ----------


def test_default_time_of_day_is_twenty_hundred(login_as) -> None:
    stack, _ = login_as("Administrateur")

    config = stack.backups.get_config()

    assert config.time_of_day == "20:00"


def test_update_config_preserves_an_already_configured_time(login_as, tmp_path) -> None:
    """Le changement de valeur par défaut ne doit jamais écraser une
    valeur déjà explicitement enregistrée (même garde que pour la
    rétention — voir ``_read_config``)."""
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="03:15",
        destination=str(tmp_path / "backups"), retention=10,
    )

    assert stack.backups.get_config().time_of_day == "03:15"


def _set_last_auto_run(stack, when) -> None:
    from app.db.session import session_scope
    from app.repositories.parameter_repository import ParameterRepository

    with session_scope(stack.settings) as session:
        ParameterRepository(session).set_value("backup.last_auto_run", when.isoformat())


def test_catchup_triggers_immediately_when_a_full_day_was_missed(login_as, tmp_path) -> None:
    """Scénario du mandat correctif : heure configurée 20h, une sauvegarde
    a réussi il y a deux jours (donc la veille a été entièrement manquée —
    ordinateur éteint à 20h), et on interroge maintenant à 08h (bien avant
    l'heure cible du jour) : la sauvegarde doit être considérée due
    immédiatement, sans attendre 20h aujourd'hui."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="20:00", destination=str(destination), retention=10,
    )
    two_days_ago = datetime(2026, 1, 1, 20, 5, 0)
    _set_last_auto_run(stack, two_days_ago)
    config = stack.backups.get_config()

    now = datetime(2026, 1, 3, 8, 0, 0)  # le lendemain du jour manqué, 8h du matin
    assert stack.backups._is_due(config, now) is True


def test_catchup_does_not_trigger_the_normal_day_before_target_time(login_as, tmp_path) -> None:
    """Cas normal, non manqué : la dernière sauvegarde réussie date d'hier
    — pas de rattrapage, on attend bien l'heure cible d'aujourd'hui comme
    avant ce correctif."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="20:00", destination=str(destination), retention=10,
    )
    yesterday = datetime(2026, 1, 1, 20, 5, 0)
    _set_last_auto_run(stack, yesterday)
    config = stack.backups.get_config()

    now = datetime(2026, 1, 2, 8, 0, 0)  # le jour suivant, mais avant 20h — rien manqué encore.
    assert stack.backups._is_due(config, now) is False


def test_catchup_never_triggers_for_a_never_run_backup(login_as, tmp_path) -> None:
    """Jamais de rattrapage pour une toute première sauvegarde : une
    installation qui vient d'activer la sauvegarde automatique doit
    attendre la première heure cible, pas un déclenchement immédiat et
    inattendu."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="20:00", destination=str(destination), retention=10,
    )
    config = stack.backups.get_config()

    now = datetime(2026, 1, 1, 8, 0, 0)
    assert stack.backups._is_due(config, now) is False


def test_catchup_runs_only_once_even_when_queried_repeatedly_before_target_time(login_as, tmp_path) -> None:
    """Évite les sauvegardes automatiques inutiles (§3.4) : une fois le
    rattrapage effectué, une nouvelle interrogation le même jour (toujours
    avant l'heure cible) ne doit plus déclencher de seconde sauvegarde."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="20:00", destination=str(destination), retention=10,
    )
    _set_last_auto_run(stack, datetime(2026, 1, 1, 20, 5, 0))

    first_result = stack.backups.run_scheduled_backup_if_due()
    assert first_result is not None
    assert first_result.success is True

    config = stack.backups.get_config()
    second_check = stack.backups._is_due(config, datetime(2026, 1, 3, 9, 0, 0))
    assert second_check is False


def test_catchup_also_works_for_weekly_frequency(login_as, tmp_path) -> None:
    """Mission « Gestion complète de la planification des sauvegardes
    Windows » : l'échéance hebdomadaire est désormais consciente du jour
    réellement configuré (jeudi, ``weekday() == 3``), jamais un simple
    compteur de 7 jours — 2026-01-01 et 2026-01-08 sont tous deux des
    jeudis. La dernière réussite datant du jeudi 1er, l'échéance du jeudi
    8 (dépassée hier) déclenche un rattrapage immédiat le 10, bien avant
    l'heure cible."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=True, frequency="weekly", time_of_day="20:00", destination=str(destination), retention=10,
        weekly_days=frozenset({3}),
    )
    _set_last_auto_run(stack, datetime(2026, 1, 1, 20, 5, 0))
    config = stack.backups.get_config()

    now = datetime(2026, 1, 10, 8, 0, 0)  # samedi, après le jeudi 8 manqué
    assert stack.backups._is_due(config, now) is True


class TestMostRecentScheduledDate:
    """Mission « Gestion complète de la planification des sauvegardes
    Windows », §12 : calcul pur de l'échéance la plus récente — hebdomadaire
    multi-jours, mensuel jour fixe (y compris mois courts), mensuel dernier
    jour (y compris années bissextiles). Jamais un décalage silencieux :
    un jour du mois absent d'un mois donné est simplement sauté vers le
    mois précédent, jamais reporté à un autre jour du même mois."""

    @staticmethod
    def _config(**overrides):
        from app.services.backups.backup_service import BackupConfig

        base = dict(
            auto_enabled=True, frequency="daily", time_of_day="20:00",
            destination=Path("/tmp/backups"), retention=10,
        )
        base.update(overrides)
        return BackupConfig(**base)

    def test_daily_returns_the_reference_date_itself(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="daily")
        assert _most_recent_scheduled_date(config, date(2026, 3, 15)) == date(2026, 3, 15)

    def test_weekly_single_day_finds_the_most_recent_occurrence(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="weekly", weekly_days=frozenset({3}))  # jeudi
        # 2026-03-15 est un dimanche ; le jeudi précédent est le 2026-03-12.
        assert _most_recent_scheduled_date(config, date(2026, 3, 15)) == date(2026, 3, 12)

    def test_weekly_multiple_days_finds_the_closer_of_the_two(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="weekly", weekly_days=frozenset({0, 3}))  # lundi, jeudi
        # 2026-03-15 (dimanche) : le lundi 2026-03-09 et le jeudi 2026-03-12
        # ont tous deux eu lieu dans la semaine précédente — le jeudi (12)
        # est le plus récent des deux.
        assert _most_recent_scheduled_date(config, date(2026, 3, 15)) == date(2026, 3, 12)

    def test_weekly_occurrence_on_the_reference_date_itself(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="weekly", weekly_days=frozenset({6}))  # dimanche
        assert _most_recent_scheduled_date(config, date(2026, 3, 15)) == date(2026, 3, 15)

    def test_monthly_fixed_day_within_the_same_month(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_day=15)
        assert _most_recent_scheduled_date(config, date(2026, 3, 20)) == date(2026, 3, 15)

    def test_monthly_fixed_day_not_yet_reached_falls_back_to_previous_month(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_day=20)
        assert _most_recent_scheduled_date(config, date(2026, 3, 10)) == date(2026, 2, 20)

    def test_monthly_fixed_day_31_skips_a_thirty_day_month(self) -> None:
        """Avril compte 30 jours : le jour 31 n'y existe jamais, jamais
        reporté au 30 — l'occurrence la plus récente avant le 15 avril est
        donc celle de mars."""
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_day=31)
        assert _most_recent_scheduled_date(config, date(2026, 4, 15)) == date(2026, 3, 31)

    def test_monthly_fixed_day_29_skips_february_in_a_non_leap_year(self) -> None:
        """2026 n'est pas bissextile (février compte 28 jours) : le jour 29
        n'y existe pas, jamais reporté au 28 — l'occurrence la plus récente
        avant le 10 mars est celle de janvier."""
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_day=29)
        assert _most_recent_scheduled_date(config, date(2026, 3, 10)) == date(2026, 1, 29)

    def test_monthly_fixed_day_29_exists_in_a_leap_year_february(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_day=29)
        assert _most_recent_scheduled_date(config, date(2028, 3, 10)) == date(2028, 2, 29)  # 2028 est bissextile.

    def test_monthly_last_day_of_a_thirty_one_day_month(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_last_day=True)
        assert _most_recent_scheduled_date(config, date(2026, 1, 20)) == date(2025, 12, 31)

    def test_monthly_last_day_of_february_in_a_leap_year(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_last_day=True)
        assert _most_recent_scheduled_date(config, date(2028, 3, 10)) == date(2028, 2, 29)

    def test_monthly_last_day_of_february_in_a_non_leap_year(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_last_day=True)
        assert _most_recent_scheduled_date(config, date(2026, 3, 10)) == date(2026, 2, 28)

    def test_monthly_last_day_matching_the_reference_date_itself(self) -> None:
        from app.services.backups.backup_service import _most_recent_scheduled_date

        config = self._config(frequency="monthly", monthly_last_day=True)
        assert _most_recent_scheduled_date(config, date(2026, 4, 30)) == date(2026, 4, 30)


def test_is_due_as_of_monthly_fixed_day_due_after_the_occurrence(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=True, frequency="monthly", time_of_day="20:00", destination=str(destination),
        retention=10, monthly_day=15,
    )
    config = stack.backups.get_config()

    assert stack.backups._is_due_as_of(config, datetime(2026, 2, 15, 20, 5, 0), date(2026, 3, 16)) is True
    assert stack.backups._is_due_as_of(config, datetime(2026, 3, 15, 20, 5, 0), date(2026, 3, 16)) is False


def test_is_due_as_of_monthly_last_day_never_shifts_to_another_day(login_as, tmp_path) -> None:
    """Mission §3.1/§12 : vérifie bout en bout (via ``update_config`` puis
    ``_is_due_as_of``, pas seulement la fonction pure ci-dessus) qu'une
    fréquence mensuelle « dernier jour » ne décale jamais silencieusement
    vers un autre jour selon le mois."""
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=True, frequency="monthly", time_of_day="20:00", destination=str(destination),
        retention=10, monthly_last_day=True,
    )
    config = stack.backups.get_config()

    # Dernière réussite le 28 février 2026 (dernier jour de ce mois-là,
    # 2026 n'étant pas bissextile) : le 31 mars 2026 (dernier jour de mars)
    # rend une nouvelle sauvegarde due.
    assert stack.backups._is_due_as_of(config, datetime(2026, 2, 28, 20, 5, 0), date(2026, 4, 1)) is True
