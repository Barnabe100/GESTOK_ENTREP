"""Récupération autonome après une base SQLite rendue inexploitable
(mission corrective « Fiabilisation du module de sauvegarde », §3.3) —
destinée exclusivement au scénario où StockManager Desktop ne démarre plus
du tout (base active corrompue/illisible) : l'assistant de restauration
habituel (voir ``app.views.backup_restore_wizard_dialog``) est alors hors
de portée, puisqu'il vit À L'INTÉRIEUR de l'application qui ne démarre
plus.

Différences volontaires et nécessaires avec ``BackupService`` :
- aucune session SQLAlchemy ouverte contre la base active (potentiellement
  celle-là même qui est cassée) n'est jamais requise pour FONCTIONNER —
  seule la résolution du dossier de sauvegardes tente une lecture de
  configuration, avec repli silencieux sur le dossier par défaut si cette
  lecture échoue (voir :func:`resolve_recovery_destination`) ;
- aucune vérification de permission (``PermissionService``) : par
  construction, personne ne peut se connecter si l'application ne démarre
  pas — exactement la même convention que
  ``BackupService.run_scheduled_backup_if_due``/``list_backups_for_automation``,
  poussée ici à son terme logique ;
- jamais de comparaison de version de schéma avec la base active (celle-ci
  est supposée cassée, donc pas d'information fiable à en tirer) : la
  restauration se fonde uniquement sur la vérification structurelle de
  l'archive choisie (déjà, par construction, une ancienne sauvegarde de
  sécurité pré-restauration créée et vérifiée par ``BackupService`` lui-même
  avant une restauration antérieure) ;
- portée volontairement limitée à SQLite (voir la docstring de
  :func:`restore_from_recovery`) : le scénario « la base locale empêche le
  démarrage » ne concerne par construction que ce moteur — en PostgreSQL,
  les données vivent sur le serveur, jamais dans le fichier local.

Réutilise entièrement la mécanique de fichiers existante
(``backup_engine``), jamais une seconde implémentation de la copie/
vérification/remplacement atomique."""
from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config.settings import Settings
from app.repositories.parameter_repository import ParameterRepository
from app.services.backups import backup_engine

_KEY_DESTINATION = "backup.destination"


def _default_destination(settings: Settings) -> Path:
    """Même calcul que ``BackupService._default_destination`` — jamais
    dupliqué autrement qu'en valeur littérale identique, puisqu'importer
    ``backup_service`` ici réintroduirait une dépendance à SQLAlchemy dans
    un module dont la raison d'être est justement de fonctionner sans elle."""
    return settings.data_dir / "backups"


def resolve_recovery_destination(settings: Settings) -> Path:
    """Dossier contenant les sauvegardes (donc les sauvegardes de sécurité
    pré-restauration à lister) — tente de lire la configuration
    enregistrée (``ParameterRepository``, même clé que ``BackupService``),
    mais ne lève jamais si cette lecture échoue (base active corrompue,
    verrouillée, ou toute autre erreur) : repli silencieux sur le dossier
    par défaut, qui reste correct pour toute installation n'ayant jamais
    personnalisé ce réglage — le cas le plus probable en pratique."""
    try:
        from app.db.session import session_scope

        with session_scope(settings) as session:
            value = ParameterRepository(session).get_value(_KEY_DESTINATION)
        if value:
            return Path(value)
    except Exception:  # noqa: BLE001 - toute erreur ici doit mener au repli, jamais remonter.
        pass
    return _default_destination(settings)


@dataclass(frozen=True)
class RecoverableBackup:
    """Une sauvegarde de sécurité pré-restauration candidate à la
    récupération — ``valid`` reflète uniquement la vérification
    structurelle SQLite (``PRAGMA integrity_check`` + tables attendues),
    jamais une comparaison de version de schéma (voir la docstring de
    module)."""

    path: Path
    size_bytes: int
    modified_at: datetime
    valid: bool
    errors: list[str]


def list_recoverable_backups(destination: Path) -> list[RecoverableBackup]:
    """Sauvegardes de sécurité pré-restauration SQLite présentes dans
    ``destination`` (préfixe ``stockmanager_prerestore_``), les plus
    récentes d'abord, chacune accompagnée du résultat de sa vérification
    structurelle. Liste vide (jamais une exception) si ``destination``
    n'existe pas ou ne contient aucune sauvegarde de ce type."""
    infos = backup_engine.list_backup_files(destination, prefix=backup_engine.PRERESTORE_PREFIX)
    results = []
    for info in infos:
        verification = backup_engine.verify_backup_file(info.path)
        results.append(
            RecoverableBackup(
                path=info.path, size_bytes=info.size_bytes, modified_at=info.modified_at,
                valid=verification.valid, errors=verification.errors,
            )
        )
    return results


@dataclass(frozen=True)
class RecoveryResult:
    success: bool
    message: str
    moved_aside_path: Optional[Path] = None


def restore_from_recovery(backup_path: Path, db_path: Path) -> RecoveryResult:
    """Restaure ``db_path`` (la base active, supposée inexploitable) à
    partir de ``backup_path`` (une sauvegarde choisie par l'administrateur,
    typiquement listée par :func:`list_recoverable_backups`) — SQLite
    uniquement (voir la docstring de module : le scénario visé — base
    locale empêchant le démarrage — ne concerne que ce moteur).

    Si ``db_path`` existe déjà (le cas normal : c'est la base cassée que
    l'on remplace), une COPIE en est d'abord faite de côté, jamais un
    déplacement (préfixe horodaté ``.corrompue-AAAAMMJJ_HHMMSS``) — pur
    filet de sécurité redondant : ``backup_engine.restore_database_from_backup``
    (réutilisé ici tel quel, jamais une seconde mécanique de restauration)
    garantit déjà par construction (§3.2 de la mission corrective) que
    ``db_path`` n'est jamais touché avant qu'une copie vérifiée de
    ``backup_path`` ne soit prête à la remplacer — donc jamais perdu même
    sans cette copie en cas d'échec. Elle reste néanmoins faite par
    prudence, au cas où l'administrateur réaliserait après coup avoir
    choisi la mauvaise archive malgré un succès apparent."""
    backup_path = Path(backup_path)
    db_path = Path(db_path)

    if backup_path.suffix != ".db":
        return RecoveryResult(
            success=False,
            message=(
                "Cette commande de récupération ne prend en charge que les sauvegardes SQLite "
                "(fichiers .db) — pour PostgreSQL, les données vivent sur le serveur, jamais "
                "dans un fichier local à récupérer de cette façon."
            ),
        )

    moved_aside_path: Optional[Path] = None
    if db_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        moved_aside_path = db_path.with_name(f"{db_path.name}.corrompue-{timestamp}")
        try:
            shutil.copy2(str(db_path), str(moved_aside_path))
        except OSError as exc:
            return RecoveryResult(
                success=False,
                message=f"Impossible de conserver une copie de la base actuelle avant restauration : {exc}",
            )

    try:
        backup_engine.restore_database_from_backup(backup_path, db_path)
    except (OSError, sqlite3.Error, backup_engine.RestoreValidationError, backup_engine.AtomicReplaceError) as exc:
        # db_path n'a, par construction, jamais été modifié dans ce cas
        # (voir la docstring ci-dessus) — la copie de prudence créée plus
        # haut n'était donc pas nécessaire pour ce résultat précis, mais
        # reste disponible sans inconvénient.
        return RecoveryResult(
            success=False, message=f"Échec de la restauration : {exc} La base active n'a pas été modifiée.",
            moved_aside_path=moved_aside_path,
        )

    message = f"Restauration réussie depuis {backup_path}."
    if moved_aside_path is not None:
        message += f" Une copie de l'ancienne base (avant récupération) a été conservée ici : {moved_aside_path}."
    return RecoveryResult(success=True, message=message, moved_aside_path=moved_aside_path)
