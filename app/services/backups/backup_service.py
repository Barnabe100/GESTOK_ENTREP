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
import tempfile
from dataclasses import dataclass
from datetime import datetime, time as time_type, timedelta
from pathlib import Path
from typing import Optional

from app.config.settings import Settings, get_settings
from app.db import init_db
from app.db import session as db_session_module
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.repositories.parameter_repository import ParameterRepository
from app.security.credential_vault import CredentialVault
from app.services.auth.permission_service import PermissionService
from app.services.backups import archive_manifest, backup_engine, temp_cleanup
from app.services.backups import postgresql_backup_engine as pg_backup_engine
from app.services.backups import archive_encryption
from app.services.backups.archive_encryption import ArchiveEncryptionError, decrypt_file_to_temp, encrypt_file_in_place
from app.services.backups.postgresql_backup_engine import (
    PostgreSQLBackupError,
    PostgreSQLTarget,
    PostgreSQLToolNotFoundError,
)
from app.utils.exceptions import CredentialVaultUnavailableError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.backups")

_KEY_AUTO_ENABLED = "backup.auto_enabled"
_KEY_FREQUENCY = "backup.frequency"
_KEY_TIME = "backup.time"
_KEY_DESTINATION = "backup.destination"
_KEY_RETENTION = "backup.retention"
_KEY_LAST_AUTO_RUN = "backup.last_auto_run"
# Mission « Sauvegarde automatique et restauration », §5 : chiffrement
# optionnel des archives, désactivé par défaut (voir
# ``archive_encryption.py`` pour la justification de ce choix).
_KEY_ENCRYPTION_ENABLED = "backup.encryption_enabled"

FREQUENCY_DAILY = "daily"
FREQUENCY_WEEKLY = "weekly"
_VALID_FREQUENCIES = {FREQUENCY_DAILY, FREQUENCY_WEEKLY}

# Valeurs par défaut sûres (§14) : sauvegarde automatique désactivée tant
# qu'un administrateur ne l'a pas explicitement activée. Rétention par
# défaut 30 (Mission « Sauvegarde automatique et restauration », §2.A —
# avant cette mission : 10 ; ne change rien pour un poste ayant déjà
# enregistré une valeur explicite, voir ``_read_config``). Heure par défaut
# 20:00 (mission corrective « Fiabilisation du module de sauvegarde »,
# §3.8 — avant cette mission : 02:00) : la tâche planifiée Windows unique
# (sauvegarde locale ET copie externe, voir ``ExternalBackupService``)
# hérite désormais directement de cette heure, et ne peut s'exécuter que
# si une session Windows est active à cet instant précis (voir
# ``scheduled_task_manager``) — 20h est beaucoup plus susceptible de
# trouver un ordinateur encore allumé que 2h du matin. Ne change rien pour
# un poste ayant déjà enregistré une valeur explicite (voir
# ``_read_config``, même garde que pour la rétention ci-dessus).
_DEFAULT_FREQUENCY = FREQUENCY_DAILY
_DEFAULT_TIME = "20:00"
_DEFAULT_RETENTION = 30

# Erreurs anticipées d'accès fichier/SQLite — jamais une exception large
# masquant un bug ailleurs dans le moteur. Inclut les deux nouvelles erreurs
# de l'écriture/du remplacement atomiques (mission corrective, §3.2/§3.9) :
# toutes les deux signifient, comme OSError/sqlite3.Error, un échec
# anticipé de la mécanique de fichiers, jamais un bug applicatif — voir
# backup_engine.RestoreValidationError/AtomicReplaceError.
_BACKUP_IO_ERRORS = (
    OSError, sqlite3.Error, backup_engine.RestoreValidationError, backup_engine.AtomicReplaceError,
)

# Pendant PostgreSQL de ``_BACKUP_IO_ERRORS`` (Lot E, §E.2) : erreurs
# anticipées d'exécution de pg_dump/pg_restore — jamais une exception large.
_POSTGRESQL_BACKUP_ERRORS = (PostgreSQLToolNotFoundError, PostgreSQLBackupError)


def _default_destination(settings: Settings) -> Path:
    return settings.data_dir / "backups"


def _check_destination_accessible(path: Path) -> Optional[str]:
    """Mission corrective, §3.11 : vérifie que ``path`` existe et accepte
    réellement l'écriture SUR CE POSTE — jamais seulement son existence,
    jamais une simple vérification de permissions qui pourrait mentir (ex.
    dossier présent mais lecture seule, ou sur un support externe
    actuellement débranché). Retourne ``None`` si tout est en ordre, sinon
    un message prêt à afficher à l'administrateur — ne crée et ne modifie
    jamais le dossier lui-même (contrairement à ``update_config``, qui le
    crée explicitement sur demande de configuration) : une simple
    revalidation après restauration ne doit jamais avoir d'effet de bord
    sur le système de fichiers autre que l'écriture éphémère de son propre
    fichier de test, immédiatement supprimé."""
    if not path.exists() or not path.is_dir():
        return (
            f"Le dossier de destination des sauvegardes configuré dans la sauvegarde restaurée "
            f"(« {path} ») n'existe pas sur ce poste. Reconfigurez un nouveau dossier de destination "
            f"avant la prochaine sauvegarde."
        )
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".stockmanager_test_ecriture_", delete=True):
            pass
    except OSError as exc:
        return (
            f"Le dossier de destination des sauvegardes configuré dans la sauvegarde restaurée "
            f"(« {path} ») n'est pas accessible en écriture sur ce poste : {exc} Reconfigurez un "
            f"nouveau dossier de destination avant la prochaine sauvegarde."
        )
    return None


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
    # Mission « Sauvegarde automatique et restauration », §5 : désactivé
    # par défaut (voir archive_encryption.py) — change un comportement
    # établi (archives jusqu'ici en clair), jamais activé implicitement.
    encryption_enabled: bool = False


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
    # Mission corrective « Fiabilisation du module de sauvegarde », §3.11 :
    # renseigné (jamais sur un échec) lorsque le dossier de destination des
    # sauvegardes RESTAURÉ (venu de la base restaurée elle-même, via la
    # table ``parametres``) n'existe pas ou n'est pas accessible en
    # écriture sur CE poste — cas typique d'un changement d'ordinateur, où
    # l'ancien chemin (ex. ``D:\Sauvegardes``) n'a aucune raison d'exister
    # à l'identique sur le nouveau. Jamais corrigé silencieusement : à
    # l'appelant (interface) de le signaler et de proposer un nouveau
    # dossier, voir ``BackupsPage``/``BackupRestoreWizardDialog``.
    destination_warning: Optional[str] = None


@dataclass(frozen=True)
class BackupEntry:
    """Une ligne de l'historique des sauvegardes, avec le moteur qui l'a
    produite (Lot E, §E.3) — ``backup_engine``/``postgresql_backup_engine``
    utilisent des motifs de nommage et des extensions mutuellement
    exclusifs (``.db`` vs ``.dump``), jamais confondus : l'historique peut
    légitimement contenir les deux (ex. un poste ayant changé de moteur),
    mais ne doit jamais présenter l'un comme l'autre."""

    engine: str
    info: backup_engine.BackupFileInfo


class BackupService:
    def __init__(
        self, permission_service: PermissionService, settings: Optional[Settings] = None,
        *, encryption_vault: Optional[CredentialVault] = None,
    ) -> None:
        self._permissions = permission_service
        self._settings = settings
        # Jamais résolu ici (coûteux, spécifique Windows) : seulement
        # transmis tel quel à ``archive_encryption`` au moment précis d'un
        # chiffrement/déchiffrement. ``None`` (comportement par défaut en
        # production) laisse ``archive_encryption`` résoudre le coffre
        # Windows réel ; un coffre injecté ici (tests) permet de valider le
        # cycle complet chiffrement/sauvegarde/restauration sans Windows
        # Credential Manager (voir tests/test_backup_service.py).
        self._encryption_vault = encryption_vault

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _effective_settings(self) -> Settings:
        return self._settings or get_settings()

    def _db_path(self) -> Path:
        return self._effective_settings().db_path

    def _postgresql_target(self, settings: Settings) -> PostgreSQLTarget:
        """Jamais appelée lorsque ``settings.postgresql`` est ``None`` —
        l'appelant doit vérifier (voir ``_create_backup_postgresql``/
        ``_restore_backup_postgresql``)."""
        pg = settings.postgresql
        assert pg is not None
        return PostgreSQLTarget(host=pg.host, port=pg.port, database=pg.database, username=pg.username)

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

    def active_engine(self) -> str:
        """Moteur de base de données réellement actif (``"sqlite"`` ou
        ``"postgresql"``) — Lot E, §E.4 : l'interface doit toujours afficher
        clairement le moteur concerné plutôt que de le laisser implicite."""
        self._permissions.require_permission("BACKUP_VIEW")
        return self._effective_settings().db_backend

    def active_postgresql_target(self) -> Optional[PostgreSQLTarget]:
        """Cible PostgreSQL active (hôte/port/base/utilisateur — jamais le
        mot de passe), ou ``None`` si le moteur actif n'est pas PostgreSQL.
        Lot E.7, §E.7.2 : permet à l'interface d'identifier clairement la
        base qui serait affectée par une restauration (pas seulement le nom
        du moteur) — ne permet jamais de choisir une autre base depuis cet
        écran, cette méthode ne fait que lire la configuration déjà active."""
        self._permissions.require_permission("BACKUP_VIEW")
        settings = self._effective_settings()
        if settings.db_backend != "postgresql" or settings.postgresql is None:
            return None
        return self._postgresql_target(settings)

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
            encryption_enabled = (repo.get_value(_KEY_ENCRYPTION_ENABLED) or "false") == "true"
        return BackupConfig(
            auto_enabled=auto_enabled, frequency=frequency, time_of_day=time_of_day,
            destination=Path(destination), retention=retention, encryption_enabled=encryption_enabled,
        )

    def update_config(
        self, *, auto_enabled: bool, frequency: str, time_of_day: str, destination: str, retention: int,
        encryption_enabled: bool = False,
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
            repo.set_value(_KEY_ENCRYPTION_ENABLED, "true" if encryption_enabled else "false")

        self._audit("BACKUP_CONFIG_UPDATE", ResultatAudit.SUCCES)
        logger.info("Configuration des sauvegardes mise à jour.")
        return self._read_config()

    # -- sauvegarde manuelle ----------------------------------------------------

    def _backup_lock(self):
        """Verrou partagé par toute opération mutative de sauvegarde/
        restauration (mission corrective, §3.7) — même fichier que l'agent
        auxiliaire (``app.backup_external_agent_cli``, voir
        ``app.utils.process_lock.BACKUP_LOCK_FILENAME``) : une action
        manuelle (ce module) et le cycle planifié de l'agent ne peuvent
        ainsi jamais manipuler simultanément les mêmes fichiers. Réentrant
        au sein d'un même processus (voir ``ProcessLock``, docstring de
        module) : un appel imbriqué (ex. l'agent détient déjà ce verrou,
        puis appelle une des méthodes ci-dessous) ne se bloque jamais
        lui-même."""
        from app.utils.process_lock import BACKUP_LOCK_FILENAME, ProcessLock

        return ProcessLock(self._effective_settings().data_dir / BACKUP_LOCK_FILENAME)

    def cleanup_orphaned_temp_files(self) -> list[Path]:
        """Mission corrective, §3.13 : balaie les dossiers que ce service
        gère lui-même (dossier de la base active, dossier de destination
        des sauvegardes locales) à la recherche de fichiers temporaires
        orphelins laissés par une opération interrompue brutalement
        (jamais par une fermeture normale, qui nettoie toujours les siens
        elle-même via ``finally`` — voir ``backup_engine``/
        ``archive_encryption``). Acquiert elle-même le verrou partagé
        (§3.7) avant tout nettoyage — jamais de suppression tant qu'une
        autre opération pourrait être en cours (voir
        ``temp_cleanup.cleanup_orphaned_temp_files``, docstring de
        module) ; renonce silencieusement (liste vide) si le verrou est
        déjà détenu, plutôt que d'attendre.

        Jamais de vérification de permission ici : appelée uniquement par
        l'agent auxiliaire (aucun utilisateur connecté, même convention
        que ``run_scheduled_backup_if_due``) — jamais exposée telle quelle
        à l'interface."""
        lock = self._backup_lock()
        if not lock.acquire():
            return []
        try:
            removed = temp_cleanup.cleanup_orphaned_temp_files(self._effective_settings().data_dir)
            removed += temp_cleanup.cleanup_orphaned_temp_files(self._read_config().destination)
            return removed
        finally:
            lock.release()

    def create_manual_backup(self) -> BackupResult:
        self._permissions.require_permission("BACKUP_CREATE")
        lock = self._backup_lock()
        if not lock.acquire():
            return BackupResult(
                success=False,
                message=(
                    "Une autre opération de sauvegarde ou de restauration est déjà en cours sur ce "
                    "poste. Réessayez dans quelques instants."
                ),
            )
        try:
            config = self._read_config()
            settings = self._effective_settings()
            if settings.db_backend == "postgresql":
                return self._create_backup_postgresql(config, settings, action="BACKUP_MANUAL")
            return self._create_backup(config, action="BACKUP_MANUAL")
        finally:
            lock.release()

    def _create_backup(
        self, config: BackupConfig, *, action: str, backup_type: str = archive_manifest.BACKUP_TYPE_LOCAL,
    ) -> BackupResult:
        """Créer -> vérifier -> chiffrer si activé -> manifeste -> ne
        prétendre un succès qu'après vérification (§4) -> appliquer la
        rétention -> auditer. Jamais l'inverse."""
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

        encrypted = False
        if config.encryption_enabled:
            try:
                encrypt_file_in_place(backup_path, vault=self._encryption_vault)
                encrypted = True
            except (ArchiveEncryptionError, CredentialVaultUnavailableError) as exc:
                message = f"Sauvegarde créée mais échec du chiffrement : {exc}"
                logger.error(message)
                self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=message)
                return BackupResult(success=False, message=message, file_path=backup_path)

        # Manifeste écrit en dernier (§5) : son empreinte doit toujours
        # correspondre exactement aux octets finaux sur le disque, chiffrés
        # ou non.
        archive_manifest.write_manifest_for(
            backup_path, db_engine="sqlite", schema_version=verification.alembic_version,
            backup_type=backup_type, encrypted=encrypted,
        )

        deleted = backup_engine.apply_retention(config.destination, config.retention)
        if deleted:
            for deleted_path in deleted:
                archive_manifest.delete_manifest_for(deleted_path)
            logger.info("Rotation des sauvegardes : %d fichier(s) supprimé(s).", len(deleted))
            self._audit(
                "BACKUP_ROTATION", ResultatAudit.SUCCES,
                details=f"{len(deleted)} sauvegarde(s) supprimée(s) : {', '.join(p.name for p in deleted)}",
            )

        self._audit(f"{action}_SUCCESS", ResultatAudit.SUCCES, details=str(backup_path))
        logger.info("Sauvegarde créée : %s", backup_path)
        return BackupResult(success=True, message="Sauvegarde créée avec succès.", file_path=backup_path)

    def _create_backup_postgresql(self, config: BackupConfig, settings: Settings, *, action: str) -> BackupResult:
        """Pendant PostgreSQL de :meth:`_create_backup` (Lot E, §E.2.2) :
        même ordre strict (créer -> vérifier -> rotation -> auditer),
        jamais de prétention de succès avant vérification."""
        pg = settings.postgresql
        if pg is None:
            message = "Aucune configuration PostgreSQL active : sauvegarde impossible."
            self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=message)
            return BackupResult(success=False, message=message)

        try:
            password = pg.resolve_password()
        except ValueError as exc:
            message = f"Échec de la sauvegarde : {exc}"
            self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=message)
            return BackupResult(success=False, message=message)

        target = self._postgresql_target(settings)
        try:
            backup_path = pg_backup_engine.create_backup_file(target, password, config.destination)
        except _POSTGRESQL_BACKUP_ERRORS as exc:
            message = f"Échec de la sauvegarde : {exc}"
            logger.error(message)
            self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=message)
            return BackupResult(success=False, message=message)

        verification = pg_backup_engine.verify_backup_file(backup_path)
        if not verification.valid:
            message = "La sauvegarde créée n'a pas passé la vérification : " + "; ".join(verification.errors)
            logger.error(message)
            self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=message)
            return BackupResult(success=False, message=message, file_path=backup_path)

        encrypted = False
        if config.encryption_enabled:
            try:
                encrypt_file_in_place(backup_path, vault=self._encryption_vault)
                encrypted = True
            except (ArchiveEncryptionError, CredentialVaultUnavailableError) as exc:
                message = f"Sauvegarde créée mais échec du chiffrement : {exc}"
                logger.error(message)
                self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=message)
                return BackupResult(success=False, message=message, file_path=backup_path)

        archive_manifest.write_manifest_for(
            backup_path, db_engine="postgresql", schema_version=verification.alembic_version,
            backup_type=archive_manifest.BACKUP_TYPE_LOCAL, encrypted=encrypted,
        )

        deleted = pg_backup_engine.apply_retention(config.destination, config.retention)
        if deleted:
            for deleted_path in deleted:
                archive_manifest.delete_manifest_for(deleted_path)
            logger.info("Rotation des sauvegardes PostgreSQL : %d fichier(s) supprimé(s).", len(deleted))
            self._audit(
                "BACKUP_ROTATION", ResultatAudit.SUCCES,
                details=f"{len(deleted)} sauvegarde(s) PostgreSQL supprimée(s) : {', '.join(p.name for p in deleted)}",
            )

        self._audit(f"{action}_SUCCESS", ResultatAudit.SUCCES, details=str(backup_path))
        logger.info("Sauvegarde PostgreSQL créée : %s", backup_path)
        return BackupResult(success=True, message="Sauvegarde PostgreSQL créée avec succès.", file_path=backup_path)

    # -- historique -------------------------------------------------------------

    def list_backups(self) -> list[BackupEntry]:
        """Historique combiné des deux moteurs (Lot E, §E.3) — un poste
        ayant changé de moteur peut légitimement conserver des sauvegardes
        des deux types ; chaque entrée porte son propre moteur, jamais
        ambigu grâce aux motifs de nommage mutuellement exclusifs."""
        self._permissions.require_permission("BACKUP_VIEW")
        return self._list_backups_unchecked()

    def list_backups_for_automation(self) -> list[BackupEntry]:
        """Même résultat que :meth:`list_backups`, sans aucune vérification
        de permission — réservé aux appelants système non interactifs
        (``ExternalBackupService``/l'agent auxiliaire, voir
        ``app.backup_external_agent_cli``, exécutés sans session
        utilisateur), jamais à l'interface utilisateur (qui doit toujours
        passer par :meth:`list_backups`, qui vérifie BACKUP_VIEW) — même
        convention que ``run_scheduled_backup_if_due``."""
        return self._list_backups_unchecked()

    def _list_backups_unchecked(self) -> list[BackupEntry]:
        config = self._read_config()
        entries = [BackupEntry("sqlite", info) for info in backup_engine.list_backup_files(config.destination)]
        entries += [
            BackupEntry("postgresql", info) for info in pg_backup_engine.list_backup_files(config.destination)
        ]
        return sorted(entries, key=lambda entry: entry.info.name, reverse=True)

    def verify_backup_file(self, file_path: Path):
        """Expose la vérification d'un fichier de sauvegarde à l'UI (ex.
        colonne « statut » de l'historique) sans que celle-ci n'ait à
        importer les moteurs directement — conserve la couche
        UI -> Service -> mécanique de fichiers. Le moteur de vérification
        est déduit de l'extension du fichier (``.dump`` -> PostgreSQL,
        ``.db`` -> SQLite), jamais du moteur actif (l'historique peut
        contenir des sauvegardes de l'autre moteur, voir :meth:`list_backups`).

        Décrypte vers une copie temporaire si l'archive est chiffrée (voir
        le manifeste) avant toute vérification structurelle — jamais une
        tentative de lecture directe d'une archive chiffrée, qui
        échouerait toujours. La copie temporaire est systématiquement
        supprimée après usage, qu'elle ait servi ou non."""
        self._permissions.require_permission("BACKUP_VIEW")
        file_path, temp_to_cleanup = self._resolve_plaintext_path(file_path)
        try:
            if file_path.suffix == ".dump":
                return pg_backup_engine.verify_backup_file(file_path)
            return backup_engine.verify_backup_file(file_path)
        finally:
            if temp_to_cleanup is not None:
                temp_to_cleanup.unlink(missing_ok=True)

    def _resolve_plaintext_path(self, archive_path: Path) -> tuple[Path, Optional[Path]]:
        """Retourne ``(chemin à utiliser pour toute lecture, chemin
        temporaire à nettoyer ensuite ou None)``. Si l'archive n'est pas
        chiffrée (ou aucun manifeste associé — sauvegarde antérieure à ce
        mécanisme), retourne l'archive elle-même sans aucune copie.

        Vérifie d'abord l'empreinte du manifeste : une archive chiffrée
        altérée depuis sa création est refusée ici, avant même toute
        tentative de déchiffrement — jamais un déchiffrement tenté sur un
        contenu dont l'intégrité n'est plus garantie."""
        archive_path = Path(archive_path)
        manifest = archive_manifest.read_manifest_for(archive_path)
        if manifest is None or not manifest.encrypted:
            return archive_path, None

        manifest_check = archive_manifest.verify_manifest_for(archive_path)
        if not manifest_check.hash_matches:
            raise ValidationError(
                "L'empreinte de cette archive chiffrée ne correspond plus à celle enregistrée "
                "à sa création — fichier altéré ou corrompu : " + "; ".join(manifest_check.errors)
            )
        temp_path = decrypt_file_to_temp(archive_path, vault=self._encryption_vault)
        return temp_path, temp_path

    # -- transfert de la clé de chiffrement (mission corrective, §3.1) ------------
    #
    # Toutes ces méthodes exposent app.services.backups.archive_encryption à
    # l'interface sans que celle-ci n'ait à importer ce module directement
    # (même principe que verify_backup_file ci-dessus) — chacune vérifie sa
    # propre permission dédiée (BACKUP_ENCRYPTION_MANAGE pour les opérations
    # sensibles d'export/import, BACKUP_VIEW pour la simple consultation/le
    # test en lecture seule), et journalise chaque export/import réussi ou
    # refusé dans l'audit, exactement comme le reste du module.

    def has_encryption_key_configured(self) -> bool:
        self._permissions.require_permission("BACKUP_VIEW")
        try:
            archive_encryption.require_existing_encryption_key(self._encryption_vault)
        except archive_encryption.ArchiveEncryptionError:
            return False
        return True

    def export_encryption_key(self, destination_path: Path, password: str) -> None:
        """Exporte la clé de chiffrement actuelle — jamais dans le dossier
        de sauvegardes configuré (voir
        ``archive_encryption.export_encryption_key``, paramètre
        ``backup_destination``)."""
        self._permissions.require_permission("BACKUP_ENCRYPTION_MANAGE")
        config = self._read_config()
        try:
            archive_encryption.export_encryption_key(
                Path(destination_path), password, vault=self._encryption_vault,
                backup_destination=config.destination,
            )
        except archive_encryption.ArchiveEncryptionError as exc:
            self._audit("BACKUP_ENCRYPTION_KEY_EXPORT_FAILURE", ResultatAudit.ECHEC, details=str(exc))
            raise
        self._audit("BACKUP_ENCRYPTION_KEY_EXPORT_SUCCESS", ResultatAudit.SUCCES)
        logger.info("Clé de chiffrement des sauvegardes exportée vers %s.", destination_path)

    def import_encryption_key(self, source_path: Path, password: str, *, overwrite: bool = False) -> None:
        self._permissions.require_permission("BACKUP_ENCRYPTION_MANAGE")
        try:
            archive_encryption.import_encryption_key(
                Path(source_path), password, vault=self._encryption_vault, overwrite=overwrite,
            )
        except archive_encryption.ArchiveEncryptionError as exc:
            self._audit("BACKUP_ENCRYPTION_KEY_IMPORT_FAILURE", ResultatAudit.ECHEC, details=str(exc))
            raise
        self._audit("BACKUP_ENCRYPTION_KEY_IMPORT_SUCCESS", ResultatAudit.SUCCES)
        logger.info("Clé de chiffrement des sauvegardes importée depuis %s.", source_path)

    def test_encryption_key_against_archive(self, archive_path: Path) -> bool:
        """Vérification en lecture seule, jamais destructive — permission
        ``BACKUP_VIEW`` (même niveau que :meth:`verify_backup_file`), pas
        ``BACKUP_ENCRYPTION_MANAGE`` (aucune écriture dans le coffre ici)."""
        self._permissions.require_permission("BACKUP_VIEW")
        return archive_encryption.test_key_against_archive(Path(archive_path), vault=self._encryption_vault)

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

        # Verrou acquis seulement une fois su qu'une sauvegarde va
        # réellement être tentée (§3.7) — jamais pour les appels fréquents
        # (minuteur applicatif toutes les 60 s) qui ne font rien tant que
        # l'échéance n'est pas atteinte.
        lock = self._backup_lock()
        if not lock.acquire():
            logger.info("Sauvegarde planifiée reportée : une autre opération de sauvegarde est déjà en cours.")
            return None
        try:
            settings = self._effective_settings()
            if settings.db_backend == "postgresql":
                result = self._create_backup_postgresql(config, settings, action="BACKUP_AUTO")
            else:
                result = self._create_backup(config, action="BACKUP_AUTO")
            with session_scope(self._settings) as session:
                ParameterRepository(session).set_value(_KEY_LAST_AUTO_RUN, now.isoformat())
            return result
        finally:
            lock.release()

    def _is_due(self, config: BackupConfig, now: datetime) -> bool:
        """Mission corrective « Fiabilisation du module de sauvegarde »,
        §3.4 : avant ce correctif, ``now.time() < target_time`` bloquait
        systématiquement toute sauvegarde avant l'heure cible DU JOUR,
        même si une échéance complète avait déjà été manquée la veille
        (ordinateur éteint à l'heure prévue) — il fallait alors attendre
        l'heure cible du jour suivant, qui pouvait elle-même être manquée
        de la même façon, sans fin. Un rattrapage immédiat est désormais
        déclenché dès qu'au moins un jour calendaire complet s'est écoulé
        sans sauvegarde réussie (voir :meth:`_is_due_as_of` ci-dessous) —
        quelle que soit l'heure actuelle, dès le prochain appel (minuteur
        applicatif de l'interface ou agent planifié Windows, voir leurs
        docstrings respectives : les deux appellent cette même méthode,
        jamais une logique de rattrapage dupliquée entre eux).

        Jamais appliqué à une toute première sauvegarde
        (``last_run is None``) : une installation qui vient d'activer la
        sauvegarde automatique doit attendre la première heure cible, pile
        comme avant ce correctif — un déclenchement immédiat et inattendu
        dès l'activation serait une surprise, pas un rattrapage d'une
        échéance réellement manquée."""
        target_time = _parse_time_of_day(config.time_of_day)

        with session_scope(self._settings) as session:
            last_run_raw = ParameterRepository(session).get_value(_KEY_LAST_AUTO_RUN)
        last_run = datetime.fromisoformat(last_run_raw) if last_run_raw else None

        if now.time() < target_time:
            if last_run is not None and self._is_due_as_of(config, last_run, now.date() - timedelta(days=1)):
                return True  # rattrapage : déjà en retard hier, inutile d'attendre l'heure cible d'aujourd'hui.
            return False

        if last_run is None:
            return True
        return self._is_due_as_of(config, last_run, now.date())

    @staticmethod
    def _is_due_as_of(config: BackupConfig, last_run: datetime, reference_date) -> bool:
        """Logique pure de « échéance atteinte », isolée de l'heure du jour
        — appelée à la fois pour la date du jour (chemin normal) et pour la
        veille (vérification de rattrapage ci-dessus), jamais dupliquée
        entre les deux."""
        if config.frequency == FREQUENCY_DAILY:
            return last_run.date() < reference_date
        return (reference_date - last_run.date()).days >= 7  # hebdomadaire

    # -- restauration -------------------------------------------------------------

    def restore_backup(self, backup_path: Path) -> RestoreResult:
        """Restauration : opération critique (§9-11, Lot E §E.2.3). Première
        vérification, commune aux deux moteurs : le fichier doit provenir
        du moteur réellement actif — jamais une opération incohérente avec
        le moteur actif (ex. restaurer une sauvegarde PostgreSQL alors que
        SQLite est actif, ou l'inverse) : refusé avant même d'examiner le
        contenu du fichier. La confirmation explicite de l'utilisateur est
        de la responsabilité de l'interface (avant même l'appel à cette
        méthode)."""
        self._permissions.require_permission("BACKUP_RESTORE")
        backup_path = Path(backup_path)
        settings = self._effective_settings()

        backup_engine_kind = "postgresql" if backup_path.suffix == ".dump" else "sqlite"
        if backup_engine_kind != settings.db_backend:
            message = (
                f"Cette sauvegarde provient du moteur « {backup_engine_kind} », alors que le "
                f"moteur actif est « {settings.db_backend} » — restauration refusée."
            )
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message)

        # §3.7 : une restauration ne doit jamais s'exécuter en même temps
        # qu'une création de sauvegarde ou une copie externe (même verrou
        # que create_manual_backup/run_scheduled_backup_if_due ci-dessus).
        lock = self._backup_lock()
        if not lock.acquire():
            message = (
                "Une autre opération de sauvegarde ou de restauration est déjà en cours sur ce "
                "poste. Réessayez dans quelques instants."
            )
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message)
        try:
            if settings.db_backend == "postgresql":
                return self._restore_backup_postgresql(backup_path, settings)
            return self._restore_backup_sqlite(backup_path)
        finally:
            lock.release()

    def _restore_backup_sqlite(self, backup_path: Path) -> RestoreResult:
        """Ordre strict, jamais modifié :
        1) vérifier le fichier source (intégrité, tables, version de schéma) —
           refusé sans qu'aucune donnée actuelle ne soit touchée si invalide ;
        2) créer une sauvegarde de sécurité de la base actuelle (préfixe
           dédié ``stockmanager_prerestore_``, jamais purgée par la rotation
           normale — §16 : ne jamais supprimer la sauvegarde de sécurité
           avant confirmation du succès) ;
        3) seulement alors remplacer la base active — jamais directement :
           voir ``backup_engine.restore_database_from_backup``, qui copie
           d'abord vers un fichier temporaire du même répertoire, vérifie
           son intégrité SQLite, puis ne remplace ``self._db_path()`` que
           par un remplacement atomique (mission corrective, §3.2 : jamais
           de risque qu'une interruption laisse la base active dans un état
           partiellement remplacé, puisqu'elle n'est jamais touchée avant
           que la copie ne soit intégralement prête et vérifiée).
        4) si ce remplacement final échoue malgré tout (ex. verrou
           transitoire Windows), la base active n'a, par construction,
           jamais été modifiée — jamais besoin ici d'une restauration de
           secours depuis la sauvegarde préalable : le scénario qu'elle
           couvrait (un remplacement partiellement effectué) ne peut plus
           se produire. La sauvegarde préalable reste néanmoins créée et
           conservée dans tous les cas (défense en profondeur).

        La tentative est tracée dans le journal applicatif, pas dans la
        table d'audit (voir commentaire avant l'appel à ``logger.info``
        ci-dessous) : seuls le succès et l'échec définitifs y sont écrits.

        Décrypte d'abord ``backup_path`` vers une copie temporaire en clair
        si l'archive est chiffrée (voir le manifeste) — la vérification et
        la restauration elles-mêmes opèrent toujours sur cette copie en
        clair, jamais sur le fichier chiffré directement ; la copie
        temporaire est systématiquement supprimée après usage, succès ou
        échec."""
        try:
            plaintext_path, temp_to_cleanup = self._resolve_plaintext_path(backup_path)
        except (ValidationError, ArchiveEncryptionError) as exc:
            message = str(exc)
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message) from exc

        try:
            verification = backup_engine.verify_backup_file(plaintext_path)
            if not verification.valid:
                message = "Sauvegarde invalide, restauration refusée : " + "; ".join(verification.errors)
                self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
                raise ValidationError(message)

            current_version = backup_engine.get_alembic_version(self._db_path())
            needs_schema_upgrade = False
            if verification.alembic_version != current_version:
                # Mission corrective, §3.10 : une sauvegarde dont la version
                # est un ANCÊTRE strict de la version actuelle (migrations
                # ultérieures jamais appliquées sur la base restaurée, ex.
                # changement d'ordinateur avec une archive plus ancienne)
                # reste restaurable — le schéma sera mis à niveau vers
                # ``head`` juste après (voir plus bas) — jamais le cas
                # inverse (sauvegarde plus récente, ou branche distincte),
                # qui exigerait une régression de schéma jamais tentée
                # automatiquement.
                settings_for_version_check = self._effective_settings()
                if not init_db.is_ancestor_revision(verification.alembic_version, settings_for_version_check):
                    message = (
                        f"Version de schéma incompatible (sauvegarde : {verification.alembic_version!r}, "
                        f"base actuelle : {current_version!r}) — cette sauvegarde est plus récente que "
                        f"l'application actuelle, ou provient d'une version incompatible. Mettez à jour "
                        f"StockManager Desktop avant de réessayer. Restauration refusée."
                    )
                    self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
                    raise ValidationError(message)
                needs_schema_upgrade = True

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

            # Libère toute connexion SQLAlchemy avant de tenter le
            # remplacement final (voir backup_engine.restore_database_from_backup :
            # la copie elle-même, qui précède ce remplacement, n'a besoin
            # d'aucune connexion sur ``self._db_path()``, seul le
            # remplacement final la concerne).
            db_session_module.reset_engine_cache()
            try:
                backup_engine.restore_database_from_backup(plaintext_path, self._db_path())
            except backup_engine.AtomicReplaceError as exc:
                # La copie restaurée est déjà entièrement vérifiée ; seul le
                # remplacement final a échoué (verrou transitoire, voir la
                # docstring de la méthode) — la base active n'a, elle,
                # jamais été modifiée : jamais besoin de la restauration de
                # secours ci-dessous dans ce cas précis.
                failure_message = (
                    f"La restauration n'a pas pu être finalisée : {exc} La base active n'a pas été "
                    f"modifiée. La copie restaurée et déjà vérifiée reste disponible ici : "
                    f"{exc.recovered_path} — vous pouvez réessayer la restauration, ou copier "
                    f"manuellement ce fichier à la place de « {self._db_path()} » une fois "
                    f"StockManager Desktop complètement fermé."
                )
                logger.error(failure_message)
                self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=failure_message)
                return RestoreResult(
                    success=False, message=failure_message, security_backup_path=security_backup_path
                )
            except _BACKUP_IO_ERRORS as exc:
                # Échec avant tout remplacement (copie vers le fichier
                # temporaire, ou échec de sa vérification d'intégrité) : la
                # base active n'a, ici non plus, jamais été touchée — même
                # raisonnement que ci-dessus, jamais besoin de restauration
                # de secours.
                failure_message = f"Échec de la restauration : {exc} La base active n'a pas été modifiée."
                logger.error(failure_message)
                self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=failure_message)
                return RestoreResult(
                    success=False, message=failure_message, security_backup_path=security_backup_path
                )

            if needs_schema_upgrade:
                # §3.10 : le fichier restauré est à une version de schéma
                # ANCIENNE mais compatible (ancêtre de head, voir plus haut)
                # — on l'amène maintenant à ``head`` via les migrations
                # Alembic normales, exactement comme au premier démarrage
                # de l'application (``app.db.init_db.init_database``,
                # réutilisée telle quelle, jamais une logique dupliquée).
                try:
                    init_db.init_database(settings_for_version_check)
                except Exception as exc:
                    # La mise à niveau du schéma a échoué : jamais laisser
                    # la base active à mi-chemin entre deux versions de
                    # schéma. La sauvegarde de sécurité créée plus haut est
                    # à la version ACTUELLE, déjà connue bonne : on y
                    # revient, plutôt que de laisser la restauration dans
                    # un état incertain.
                    db_session_module.reset_engine_cache()
                    try:
                        backup_engine.restore_database_from_backup(security_backup_path, self._db_path())
                        db_session_module.reset_engine_cache()
                        rollback_note = (
                            f"La base a été rétablie dans son état d'avant restauration (sauvegarde de "
                            f"sécurité : {security_backup_path})."
                        )
                    except (backup_engine.AtomicReplaceError, *_BACKUP_IO_ERRORS) as rollback_exc:
                        rollback_note = (
                            f"Le rétablissement automatique de l'état précédent a lui-même échoué : "
                            f"{rollback_exc} Intervention manuelle nécessaire — la sauvegarde de sécurité "
                            f"reste disponible ici : {security_backup_path}."
                        )
                    failure_message = (
                        f"La sauvegarde a été restaurée mais la mise à niveau du schéma vers la version "
                        f"actuelle de l'application a échoué : {exc} {rollback_note}"
                    )
                    logger.error(failure_message)
                    self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=failure_message)
                    return RestoreResult(
                        success=False, message=failure_message, security_backup_path=security_backup_path
                    )

            # La prochaine session s'ouvrira sur la base restaurée.
            db_session_module.reset_engine_cache()
            self._audit("BACKUP_RESTORE_SUCCESS", ResultatAudit.SUCCES, details=f"Restauré depuis {backup_path}.")
            logger.info(
                "Restauration réussie depuis %s (sauvegarde de sécurité : %s).", backup_path, security_backup_path
            )
            # §3.11 : le dossier de destination des sauvegardes vient de
            # changer de contenu (il provient maintenant de la base
            # restaurée, via ``parametres``) — jamais supposé valide sur CE
            # poste sans le revérifier (cas typique d'un changement
            # d'ordinateur, voir la docstring de ``RestoreResult``).
            destination_warning = _check_destination_accessible(self._read_config().destination)
            return RestoreResult(
                success=True,
                message="Restauration réussie. Redémarrez l'application pour continuer.",
                security_backup_path=security_backup_path,
                destination_warning=destination_warning,
            )
        finally:
            if temp_to_cleanup is not None:
                temp_to_cleanup.unlink(missing_ok=True)

    def _restore_backup_postgresql(self, backup_path: Path, settings: Settings) -> RestoreResult:
        """Pendant PostgreSQL de :meth:`_restore_backup_sqlite` (Lot E,
        §E.2.3) : même ordre strict (vérifier -> sauvegarde de sécurité ->
        remplacer), mais une différence délibérée à l'étape 3 — expliquée
        ci-dessous — tenant à une garantie plus forte offerte nativement
        par PostgreSQL."""
        pg = settings.postgresql
        if pg is None:
            message = "Aucune configuration PostgreSQL active : restauration impossible."
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message)

        # Décrypte d'abord vers une copie temporaire en clair si l'archive
        # est chiffrée (voir le manifeste) — même principe que
        # ``_restore_backup_sqlite``, ``pg_restore`` ne sachant lire
        # qu'une archive ``.dump`` en clair.
        try:
            plaintext_path, temp_to_cleanup = self._resolve_plaintext_path(backup_path)
        except (ValidationError, ArchiveEncryptionError) as exc:
            message = str(exc)
            self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message) from exc

        try:
            verification = pg_backup_engine.verify_backup_file(plaintext_path)
            if not verification.valid:
                message = "Sauvegarde invalide, restauration refusée : " + "; ".join(verification.errors)
                self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
                raise ValidationError(message)

            try:
                password = pg.resolve_password()
            except ValueError as exc:
                message = f"Restauration impossible : {exc}"
                self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
                raise ValidationError(message) from exc

            target = self._postgresql_target(settings)

            current_version = pg_backup_engine.get_live_alembic_version(target, password)
            needs_schema_upgrade = False
            if verification.alembic_version != current_version:
                # §3.10, même assouplissement que pour SQLite (voir
                # ``_restore_backup_sqlite`` pour le raisonnement complet) :
                # une sauvegarde dont la version est un ANCÊTRE strict de la
                # version actuelle reste restaurable, le schéma étant mis à
                # niveau vers ``head`` juste après via Alembic.
                if not init_db.is_ancestor_revision(verification.alembic_version, settings):
                    message = (
                        f"Version de schéma incompatible (sauvegarde : {verification.alembic_version!r}, "
                        f"base actuelle : {current_version!r}) — cette sauvegarde est plus récente que "
                        f"l'application actuelle, ou provient d'une version incompatible. Mettez à jour "
                        f"StockManager Desktop avant de réessayer. Restauration refusée."
                    )
                    self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
                    raise ValidationError(message)
                needs_schema_upgrade = True

            config = self._read_config()
            try:
                security_backup_path = pg_backup_engine.create_backup_file(
                    target, password, config.destination, prefix=pg_backup_engine.PRERESTORE_PREFIX,
                )
            except _POSTGRESQL_BACKUP_ERRORS as exc:
                message = f"Impossible de créer la sauvegarde de sécurité préalable : {exc}"
                self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=message)
                raise ValidationError(message) from exc

            # Même convention que pour SQLite : seuls les résultats définitifs
            # sont audités en base, la tentative elle-même part uniquement au
            # journal applicatif (voir le commentaire équivalent dans
            # ``_restore_backup_sqlite``).
            logger.info(
                "Tentative de restauration PostgreSQL depuis %s (utilisateur=%s).",
                backup_path, self._acting_user_id(),
            )

            db_session_module.reset_engine_cache()
            try:
                pg_backup_engine.restore_database_from_backup(target, password, plaintext_path)
            except _POSTGRESQL_BACKUP_ERRORS as exc:
                # Différence délibérée avec le cas SQLite : pg_restore est
                # invoqué avec ``--single-transaction`` (voir
                # ``postgresql_backup_engine.restore_database_from_backup``), qui
                # annule l'intégralité de la restauration côté serveur en cas
                # d'échec — la base active n'a par construction jamais été
                # modifiée. Aucune « restauration de secours » n'est donc
                # nécessaire ici (contrairement à SQLite, où un remplacement de
                # fichier partiel est possible) : la sauvegarde de sécurité
                # reste disponible par prudence, mais son usage resterait un
                # choix explicite de l'administrateur, jamais une tentative
                # automatique.
                db_session_module.reset_engine_cache()
                failure_message = (
                    f"Échec de la restauration : {exc} La base active n'a pas été modifiée "
                    f"(transaction annulée côté serveur) ; sauvegarde de sécurité disponible : "
                    f"{security_backup_path}."
                )
                logger.error(failure_message)
                self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=failure_message)
                return RestoreResult(
                    success=False, message=failure_message, security_backup_path=security_backup_path
                )

            if needs_schema_upgrade:
                # §3.10 : même principe que pour SQLite (voir
                # ``_restore_backup_sqlite``) — amène le schéma à ``head``
                # via les migrations Alembic normales, ``settings`` pointant
                # déjà vers la cible PostgreSQL active.
                try:
                    init_db.init_database(settings)
                except Exception as exc:
                    db_session_module.reset_engine_cache()
                    try:
                        pg_backup_engine.restore_database_from_backup(target, password, security_backup_path)
                        db_session_module.reset_engine_cache()
                        rollback_note = (
                            f"La base a été rétablie dans son état d'avant restauration (sauvegarde de "
                            f"sécurité : {security_backup_path})."
                        )
                    except _POSTGRESQL_BACKUP_ERRORS as rollback_exc:
                        rollback_note = (
                            f"Le rétablissement automatique de l'état précédent a lui-même échoué : "
                            f"{rollback_exc} Intervention manuelle nécessaire — la sauvegarde de sécurité "
                            f"reste disponible ici : {security_backup_path}."
                        )
                    failure_message = (
                        f"La sauvegarde a été restaurée mais la mise à niveau du schéma vers la version "
                        f"actuelle de l'application a échoué : {exc} {rollback_note}"
                    )
                    logger.error(failure_message)
                    self._audit("BACKUP_RESTORE_FAILURE", ResultatAudit.ECHEC, details=failure_message)
                    return RestoreResult(
                        success=False, message=failure_message, security_backup_path=security_backup_path
                    )

            db_session_module.reset_engine_cache()
            self._audit("BACKUP_RESTORE_SUCCESS", ResultatAudit.SUCCES, details=f"Restauré depuis {backup_path}.")
            logger.info(
                "Restauration PostgreSQL réussie depuis %s (sauvegarde de sécurité : %s).",
                backup_path, security_backup_path,
            )
            # §3.11 : même revalidation que pour SQLite (voir
            # ``_restore_backup_sqlite``) — ``parametres`` fait partie de
            # la base PostgreSQL restaurée, donc la destination des
            # sauvegardes locales vient elle aussi de changer.
            destination_warning = _check_destination_accessible(self._read_config().destination)
            return RestoreResult(
                success=True,
                message="Restauration réussie. Redémarrez l'application pour continuer.",
                security_backup_path=security_backup_path,
                destination_warning=destination_warning,
            )
        finally:
            if temp_to_cleanup is not None:
                temp_to_cleanup.unlink(missing_ok=True)
