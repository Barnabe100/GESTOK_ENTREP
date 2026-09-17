import sqlite3
import time
from decimal import Decimal

import pytest

from app.config.settings import get_settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.services.backups import backup_engine
from app.utils.exceptions import PermissionDeniedError, ValidationError


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


def test_get_config_returns_safe_defaults(login_as) -> None:
    stack, _ = login_as("Administrateur")

    config = stack.backups.get_config()

    assert config.auto_enabled is False
    assert config.retention >= 1


def test_update_config_persists_values(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"

    updated = stack.backups.update_config(
        auto_enabled=True, frequency="weekly", time_of_day="03:30",
        destination=str(destination), retention=5,
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
            auto_enabled=False, frequency="monthly", time_of_day="02:00",
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


