"""Nettoyage prudent des fichiers temporaires orphelins laissés par une
opération de sauvegarde/restauration/copie externe interrompue brutalement
(coupure de courant, fermeture forcée du processus, avant que son propre
bloc ``finally`` n'ait pu s'exécuter) — mission corrective « Fiabilisation
du module de sauvegarde », §3.13.

Tous les fichiers temporaires produits par ce module (voir
``backup_engine``, ``postgresql_backup_engine``, ``archive_encryption``,
``external_backup_service``) partagent la même convention de nommage : un
nom de fichier CACHÉ (préfixé d'un point, jamais visible dans l'historique
des sauvegardes ni dans un explorateur de fichiers par défaut) se
terminant par ``.tmp`` (``.creating.tmp``, ``.enc.tmp``, ``.dec.tmp``,
``.dump.tmp``, ou simplement ``.tmp`` selon l'opération — tous se
terminent littéralement par ces quatre caractères). Repérer ces deux
traits suffit donc à identifier sans ambiguïté un fichier temporaire
produit par StockManager, jamais un fichier déposé par un autre logiciel
dans le même dossier.

Jamais appelé sans que l'appelant détienne déjà le verrou partagé
anti-concurrence (§3.7, voir ``app.utils.process_lock``) : un fichier
temporaire plus vieux que le seuil mais appartenant à une opération
RÉELLEMENT en cours (improbable mais pas impossible pour une très grosse
base) ne pourrait alors jamais exister, puisque cette même opération
détiendrait déjà ce verrou — voir ``BackupService.cleanup_orphaned_temp_files``/
``ExternalBackupService.cleanup_orphaned_temp_files``, qui l'acquièrent
eux-mêmes avant d'appeler cette fonction."""
from __future__ import annotations

import time
from pathlib import Path

# Une heure : largement supérieur à la durée de toute opération normale,
# même une grosse base de données — jamais si court qu'une opération
# légitime mais lente puisse être confondue avec un orphelin.
_MIN_ORPHAN_AGE_SECONDS = 3600


def cleanup_orphaned_temp_files(directory: Path, *, min_age_seconds: int = _MIN_ORPHAN_AGE_SECONDS) -> list[Path]:
    """Supprime, dans ``directory`` (jamais récursivement dans ses
    sous-dossiers — chaque emplacement concerné est balayé explicitement
    par l'appelant), les fichiers temporaires orphelins plus vieux que
    ``min_age_seconds``. Ne lève jamais : un échec de suppression
    individuel (fichier verrouillé ailleurs, permissions) est
    silencieusement ignoré pour ce fichier précis, sans empêcher le
    nettoyage des autres. Retourne la liste de ceux effectivement
    supprimés, pour journalisation par l'appelant — jamais une suppression
    totalement silencieuse."""
    if not directory.is_dir():
        return []
    now = time.time()
    removed: list[Path] = []
    for entry in directory.iterdir():
        if not entry.name.startswith(".") or not entry.name.endswith(".tmp"):
            continue
        try:
            if not entry.is_file():
                continue
            age_seconds = now - entry.stat().st_mtime
        except OSError:
            continue
        if age_seconds < min_age_seconds:
            continue
        try:
            entry.unlink()
        except OSError:
            continue
        removed.append(entry)
    return removed
