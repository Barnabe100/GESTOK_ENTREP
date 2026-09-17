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
"""
from __future__ import annotations

import sys

from app.config import get_settings
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.services.backups.backup_service import BackupService
from app.utils.logging_config import get_logger, setup_logging


def main() -> int:
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


if __name__ == "__main__":
    sys.exit(main())
