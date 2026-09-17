"""Vérifie que la sauvegarde planifiée fonctionne sans utilisateur connecté
(exécution système, ex. Planificateur de tâches), scénario spécifique à
``app/backup_cli.py`` — voir §8 du cahier des charges de la phase Sauvegardes.

La configuration (qui exige la permission BACKUP_CREATE) est mise en place
via une session administrateur normale (``login_as``) ; c'est ensuite une
toute nouvelle instance de ``BackupService``, sans aucun utilisateur
connecté (``PermissionService.current_user is None``, exactement comme
depuis ``app/backup_cli.py``), qui déclenche la sauvegarde planifiée —
laquelle ne vérifie volontairement aucune permission."""
from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.services.backups.backup_service import BackupService


def test_run_scheduled_backup_if_due_works_without_logged_in_user(login_as, initialized_db: Settings, tmp_path) -> None:
    destination = tmp_path / "backups"
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(destination), retention=5,
    )

    unattended_permissions = PermissionService(AuthService(initialized_db))
    unattended_service = BackupService(unattended_permissions, settings=initialized_db)
    assert unattended_permissions.current_user is None  # aucune session, comme depuis backup_cli.py

    result = unattended_service.run_scheduled_backup_if_due()

    assert result is not None
    assert result.success is True
    assert result.file_path.exists()


def test_scheduled_backup_audit_has_null_user_id_when_unattended(login_as, initialized_db: Settings, tmp_path) -> None:
    destination = tmp_path / "backups"
    stack, _ = login_as("Administrateur")
    stack.backups.update_config(
        auto_enabled=True, frequency="daily", time_of_day="00:00",
        destination=str(destination), retention=5,
    )

    unattended_service = BackupService(PermissionService(AuthService(initialized_db)), settings=initialized_db)
    unattended_service.run_scheduled_backup_if_due()

    with session_scope(initialized_db) as session:
        rows = session.query(AuditLog).filter_by(action="BACKUP_AUTO_SUCCESS").all()
        assert len(rows) == 1
        assert rows[0].user_id is None
