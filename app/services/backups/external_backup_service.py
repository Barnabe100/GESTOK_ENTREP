"""Orchestration de la protection externe (Mission « Sauvegarde automatique
et restauration », §B/§4) : copie de la dernière sauvegarde locale validée
vers un support externe (clé USB, disque externe), avec sa propre
politique de conservation (30 à 50 archives), et gestion de la tâche
planifiée Windows qui déclenche cette copie même StockManager fermé.

Réutilise au maximum ce qui existe déjà, jamais une deuxième architecture
de sauvegarde :
- :mod:`app.services.backups.backup_engine`/``postgresql_backup_engine``
  pour lister/vérifier les fichiers (même mécanique que les sauvegardes
  locales — ce module ne sait créer AUCUNE sauvegarde lui-même, il ne fait
  jamais que copier une sauvegarde locale déjà créée et déjà validée par
  :class:`~app.services.backups.backup_service.BackupService`) ;
- :mod:`app.services.backups.archive_manifest` pour l'empreinte et les
  métadonnées (la copie externe emporte le manifeste de l'archive locale
  tel quel — mêmes octets, même empreinte, jamais régénéré) ;
- :mod:`app.services.backups.external_media` pour retrouver le support par
  son marqueur, jamais une lettre de lecteur fixe ;
- :mod:`app.services.backups.scheduled_task_manager` pour la tâche
  Windows ;
- ``ParameterRepository``/``AuditLog`` pour la configuration et la
  traçabilité, exactement comme ``BackupService``.

Invariant central (§4 du mandat, points 6-10) : une sauvegarde locale n'est
jamais considérée « due à copier » tant qu'elle n'a pas déjà un manifeste
valide (donc déjà créée ET déjà vérifiée par ``BackupService``) — ce module
ne vérifie jamais lui-même qu'une sauvegarde est « terminée » par une
heuristique de date de modification : l'existence d'un manifeste valide EST
la preuve qu'elle est terminée et validée (le manifeste n'est écrit qu'en
tout dernier, voir ``BackupService._create_backup``). Aucune suppression
d'ancienne copie externe n'a jamais lieu avant que la nouvelle copie soit
elle-même vérifiée par empreinte (§4, point 10 — jamais l'inverse)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from app.config.settings import Settings, get_settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.repositories.parameter_repository import ParameterRepository
from app.services.auth.permission_service import PermissionService
from app.services.backups import archive_manifest, backup_engine, temp_cleanup
from app.services.backups import postgresql_backup_engine as pg_backup_engine
from app.services.backups import scheduled_task_manager
from app.services.backups.backup_service import BackupEntry, BackupService
from app.services.backups import external_media
from app.services.backups.external_media import (
    DriveInfo,
    check_root_accessible,
    create_marker,
    find_marker_drive,
    list_candidate_drive_roots,
    normalize_drive_root,
    read_marker,
)
from app.utils.exceptions import UnsupportedPlatformError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.backups.external")

SCHEDULED_TASK_NAME = "StockManager - Sauvegarde automatique"
# Mission corrective « Fiabilisation du module de sauvegarde », §3.4/§3.5/
# §3.6 : tâche complémentaire, déclenchée à chaque ouverture de session
# plutôt qu'à heure fixe — sert uniquement de rattrapage (sauvegarde locale
# manquée la veille, ou nouvelle tentative de copie externe après un échec
# le même jour), jamais à la place de la tâche quotidienne ci-dessus :
# même agent (``run_cycle``), qui décide lui-même s'il y a réellement
# quelque chose à faire (voir ``BackupService._is_due``/
# ``ExternalBackupService.run_scheduled_external_copy_if_due``) — jamais
# une sauvegarde/copie supplémentaire inutile du seul fait de cette
# seconde tâche.
SCHEDULED_TASK_NAME_LOGON = "StockManager - Sauvegarde automatique (ouverture de session)"

_KEY_ENABLED = "backup.external.enabled"
_KEY_MARKER_ID = "backup.external.marker_id"
_KEY_LABEL = "backup.external.label"
_KEY_RETENTION = "backup.external.retention"
_KEY_LAST_RUN_AT = "backup.external.last_run_at"
_KEY_LAST_RESULT = "backup.external.last_result"
# Mission corrective « Fiabilisation du module de sauvegarde », §3.6 :
# ``_KEY_LAST_AUTO_RUN_DATE`` (seule clé existant avant ce correctif) ne
# distinguait pas une TENTATIVE d'un SUCCÈS — elle était posée à la date du
# jour que la copie réussisse ou échoue, empêchant toute nouvelle tentative
# le même jour même après un échec dû à la seule absence transitoire du
# support (ex. débranché à l'heure planifiée, reconnecté peu après).
# ``_KEY_LAST_AUTO_SUCCESS_DATE`` ne retient désormais que les succès —
# jamais plus d'une copie externe RÉUSSIE par jour calendaire (inchangé),
# mais un échec n'empêche plus plusieurs tentatives le même jour.
_KEY_LAST_AUTO_SUCCESS_DATE = "backup.external.last_auto_success_date"
# Mission corrective, §3.5 : heure utilisée lors de la dernière création/
# réparation réussie de la tâche planifiée Windows — comparée à l'heure
# actuellement configurée (``BackupService.get_config().time_of_day``)
# pour détecter une désynchronisation (voir
# :meth:`ExternalBackupService.is_scheduled_task_time_synchronized`),
# jamais lue depuis Windows lui-même (``schtasks /query`` n'expose pas
# l'heure du déclencheur de façon simple et fiable, seulement sa prochaine
# exécution calculée, qui dépend de la date du jour).
_KEY_TASK_CONFIGURED_TIME = "backup.external.task_configured_time"

MIN_RETENTION = 30
MAX_RETENTION = 50
DEFAULT_RETENTION = 30

_EXTERNAL_SUBDIR = "StockManager_Sauvegardes"


@dataclass(frozen=True)
class ExternalBackupConfig:
    """Configuration de la protection externe, persistée dans
    ``parametres`` — ``marker_id`` vide signifie « aucun support encore
    configuré » (jamais ``None`` en base, pour rester une simple chaîne
    comme le reste de ce mécanisme de configuration)."""

    enabled: bool
    marker_id: str
    label: str
    retention: int
    last_run_at: Optional[str]
    last_result: Optional[str]

    @property
    def is_configured(self) -> bool:
        return bool(self.marker_id)


@dataclass(frozen=True)
class ExternalCopyResult:
    success: bool
    message: str
    file_path: Optional[Path] = None


class ExternalBackupService:
    def __init__(
        self, backup_service: BackupService, permission_service: PermissionService,
        settings: Optional[Settings] = None,
        *, media_roots_provider: Optional[Callable[[], list[Path]]] = None,
    ) -> None:
        self._backup_service = backup_service
        self._permissions = permission_service
        self._settings = settings
        # Jamais appelé directement ici (spécifique Windows, liste vide
        # hors Windows) : seulement au moment précis de chercher le
        # support. Un fournisseur injecté (tests) permet de simuler des
        # racines de support arbitraires sans dépendre de lettres de
        # lecteur Windows réelles.
        self._media_roots_provider = media_roots_provider or list_candidate_drive_roots

    def _effective_settings(self) -> Settings:
        return self._settings or get_settings()

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, action: str, resultat: ResultatAudit, details: Optional[str] = None) -> None:
        with session_scope(self._settings) as session:
            session.add(
                AuditLog(
                    user_id=self._acting_user_id(), action=action, entite="sauvegardes_externes",
                    entite_id=None, resultat=resultat, details=details,
                )
            )

    # -- configuration --------------------------------------------------------

    def get_config(self) -> ExternalBackupConfig:
        self._permissions.require_permission("BACKUP_VIEW")
        return self._read_config()

    def _read_config(self) -> ExternalBackupConfig:
        with session_scope(self._settings) as session:
            repo = ParameterRepository(session)
            enabled = (repo.get_value(_KEY_ENABLED) or "false") == "true"
            marker_id = repo.get_value(_KEY_MARKER_ID) or ""
            label = repo.get_value(_KEY_LABEL) or ""
            retention_raw = repo.get_value(_KEY_RETENTION)
            retention = int(retention_raw) if retention_raw else DEFAULT_RETENTION
            last_run_at = repo.get_value(_KEY_LAST_RUN_AT)
            last_result = repo.get_value(_KEY_LAST_RESULT)
        return ExternalBackupConfig(
            enabled=enabled, marker_id=marker_id, label=label, retention=retention,
            last_run_at=last_run_at, last_result=last_result,
        )

    def list_available_drives(self) -> list[DriveInfo]:
        """Mission corrective « Correction et validation du module de
        sauvegarde sous Windows », §2.4 : remplace le sélecteur de dossier
        générique — l'utilisateur choisit désormais un lecteur réellement
        identifié (lettre, type, étiquette), jamais un chemin arbitraire.
        Inclut les clés USB ET les disques durs externes (souvent
        rapportés ``DRIVE_FIXED`` par Windows), exclut le disque système et
        les destinations inappropriées (réseau, optique, RAM) — voir
        ``external_media.list_drives_with_info``."""
        self._permissions.require_permission("BACKUP_VIEW")
        return external_media.list_drives_with_info(candidate_roots=self._media_roots_provider())

    def configure_media(self, drive_root: Path, label: str) -> ExternalBackupConfig:
        """Associe (ou ré-associe) un support externe à StockManager —
        jamais une simple écriture suivie d'une confirmation aveugle
        (mission corrective, §1/§3.1 : le défaut diagnostiqué était
        exactement « succès affiché, puis test d'accessibilité en échec
        immédiat »). Pipeline strict, chaque étape devant réussir avant la
        suivante :

        1. normaliser ``drive_root`` vers la racine canonique de son
           lecteur (``external_media.normalize_drive_root`` — élimine la
           cause racine : une lettre sans barre finale, ou un sous-dossier,
           écrivaient le marqueur à un endroit différent de celui où la
           recherche ultérieure le cherche) ;
        2. vérifier que cette racine existe et accepte réellement
           l'écriture (``external_media.check_root_accessible``) ;
        3. écrire le marqueur (``create_marker`` — remplace tout marqueur
           déjà présent, permet de ré-associer un support déjà utilisé,
           jamais les sauvegardes déjà présentes dessus, que cette méthode
           ne touche jamais) ;
        4. RELIRE immédiatement ce marqueur et comparer son identifiant à
           celui qui vient d'être écrit — jamais une confiance aveugle dans
           le seul fait que l'écriture n'a pas levé d'exception ;
        5. n'enregistrer la configuration, auditer un succès et retourner
           qu'après cette relecture positive."""
        self._permissions.require_permission("BACKUP_EXTERNAL_CONFIGURE")
        label_text = (label or "").strip()
        if not label_text:
            raise ValidationError("Le libellé du support externe est obligatoire.")

        try:
            root = normalize_drive_root(drive_root)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        inaccessible_reason = check_root_accessible(root)
        if inaccessible_reason is not None:
            raise ValidationError(f"Support externe refusé : {inaccessible_reason}")

        try:
            marker = create_marker(root, label_text)
        except OSError as exc:
            raise ValidationError(f"Impossible d'écrire sur le support choisi : {exc}") from exc

        reread = read_marker(root)
        if reread is None or reread.marker_id != marker.marker_id:
            raise ValidationError(
                "Le marqueur d'identification n'a pas pu être relu après son écriture sur "
                f"« {root} » — le support ne peut pas être configuré en toute confiance. Réessayez, "
                "et si le problème persiste, vérifiez que le support n'est pas en lecture seule ou "
                "qu'aucun antivirus ne bloque l'écriture."
            )

        with session_scope(self._settings) as session:
            repo = ParameterRepository(session)
            repo.set_value(_KEY_MARKER_ID, marker.marker_id)
            repo.set_value(_KEY_LABEL, marker.label)

        self._audit(
            "BACKUP_EXTERNAL_CONFIGURE", ResultatAudit.SUCCES,
            details=f"Support configuré et vérifié : {label_text} ({root}).",
        )
        logger.info("Support externe configuré et vérifié : %s (%s, %s).", label_text, marker.marker_id, root)
        return self._read_config()

    def update_config(self, *, enabled: bool, retention: int) -> ExternalBackupConfig:
        """Active/désactive la protection externe et règle sa rétention
        (toujours entre :data:`MIN_RETENTION` et :data:`MAX_RETENTION`, §B
        du mandat). Refuse d'activer sans support déjà configuré (rien à
        copier vers nulle part) — jamais une activation silencieusement
        sans effet."""
        self._permissions.require_permission("BACKUP_EXTERNAL_CONFIGURE")
        if not (MIN_RETENTION <= retention <= MAX_RETENTION):
            raise ValidationError(
                f"La rétention externe doit être comprise entre {MIN_RETENTION} et {MAX_RETENTION} "
                f"(valeur reçue : {retention})."
            )
        current = self._read_config()
        if enabled and not current.is_configured:
            raise ValidationError(
                "Choisissez d'abord un support externe avant d'activer la protection externe."
            )

        with session_scope(self._settings) as session:
            repo = ParameterRepository(session)
            repo.set_value(_KEY_ENABLED, "true" if enabled else "false")
            repo.set_value(_KEY_RETENTION, str(retention))

        self._audit("BACKUP_EXTERNAL_CONFIG_UPDATE", ResultatAudit.SUCCES)
        logger.info("Configuration de la protection externe mise à jour (activée=%s).", enabled)
        return self._read_config()

    # -- support externe --------------------------------------------------------

    def find_current_media_root(self) -> Optional[Path]:
        """Chemin actuel du support configuré, ou ``None`` s'il est absent/
        inaccessible — jamais une lettre de lecteur mémorisée, toujours
        retrouvé par son marqueur (voir ``external_media.find_marker_drive``)."""
        config = self._read_config()
        if not config.is_configured:
            return None
        return find_marker_drive(config.marker_id, candidate_roots=self._media_roots_provider())

    def test_media_accessible(self) -> bool:
        self._permissions.require_permission("BACKUP_VIEW")
        return self.find_current_media_root() is not None

    def _external_destination(self, media_root: Path) -> Path:
        return media_root / _EXTERNAL_SUBDIR

    # -- historique ---------------------------------------------------------------

    def list_external_backups(self) -> list[BackupEntry]:
        """Même forme que ``BackupService.list_backups`` — liste vide
        (jamais une exception) si le support n'est actuellement pas
        accessible : l'historique externe est alors simplement invisible
        tant que le support n'est pas rebranché, jamais une erreur."""
        self._permissions.require_permission("BACKUP_VIEW")
        media_root = self.find_current_media_root()
        if media_root is None:
            return []
        destination = self._external_destination(media_root)
        entries = [BackupEntry("sqlite", info) for info in backup_engine.list_backup_files(destination)]
        entries += [BackupEntry("postgresql", info) for info in pg_backup_engine.list_backup_files(destination)]
        return sorted(entries, key=lambda entry: entry.info.name, reverse=True)

    # -- copie ----------------------------------------------------------------------

    def copy_now(self) -> ExternalCopyResult:
        self._permissions.require_permission("BACKUP_CREATE")
        return self._run_copy(action="BACKUP_EXTERNAL_MANUAL")

    def run_scheduled_external_copy_if_due(self) -> Optional[ExternalCopyResult]:
        """Appelée par l'agent auxiliaire (§4 du mandat) — aucune
        vérification de permission (opération système, même convention que
        ``BackupService.run_scheduled_backup_if_due``). Retourne ``None``
        si la protection externe est désactivée ou si une copie a déjà
        RÉUSSI aujourd'hui (sûr d'appeler cette méthode plus souvent que
        nécessaire — jamais plus d'une copie réellement réussie par jour
        calendaire).

        Mission corrective, §3.6 : un échec (ex. support absent à l'heure
        planifiée) ne pose jamais cette date — une nouvelle tentative reste
        possible plus tard le même jour calendaire si cette méthode est
        appelée à nouveau (ex. le support est reconnecté, ou une seconde
        tâche planifiée de rattrapage se déclenche — voir
        ``ExternalBackupService.configure_scheduled_task``, §3.5 du même
        mandat), jamais bloquée par le seul échec précédent de la même
        journée."""
        config = self._read_config()
        if not config.enabled or not config.is_configured:
            return None

        today = datetime.now().date().isoformat()
        with session_scope(self._settings) as session:
            last_success_date = ParameterRepository(session).get_value(_KEY_LAST_AUTO_SUCCESS_DATE)
        if last_success_date == today:
            return None

        result = self._run_copy(action="BACKUP_EXTERNAL_AUTO")
        if result.success:
            with session_scope(self._settings) as session:
                ParameterRepository(session).set_value(_KEY_LAST_AUTO_SUCCESS_DATE, today)
        return result

    def _backup_lock(self):
        """Même verrou partagé que ``BackupService`` (mission corrective,
        §3.7 — voir sa docstring équivalente) : jamais une copie externe en
        même temps qu'une création de sauvegarde locale ou une
        restauration, qu'elles proviennent de l'agent auxiliaire ou d'une
        action manuelle de l'interface. Réentrant au sein d'un même
        processus (voir ``ProcessLock``) : l'agent, qui détient déjà ce
        verrou pour tout son cycle, ne se bloque jamais lui-même en
        appelant cette méthode."""
        from app.utils.process_lock import BACKUP_LOCK_FILENAME, ProcessLock

        return ProcessLock(self._effective_settings().data_dir / BACKUP_LOCK_FILENAME)

    def cleanup_orphaned_temp_files(self) -> list[Path]:
        """Mission corrective, §3.13 : même principe que
        ``BackupService.cleanup_orphaned_temp_files`` (voir sa docstring),
        appliqué au dossier de destination sur le support externe — rien
        à faire (liste vide, jamais une erreur) si le support n'est
        actuellement ni configuré ni branché : un support externe peut
        rester débranché longtemps entre deux cycles sans que cela ne
        soit jamais considéré comme un problème."""
        lock = self._backup_lock()
        if not lock.acquire():
            return []
        try:
            media_root = self.find_current_media_root()
            if media_root is None:
                return []
            return temp_cleanup.cleanup_orphaned_temp_files(self._external_destination(media_root))
        finally:
            lock.release()

    def _run_copy(self, *, action: str) -> ExternalCopyResult:
        lock = self._backup_lock()
        if not lock.acquire():
            return ExternalCopyResult(
                False,
                "Une autre opération de sauvegarde ou de restauration est déjà en cours sur ce "
                "poste. Réessayez dans quelques instants.",
            )
        try:
            return self._run_copy_locked(action=action)
        finally:
            lock.release()

    def _run_copy_locked(self, *, action: str) -> ExternalCopyResult:
        """Corps de :meth:`_run_copy`, isolé pour que le verrou (ci-dessus)
        entoure strictement tout le travail — jamais de code mutatif hors
        de sa portée."""
        config = self._read_config()
        if not config.is_configured:
            return self._finish_copy(ExternalCopyResult(False, "Aucun support externe configuré."), action)

        media_root = self.find_current_media_root()
        if media_root is None:
            # §4, point 4/point « si le support est absent, ne pas
            # considérer l'opération comme réussie » : jamais une
            # suppression, jamais une exception — un échec journalisé,
            # réessayé automatiquement à la prochaine échéance planifiée.
            return self._finish_copy(
                ExternalCopyResult(False, f"Support externe « {config.label} » introuvable ou inaccessible."),
                action,
            )

        latest = self._latest_validated_local_backup()
        if latest is None:
            return self._finish_copy(
                ExternalCopyResult(False, "Aucune sauvegarde locale validée disponible à copier."), action
            )

        destination = self._external_destination(media_root)
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return self._finish_copy(
                ExternalCopyResult(False, f"Impossible d'écrire sur le support externe : {exc}"), action
            )

        try:
            copied_path = self._copy_file_atomically(latest.info.path, destination / latest.info.name)
            manifest_source = archive_manifest.manifest_path_for(latest.info.path)
            if manifest_source.is_file():
                self._copy_file_atomically(
                    manifest_source, archive_manifest.manifest_path_for(copied_path)
                )
        except OSError as exc:
            return self._finish_copy(
                ExternalCopyResult(False, f"Échec de la copie vers le support externe : {exc}"), action
            )

        # Vérification de la copie avant toute suppression (§4, point 10) :
        # ré-empreinte le fichier copié et le compare à celui du fichier
        # source — jamais seulement une comparaison de taille.
        source_hash = archive_manifest.compute_sha256(latest.info.path)
        copied_hash = archive_manifest.compute_sha256(copied_path)
        if source_hash != copied_hash:
            copied_path.unlink(missing_ok=True)
            archive_manifest.delete_manifest_for(copied_path)
            return self._finish_copy(
                ExternalCopyResult(False, "La copie externe ne correspond pas à la sauvegarde source — rejetée."),
                action,
            )

        deleted = _apply_retention_for_engine(latest.engine, destination, config.retention)
        if deleted:
            for deleted_path in deleted:
                archive_manifest.delete_manifest_for(deleted_path)
            self._audit(
                "BACKUP_EXTERNAL_ROTATION", ResultatAudit.SUCCES,
                details=f"{len(deleted)} sauvegarde(s) externe(s) supprimée(s).",
            )

        return self._finish_copy(
            ExternalCopyResult(True, "Copie externe réussie.", file_path=copied_path), action
        )

    def _finish_copy(self, result: ExternalCopyResult, action: str) -> ExternalCopyResult:
        now = datetime.now()
        with session_scope(self._settings) as session:
            repo = ParameterRepository(session)
            repo.set_value(_KEY_LAST_RUN_AT, now.isoformat())
            repo.set_value(_KEY_LAST_RESULT, result.message)
        if result.success:
            logger.info("Copie externe réussie : %s", result.file_path)
            self._audit(f"{action}_SUCCESS", ResultatAudit.SUCCES, details=str(result.file_path))
        else:
            logger.error("Copie externe échouée : %s", result.message)
            self._audit(f"{action}_FAILURE", ResultatAudit.ECHEC, details=result.message)
        return result

    def _latest_validated_local_backup(self) -> Optional[BackupEntry]:
        """La sauvegarde locale la plus récente portant un manifeste valide
        — jamais une sauvegarde encore en cours de création (le manifeste
        n'est écrit qu'après création ET vérification réussies, voir la
        docstring de module) ni une sauvegarde dont l'empreinte ne
        correspond plus à son manifeste (altérée depuis)."""
        for entry in self._backup_service.list_backups_for_automation():
            manifest_check = archive_manifest.verify_manifest_for(entry.info.path)
            if manifest_check.present and manifest_check.hash_matches:
                return entry
        return None

    @staticmethod
    def _copy_file_atomically(source: Path, destination: Path) -> Path:
        """Copie ``source`` vers ``destination`` — écrit d'abord dans un
        fichier temporaire du même répertoire que ``destination``, ne
        renomme (``os.replace``, atomique) qu'une fois la copie terminée :
        jamais de fichier partiellement copié visible sous le nom final en
        cas d'échec (même convention que ``postgresql_backup_engine``)."""
        import os
        import shutil
        import tempfile

        fd, tmp_path_str = tempfile.mkstemp(dir=str(destination.parent), prefix=f".{destination.name}_", suffix=".tmp")
        os.close(fd)
        tmp_path = Path(tmp_path_str)
        try:
            shutil.copyfile(source, tmp_path)
            os.replace(tmp_path, destination)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return destination

    # -- tâche planifiée Windows -----------------------------------------------------

    def scheduled_task_status(self) -> scheduled_task_manager.ScheduledTaskStatus:
        self._permissions.require_permission("BACKUP_VIEW")
        return scheduled_task_manager.query_task_status(SCHEDULED_TASK_NAME)

    def configure_scheduled_task(self, time_of_day: str) -> None:
        """Crée ou répare DEUX tâches planifiées Windows (§4 du mandat
        initial, §3.5 du mandat correctif) :
        - ``SCHEDULED_TASK_NAME`` : quotidienne à ``time_of_day``, couvre à
          la fois la sauvegarde locale ET la copie externe (décision
          d'architecture validée : une seule tâche quotidienne plutôt que
          deux tâches distinctes à administrer séparément) ;
        - ``SCHEDULED_TASK_NAME_LOGON`` : à l'ouverture de session,
          rattrapage uniquement (voir sa constante ci-dessus) — même agent,
          jamais une seconde logique.

        Les deux doivent réussir pour que l'opération soit considérée
        réussie — jamais une réussite partielle silencieuse : en cas
        d'échec de l'une ou l'autre, aucune n'est considérée configurée du
        point de vue de l'utilisateur (relancer « Configurer/réparer… »
        est sans risque, ``create_or_repair_task`` étant idempotent)."""
        self._permissions.require_permission("BACKUP_EXTERNAL_CONFIGURE")
        from app.backup_external_agent_cli import resolve_agent_invocation

        executable, arguments = resolve_agent_invocation()
        try:
            scheduled_task_manager.create_or_repair_task(
                SCHEDULED_TASK_NAME, executable, arguments, time_of_day
            )
            scheduled_task_manager.create_or_repair_task(
                SCHEDULED_TASK_NAME_LOGON, executable, arguments, time_of_day,
                schedule=scheduled_task_manager.SCHEDULE_ONLOGON,
            )
        except (scheduled_task_manager.ScheduledTaskError, UnsupportedPlatformError) as exc:
            self._audit("BACKUP_SCHEDULED_TASK_CONFIGURE_FAILURE", ResultatAudit.ECHEC, details=str(exc))
            raise ValidationError(str(exc)) from exc

        with session_scope(self._settings) as session:
            ParameterRepository(session).set_value(_KEY_TASK_CONFIGURED_TIME, time_of_day)
        self._audit("BACKUP_SCHEDULED_TASK_CONFIGURE_SUCCESS", ResultatAudit.SUCCES)
        logger.info("Tâches planifiées Windows configurées/réparées (quotidienne %s + ouverture de session).", time_of_day)

    def remove_scheduled_task(self) -> None:
        self._permissions.require_permission("BACKUP_EXTERNAL_CONFIGURE")
        try:
            scheduled_task_manager.delete_task(SCHEDULED_TASK_NAME)
            scheduled_task_manager.delete_task(SCHEDULED_TASK_NAME_LOGON)
        except (scheduled_task_manager.ScheduledTaskError, UnsupportedPlatformError) as exc:
            self._audit("BACKUP_SCHEDULED_TASK_REMOVE_FAILURE", ResultatAudit.ECHEC, details=str(exc))
            raise ValidationError(str(exc)) from exc
        self._audit("BACKUP_SCHEDULED_TASK_REMOVE_SUCCESS", ResultatAudit.SUCCES)
        logger.info("Tâches planifiées Windows supprimées.")

    def is_scheduled_task_time_synchronized(self) -> Optional[bool]:
        """Mission corrective, §3.5 : modifier l'heure dans l'écran de
        configuration locale puis cliquer seulement sur « Enregistrer »
        (voir ``BackupsPage._save_config``) ne met jamais à jour la tâche
        planifiée Windows déjà créée — ce contrôle permet à l'interface de
        le signaler explicitement plutôt que de laisser croire, à tort,
        qu'elles restent synchronisées. ``None`` si la tâche quotidienne
        n'existe pas encore (rien à comparer, pas une désynchronisation en
        soi) ; sinon ``True``/``False`` selon que l'heure actuellement
        configurée correspond toujours à celle utilisée lors de la
        dernière création/réparation réussie de la tâche."""
        self._permissions.require_permission("BACKUP_VIEW")
        status = scheduled_task_manager.query_task_status(SCHEDULED_TASK_NAME)
        if not status.exists:
            return None
        with session_scope(self._settings) as session:
            configured_time = ParameterRepository(session).get_value(_KEY_TASK_CONFIGURED_TIME)
        current_time = self._backup_service.get_config().time_of_day
        return configured_time == current_time


def _apply_retention_for_engine(engine: str, destination: Path, retention: int) -> list[Path]:
    """Sélectionne la politique de rétention du bon moteur (même motif de
    nommage mutuellement exclusif que ``BackupService.list_backups``,
    jamais mélangé) — fonction module-level, jamais dupliquée entre les
    deux branches."""
    if engine == "postgresql":
        return pg_backup_engine.apply_retention(destination, retention)
    return backup_engine.apply_retention(destination, retention)
