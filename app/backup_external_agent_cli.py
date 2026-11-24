"""Agent auxiliaire autonome de sauvegarde (Mission « Sauvegarde automatique
et restauration », §4) — invoqué quotidiennement par la tâche planifiée
Windows configurée depuis StockManager (voir
``ExternalBackupService.configure_scheduled_task``), sans jamais dépendre de
l'application graphique : aucun import PySide6/Qt dans ce module, à
l'identique de ``app/backup_cli.py`` (sauvegarde locale seule, existant
depuis la V1 — ce module le complète, ne le remplace pas).

Ce module couvre, dans l'ordre strict suivant (jamais inversé) :
1. Acquisition du verrou anti-concurrence (``app.utils.process_lock``) — si
   déjà détenu par un autre processus actif (ex. une copie manuelle lancée
   depuis l'interface pendant que la tâche planifiée se déclenche), abandon
   propre, jamais une erreur bruyante : la prochaine échéance planifiée
   réessaiera (§4, point « éviter les exécutions simultanées »).
2. Sauvegarde locale si due (``BackupService.run_scheduled_backup_if_due``,
   réutilisé tel quel — aucune logique de sauvegarde dupliquée ici).
3. Copie externe si due et activée
   (``ExternalBackupService.run_scheduled_external_copy_if_due``).

Décision d'architecture validée (une seule tâche Windows quotidienne
couvrant les deux étapes, plutôt que deux tâches distinctes) : garantit que
la sauvegarde locale elle-même s'exécute même si StockManager n'est jamais
ouvert un jour donné (critère de réussite n°1 de la mission), pas seulement
la copie externe.

Invocable de deux façons équivalentes :
- en développement/déploiement scripté, via un interpréteur Python système
  (``python -m app.backup_external_agent_cli``, même convention que
  ``app/backup_cli.py``) ;
- en production (poste client), via l'exécutable StockManager lui-même déjà
  packagé par PyInstaller (``StockManager.exe --run-backup-agent``) — voir
  :func:`resolve_agent_invocation`, qui détermine la ligne de commande à
  enregistrer dans la tâche planifiée Windows. ``app/main.py`` intercepte ce
  drapeau AVANT toute initialisation de ``QApplication`` (voir son
  ``if __name__ == "__main__":``) : l'exécutable gelé sert ainsi les deux
  usages (interface graphique normale, ou agent silencieux) sans packaging
  ni artefact PyInstaller distinct — un seul exécutable à maintenir, à
  mettre à jour, à signer."""
from __future__ import annotations

import sys

AGENT_FLAG = "--run-backup-agent"

_LOCK_FILENAME = "backup_agent.lock"


def resolve_agent_invocation() -> tuple[str, list[str]]:
    """Détermine la ligne de commande à enregistrer dans la tâche planifiée
    Windows (voir ``ExternalBackupService.configure_scheduled_task``) :
    l'exécutable StockManager lui-même packagé (``sys.executable``, qui
    pointe vers ``StockManager.exe`` une fois gelé par PyInstaller) avec le
    drapeau :data:`AGENT_FLAG`, ou en développement un interpréteur Python
    système exécutant ce module."""
    if getattr(sys, "frozen", False):
        return sys.executable, [AGENT_FLAG]
    return sys.executable, ["-m", "app.backup_external_agent_cli"]


def run_cycle(backup_service, external_service, logger) -> int:
    """Logique pure du cycle verrou -> sauvegarde locale si due -> copie
    externe si due (hors acquisition du verrou, voir :func:`run_agent`) —
    isolée pour rester testable avec des services déjà construits (``stack``
    de test), sans jamais appeler ``setup_logging`` ni en construire de
    nouveaux (la reconfiguration du logger racine est un effet global sur le
    processus, jamais souhaitable pendant une suite de tests — voir
    ``tests/test_backup_external_agent_cli.py``). Retourne un code de sortie
    non nul si l'une des deux étapes a échoué (jamais si l'une des deux
    était simplement « rien à faire », qui n'est jamais un échec)."""
    exit_code = 0

    local_result = backup_service.run_scheduled_backup_if_due()
    if local_result is None:
        logger.info("Sauvegarde locale planifiée : rien à faire (désactivée ou hors échéance).")
    elif not local_result.success:
        logger.error("Sauvegarde locale planifiée échouée : %s", local_result.message)
        exit_code = 1
    else:
        logger.info("Sauvegarde locale planifiée réussie : %s", local_result.file_path)

    external_result = external_service.run_scheduled_external_copy_if_due()
    if external_result is None:
        logger.info("Copie externe planifiée : rien à faire (désactivée, non configurée, ou déjà effectuée aujourd'hui).")
    elif not external_result.success:
        logger.error("Copie externe planifiée échouée : %s", external_result.message)
        exit_code = 1
    else:
        logger.info("Copie externe planifiée réussie : %s", external_result.file_path)

    return exit_code


def run_agent_locked(lock, backup_service, external_service, logger) -> int:
    """Isolé de :func:`run_agent` pour rester testable sans
    ``setup_logging`` ni construction des services système (même principe
    que :func:`run_cycle`, voir sa docstring et
    ``tests/test_backup_external_agent_cli.py``) : vérifie l'acquisition du
    verrou anti-concurrence (``lock``, déjà construit par l'appelant) avant
    toute exécution, délègue à :func:`run_cycle` uniquement si acquis, le
    libère toujours ensuite. Si le verrou est déjà détenu par une autre
    exécution (ex. une copie manuelle lancée depuis l'interface pendant que
    la tâche planifiée se déclenche), abandon propre sans erreur — jamais
    deux cycles en parallèle sur le même poste (§4/§8 du mandat)."""
    if not lock.acquire():
        logger.info("Agent de sauvegarde : une autre exécution est déjà en cours, abandon propre.")
        return 0
    try:
        return run_cycle(backup_service, external_service, logger)
    finally:
        lock.release()


def run_agent() -> int:
    """Point d'entrée réel : construit les services système (aucun
    utilisateur connecté — ``PermissionService.current_user`` est ``None``,
    ce qui est attendu, ni ``run_scheduled_backup_if_due`` ni
    ``run_scheduled_external_copy_if_due`` ne vérifient de permission, même
    convention que ``app/backup_cli.py``), puis délègue à
    :func:`run_agent_locked`."""
    from app.config import get_settings
    from app.services.auth.auth_service import AuthService
    from app.services.auth.permission_service import PermissionService
    from app.services.backups.backup_service import BackupService
    from app.services.backups.external_backup_service import ExternalBackupService
    from app.utils.logging_config import get_logger, setup_logging
    from app.utils.process_lock import ProcessLock

    settings = get_settings()
    setup_logging(settings)
    logger = get_logger("backup_external_agent")

    lock = ProcessLock(settings.data_dir / _LOCK_FILENAME)
    permissions = PermissionService(AuthService(settings))
    backup_service = BackupService(permissions, settings=settings)
    external_service = ExternalBackupService(backup_service, permissions, settings=settings)
    return run_agent_locked(lock, backup_service, external_service, logger)


def main() -> int:
    return run_agent()


if __name__ == "__main__":
    sys.exit(main())
