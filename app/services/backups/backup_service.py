"""Orchestration des sauvegardes/restaurations : permissions, configuration
(stockée dans la table ``parametres`` existante), audit (journal d'audit
existant), rotation, sauvegarde de sécurité avant restauration.

Toute la mécanique de fichiers (création/vérification/rotation/restauration
SQLite) vit dans :mod:`app.services.backups.backup_engine`, réutilisée telle
quelle ici — ce module ne fait qu'orchestrer : vérifier les permissions,
lire/écrire la configuration, appeler le moteur, auditer le résultat.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, time as time_type
from pathlib import Path
from typing import Optional

from app.config.settings import Settings, get_settings
from app.db import session as db_session_module
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.repositories.parameter_repository import ParameterRepository
from app.services.auth.permission_service import PermissionService
from app.services.backups import backup_engine
from app.utils.exceptions import ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.backups")

_KEY_AUTO_ENABLED = "backup.auto_enabled"
_KEY_FREQUENCY = "backup.frequency"
_KEY_TIME = "backup.time"
_KEY_DESTINATION = "backup.destination"
_KEY_RETENTION = "backup.retention"
_KEY_LAST_AUTO_RUN = "backup.last_auto_run"

FREQUENCY_DAILY = "daily"
FREQUENCY_WEEKLY = "weekly"
_VALID_FREQUENCIES = {FREQUENCY_DAILY, FREQUENCY_WEEKLY}

# Valeurs par défaut sûres (§14) : sauvegarde automatique désactivée tant
# qu'un administrateur ne l'a pas explicitement activée, rétention modérée.
_DEFAULT_FREQUENCY = FREQUENCY_DAILY
_DEFAULT_TIME = "02:00"
_DEFAULT_RETENTION = 10

# Erreurs anticipées d'accès fichier/SQLite — jamais une exception large
# masquant un bug ailleurs dans le moteur.
_BACKUP_IO_ERRORS = (OSError, sqlite3.Error)


def _default_destination(settings: Settings) -> Path:
    return settings.data_dir / "backups"


def _parse_time_of_day(text: str) -> time_type:
    try:
        hour_str, minute_str = text.split(":")
        return time_type(int(hour_str), int(minute_str))
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"Heure invalide : « {text} » (format attendu HH:MM).") from exc


@dataclass(frozen=True)
class BackupConfig:
    """Configuration des sauvegardes, persistée dans ``parametres``."""

    auto_enabled: bool
    frequency: str
    time_of_day: str
    destination: Path
    retention: int


@dataclass(frozen=True)
class BackupResult:
    success: bool
    message: str
    file_path: Optional[Path] = None


@dataclass(frozen=True)
class RestoreResult:
    success: bool
    message: str
    security_backup_path: Optional[Path] = None


class BackupService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _effective_settings(self) -> Settings:
        return self._settings or get_settings()

    def _db_path(self) -> Path:
        return self._effective_settings().db_path

    def _audit(self, action: str, resultat: ResultatAudit, details: Optional[str] = None) -> None:
        with session_scope(self._settings) as session:
            session.add(
                AuditLog(
                    user_id=self._acting_user_id(), action=action, entite="sauvegardes",
                    entite_id=None, resultat=resultat, details=details,
                )
            )

    # -- configuration --------------------------------------------------------

    def get_config(self) -> BackupConfig:
        self._permissions.require_permission("BACKUP_VIEW")
        return self._read_config()

    def _read_config(self) -> BackupConfig:
        settings = self._effective_settings()
        with session_scope(self._settings) as session:
            repo = ParameterRepository(session)
            auto_enabled = (repo.get_value(_KEY_AUTO_ENABLED) or "false") == "true"
            frequency = repo.get_value(_KEY_FREQUENCY) or _DEFAULT_FREQUENCY
            time_of_day = repo.get_value(_KEY_TIME) or _DEFAULT_TIME
            destination = repo.get_value(_KEY_DESTINATION) or str(_default_destination(settings))
            retention_raw = repo.get_value(_KEY_RETENTION)
            retention = int(retention_raw) if retention_raw else _DEFAULT_RETENTION
        return BackupConfig(
            auto_enabled=auto_enabled, frequency=frequency, time_of_day=time_of_day,
            destination=Path(destination), retention=retention,
        )

    def update_config(
        self, *, auto_enabled: bool, frequency: str, time_of_day: str, destination: str, retention: int
    ) -> BackupConfig:
        """Valide et persiste la configuration. Aucune prétention de succès
        si le dossier de destination n'est pas accessible (§5) : la création
        du dossier est tentée immédiatement, toute ``OSError`` devient une
        ``ValidationError`` explicite, rien n'est enregistré."""
        self._permissions.require_permission("BACKUP_CREATE")

        if frequency not in _VALID_FREQUENCIES:
            raise ValidationError(
                f"Fréquence invalide : « {frequency} » (valeurs autorisées : {sorted(_VALID_FREQUENCIES)})."
            )
        _parse_time_of_day(time_of_day)
        if retention < 1:
            raise ValidationError("Le nombre de sauvegardes à conserver doit être au moins 1.")

        destination_text = (destination or "").strip()
        if not destination_text:
            raise ValidationError("Le dossier de destination est obligatoire.")
        destination_path = Path(destination_text)
        try:
            destination_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValidationError(
                f"Le dossier de destination « {destination_path} » n'est pas accessible : {exc}"
            ) from exc
        if not destination_path.is_dir():
            raise ValidationError(f"« {destination_path} » n'est pas un dossier.")

        with session_scope(self._settings) as session:
            repo = ParameterRepository(session)
            repo.set_value(_KEY_AUTO_ENABLED, "true" if auto_enabled else "false")
            repo.set_value(_KEY_FREQUENCY, frequency)
            repo.set_value(_KEY_TIME, time_of_day)
            repo.set_value(_KEY_DESTINATION, str(destination_path))
            repo.set_value(_KEY_RETENTION, str(retention))

        self._audit("BACKUP_CONFIG_UPDATE", ResultatAudit.SUCCES)
        logger.info("Configuration des sauvegardes mise à jour.")
        return self._read_config()

    # -- sauvegarde manuelle ----------------------------------------------------

    def create_manual_backup(self) -> BackupResult:
        self._permissions.require_permission("BACKUP_CREATE")
        config = self._read_config()
        return self._create_backup(config, action="BACKUP_MANUAL")

    def _create_backup(self, config: BackupConfig, *, action: str) -> BackupResult:
        """Créer -> vérifier -> ne prétendre un succès qu'après vérification
        (§4) -> appliquer la rétention -> auditer. Jamais l'inverse."""
        try:
            backup_path = backup_engine.create_backup_file(self._db_path(), config.destination)
        except _BACKUP_IO_ERRORS as exc:
            message = f"Échec de la sauvegarde : {exc}"
            logger.error(message)
            self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=message)
            return BackupResult(success=False, message=message)

        verification = backup_engine.verify_backup_file(backup_path)
        if not verification.valid:
            message = "La sauvegarde créée n'a pas passé la vérification : " + "; ".join(verification.errors)
            logger.error(message)
            self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=message)
            return BackupResult(success=False, message=message, file_path=backup_path)

        deleted = backup_engine.apply_retention(config.destination, config.retention)
        if deleted:
            logger.info("Rotation des sauvegardes : %d fichier(s) supprimé(s).", len(deleted))
            self._audit(
                "BACKUP_ROTATION", ResultatAudit.SUCCES,
                details=f"{len(deleted)} sauvegarde(s) supprimée(s) : {', '.join(p.name for p in deleted)}",
            )

        self._audit(f"{action}_SUCCESS", ResultatAudit.SUCCES, details=str(backup_path))
        logger.info("Sauvegarde créée : %s", backup_path)
        return BackupResult(success=True, message="Sauvegarde créée avec succès.", file_path=backup_path)

    # -- historique -------------------------------------------------------------

    def list_backups(self) -> list[backup_engine.BackupFileInfo]:
        self._permissions.require_permission("BACKUP_VIEW")
        config = self._read_config()
        return backup_engine.list_backup_files(config.destination)

    def verify_backup_file(self, file_path: Path) -> backup_engine.BackupVerification:
        """Expose la vérification d'un fichier de sauvegarde à l'UI (ex.
        colonne « statut » de l'historique) sans que celle-ci n'ait à
        importer ``backup_engine`` directement — conserve la couche
        UI -> Service -> mécanique de fichiers."""
        self._permissions.require_permission("BACKUP_VIEW")
        return backup_engine.verify_backup_file(Path(file_path))

    # -- sauvegarde planifiée -----------------------------------------------------

    def run_scheduled_backup_if_due(self) -> Optional[BackupResult]:
        """Aucune vérification de permission : opération système, déclenchée
        soit par un minuteur interne (l'application doit être ouverte),
        soit par ``app/backup_cli.py`` (intégration externe, ex.
        Planificateur de tâches Windows — §8, fonctionne même application
        fermée). Retourne ``None`` si la sauvegarde automatique est
        désactivée ou si l'échéance n'est pas encore atteinte."""
        config = self._read_config()
        if not config.auto_enabled:
            return None

        now = datetime.now()
        if not self._is_due(config, now):
            return None

        result = self._create_backup(config, action="BACKUP_AUTO")
        with session_scope(self._settings) as session:
            ParameterRepository(session).set_value(_KEY_LAST_AUTO_RUN, now.isoformat())
        return result

    def _is_due(self, config: BackupConfig, now: datetime) -> bool:
        target_time = _parse_time_of_day(config.time_of_day)
        if now.time() < target_time:
            return False

        with session_scope(self._settings) as session:
            last_run_raw = ParameterRepository(session).get_value(_KEY_LAST_AUTO_RUN)
        last_run = datetime.fromisoformat(last_run_raw) if last_run_raw else None

        if last_run is None:
            return True
        if config.frequency == FREQUENCY_DAILY:
            return last_run.date() < now.date()
        return (now.date() - last_run.date()).days >= 7  # hebdomadaire

    # -- restauration -------------------------------------------------------------

    def restore_backup(self, backup_path: Path) -> RestoreResult:
        """Restauration : opération critique (§9-11). Ordre strict, jamais
        modifié :
        1) vérifier le fichier source (intégrité, tables, version de schéma) —
           refusé sans qu'aucune donnée actuelle ne soit touchée si invalide ;
        2) créer une sauvegarde de sécurité de la base actuelle (préfixe
           dédié ``stockmanager_prerestore_``, jamais purgée par la rotation
           normale — §16 : ne jamais supprimer la sauvegarde de sécurité
           avant confirmation du succès) ;
        3) seulement alors remplacer la base active ;
        4) en cas d'échec à l'étape 3, retenter de restaurer l'état d'origine
           depuis la sauvegarde de sécurité — jamais laisser la base dans un
           état partiellement restauré.
        La confirmation explicite de l'utilisateur est de la responsabilité
        de l'interface (avant même l'appel à cette méthode).

        La tentative est tracée dans le journal applicatif, pas dans la
        table d'audit (voir commentaire avant l'appel à ``logger.info``
        ci-dessous) : seuls le succès et l'échec définitifs y sont écrits."""
        self._permissions.require_permission("BACKUP_RESTORE")
        backup_path = Path(backup_path)

        verification = backup_engine.verify_backup_file(backup_path)
        if not verification.valid:
            message = "Sauvegarde invalide, restauration refusée : " + "; ".join(verification.errors)
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message)

        current_version = backup_engine.get_alembic_version(self._db_path())
        if verification.alembic_version != current_version:
            message = (
                f"Version de schéma incompatible (sauvegarde : {verification.alembic_version!r}, "
                f"base actuelle : {current_version!r}) — restauration refusée."
            )
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message)

        config = self._read_config()
        try:
            security_backup_path = backup_engine.create_backup_file(
                self._db_path(), config.destination, prefix=backup_engine.PRERESTORE_PREFIX
            )
        except _BACKUP_IO_ERRORS as exc:
            message = f"Impossible de créer la sauvegarde de sécurité préalable : {exc}"
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message) from exc

        # Trace de la tentative dans le journal applicatif (fichier), jamais
        # dans la table d'audit : une restauration réussie remplace la base
        # entière — table d'audit comprise — par celle de la sauvegarde ;
        # toute ligne « tentative » écrite ici dans la base ACTUELLE serait
        # donc systématiquement effacée par son propre succès. Seuls les
        # résultats définitifs (succès/échec), écrits après coup dans la
        # base alors stabilisée, sont donc audités en base (§12).
        logger.info("Tentative de restauration depuis %s (utilisateur=%s).", backup_path, self._acting_user_id())

        # Libère toute connexion SQLAlchemy avant d'écraser le fichier actif.
        db_session_module.reset_engine_cache()
        try:
            backup_engine.restore_database_from_backup(backup_path, self._db_path())
        except _BACKUP_IO_ERRORS as exc:
            failure_message = f"Échec de la restauration : {exc}"
            logger.error(failure_message)
            try:
                backup_engine.restore_database_from_backup(security_backup_path, self._db_path())
                recovery_message = (
                    failure_message + " La base précédente a été restaurée depuis la sauvegarde de sécurité."
                )
            except _BACKUP_IO_ERRORS as recovery_exc:
                recovery_message = (
                    failure_message + f" ÉCHEC CRITIQUE : la restauration de secours a également échoué "
                    f"({recovery_exc}). Sauvegarde de sécurité disponible : {security_backup_path}."
                )
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=recovery_message)
            return RestoreResult(success=False, message=recovery_message, security_backup_path=security_backup_path)

        # La prochaine session s'ouvrira sur la base restaurée.
        db_session_module.reset_engine_cache()
        self._audit("BACKUP_RESTORE_SUCCESS", ResultatAudit.SUCCES, details=f"Restauré depuis {backup_path}.")
        logger.info("Restauration réussie depuis %s (sauvegarde de sécurité : %s).", backup_path, security_backup_path)
        return RestoreResult(
            success=True,
            message="Restauration réussie. Redémarrez l'application pour continuer.",
            security_backup_path=security_backup_path,
        )
