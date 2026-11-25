"""Point d'entrée pour l'exécution d'une sauvegarde planifiée en dehors de
l'application graphique (§8 du cahier des charges de la phase Sauvegardes).

Limitation analysée : une tâche planifiée *dans* l'application (minuteur
Qt dans ``MainWindow``) ne peut s'exécuter que si l'application est ouverte.
Pour couvrir le cas où StockManager Desktop est complètement fermé, cette
commande offre une intégration propre avec un exécuteur de tâches externe
(ex. le Planificateur de tâches Windows) : elle ne dépend d'aucun composant
Qt, uniquement de :class:`BackupService` (le même moteur, la même
configuration, le même audit que la sauvegarde manuelle et le minuteur
interne — aucune logique dupliquée).

Portée V1 (documentée explicitement, aucun service Windows n'est développé
dans cette phase) :
- l'application ouverte exécute les sauvegardes planifiées via un minuteur
  interne (voir ``MainWindow``) ;
- l'application fermée nécessite qu'un administrateur enregistre CETTE
  commande auprès du Planificateur de tâches Windows (ou de l'équivalent
  cron/launchd sur d'autres systèmes), par exemple :

      schtasks /create /tn "StockManager - Sauvegarde planifiee" ^
          /tr "\"C:\\chemin\\vers\\python.exe\" -m app.backup_cli" ^
          /sc daily /st 02:00

  Cet enregistrement reste un geste d'administration système manuel, hors
  périmètre automatisé de cette phase.

Cette commande respecte elle-même la configuration enregistrée
(activation/fréquence/heure/rétention) : un appel qui tombe en dehors de la
fréquence configurée, ou alors que la sauvegarde automatique est désactivée,
ne fait rien (voir ``BackupService.run_scheduled_backup_if_due``) — il est
donc sûr de planifier cette commande plus souvent que la fréquence réelle
souhaitée (ex. toutes les heures), la commande elle-même se charge de ne
sauvegarder qu'au bon moment.

Mission corrective « Fiabilisation du module de sauvegarde », §3.3 : ajoute
la sous-commande ``recover``, un outil de secours autonome lorsque
StockManager Desktop ne démarre plus du tout (base SQLite active
inexploitable) — l'assistant de restauration habituel de l'interface est
alors hors de portée. Toute la logique vit dans
``app.services.backups.recovery`` (jamais de session SQLAlchemy requise
contre la base active, potentiellement cassée — voir sa docstring) :

    python -m app.backup_cli recover --list
    python -m app.backup_cli recover --restore "<chemin_de_l_archive>"

Sans argument, le comportement par défaut (sauvegarde planifiée) reste
inchangé — toute installation existante ayant déjà enregistré cette
commande auprès du Planificateur de tâches Windows continue de fonctionner
à l'identique.
"""
from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.services.backups.backup_service import BackupService
from app.utils.logging_config import get_logger, setup_logging


def _run_scheduled_backup() -> int:
    settings = get_settings()
    setup_logging(settings)
    logger = get_logger("backup_cli")

    # Aucun utilisateur connecté dans ce contexte (exécution système) :
    # PermissionService.current_user est None, ce qui est attendu — la
    # sauvegarde planifiée (run_scheduled_backup_if_due) ne vérifie
    # volontairement aucune permission, contrairement aux actions manuelles.
    service = BackupService(PermissionService(AuthService(settings)), settings=settings)

    result = service.run_scheduled_backup_if_due()
    if result is None:
        logger.info("Sauvegarde planifiée : rien à faire (désactivée ou hors échéance).")
        return 0
    if not result.success:
        logger.error("Sauvegarde planifiée échouée : %s", result.message)
        return 1
    logger.info("Sauvegarde planifiée réussie : %s", result.file_path)
    return 0


def _run_recover(args: argparse.Namespace) -> int:
    """Jamais de ``setup_logging``/journal applicatif ici (voir la
    docstring de module : la base active peut être cassée, et cette
    commande doit rester utilisable même si l'infrastructure habituelle de
    l'application ne fonctionne pas) — uniquement des messages écrits
    directement sur la sortie standard/d'erreur, pour un administrateur
    lisant un terminal, pas un journal applicatif."""
    from pathlib import Path

    from app.services.backups import recovery

    settings = get_settings()
    destination = recovery.resolve_recovery_destination(settings)

    if args.list or not args.restore:
        backups = recovery.list_recoverable_backups(destination)
        if not backups:
            print(f"Aucune sauvegarde de sécurité trouvée dans « {destination} ».")
            return 0
        print(f"Sauvegardes de sécurité disponibles dans « {destination} » :")
        for entry in backups:
            status = "valide" if entry.valid else "INVALIDE — " + "; ".join(entry.errors)
            print(f"  {entry.path}  ({entry.modified_at:%d/%m/%Y %H:%M:%S}, {entry.size_bytes} octets) — {status}")
        if not args.restore:
            print(
                "\nPour restaurer l'une de ces sauvegardes : "
                "python -m app.backup_cli recover --restore \"<chemin ci-dessus>\""
            )
            return 0

    backup_path = Path(args.restore)
    if not backup_path.is_file():
        print(f"Erreur : « {backup_path} » n'est pas un fichier accessible.", file=sys.stderr)
        return 1

    print(f"Restauration de « {settings.db_path} » depuis « {backup_path} »…")
    result = recovery.restore_from_recovery(backup_path, settings.db_path)
    print(result.message)
    if not result.success:
        print("Échec — la base active n'a pas été modifiée (voir le message ci-dessus).", file=sys.stderr)
        return 1
    print("Restauration réussie. Vous pouvez maintenant relancer StockManager Desktop normalement.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.backup_cli")
    subparsers = parser.add_subparsers(dest="command")

    recover_parser = subparsers.add_parser(
        "recover",
        help="Récupération autonome depuis une sauvegarde de sécurité pré-restauration (§3.3).",
    )
    recover_parser.add_argument(
        "--list", action="store_true", help="Lister les sauvegardes de sécurité disponibles.",
    )
    recover_parser.add_argument(
        "--restore", metavar="CHEMIN", help="Restaurer la base active depuis cette sauvegarde de sécurité.",
    )

    args = parser.parse_args(argv)
    if args.command == "recover":
        return _run_recover(args)
    return _run_scheduled_backup()


if __name__ == "__main__":
    sys.exit(main())
