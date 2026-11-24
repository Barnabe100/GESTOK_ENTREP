"""Verrou inter-processus par fichier — évite deux exécutions simultanées
de l'agent auxiliaire de sauvegarde (Mission « Sauvegarde automatique et
restauration », §4 : « éviter les exécutions simultanées », « prévoir un
mécanisme de verrouillage »), par exemple un déclenchement manuel pendant
que la tâche planifiée Windows est déjà en cours.

Mécanisme volontairement simple et portable (aucune dépendance
supplémentaire) : création atomique d'un fichier (``O_CREAT | O_EXCL``,
garantie par le système de fichiers, jamais une simple vérification
d'existence suivie d'une écriture — qui laisserait une fenêtre de
compétition entre deux processus) contenant le PID du détenteur. Un verrou
existant dont le PID ne correspond plus à aucun processus actif (processus
tué brutalement, redémarrage du poste sans nettoyage) est considéré comme
périmé et repris automatiquement — jamais laissé bloquer indéfiniment une
sauvegarde légitime pour cette seule raison.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


class ProcessLockHeldError(Exception):
    """Le verrou est déjà détenu par un processus réellement actif — à
    traiter comme un report propre (nouvelle tentative plus tard), jamais
    comme une erreur fatale."""


def _process_is_running(pid: int) -> bool:
    """Vrai si un processus portant ce PID existe actuellement sur ce
    poste — jamais utilisé seul pour décider d'une action destructive,
    uniquement pour distinguer un verrou légitime d'un verrou périmé."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        # PROCESS_QUERY_LIMITED_INFORMATION (0x1000) : droit minimal
        # suffisant pour vérifier l'existence d'un processus, jamais plus
        # (aucune action sur le processus trouvé) — évite toute dépendance
        # à pywin32 complet (ctypes seul, déjà disponible nativement).
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Existe mais appartient à un autre utilisateur.
    return True


class ProcessLock:
    """Verrou réutilisable autour d'un chemin de fichier donné — un chemin
    de verrou distinct par usage (ex. un verrou dédié pour l'agent de
    sauvegarde, jamais partagé avec un autre mécanisme)."""

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._acquired = False

    def acquire(self) -> bool:
        """Tente d'acquérir le verrou. Retourne ``False`` sans lever si un
        autre processus réellement actif le détient déjà — jamais une
        exception dans ce cas précis, pour laisser l'appelant décider
        (reporter, journaliser, abandonner) sans avoir à traiter une
        exception pour un cas parfaitement attendu."""
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return self._try_reclaim_stale_lock()
        try:
            os.write(fd, str(os.getpid()).encode("utf-8"))
        finally:
            os.close(fd)
        self._acquired = True
        return True

    def _try_reclaim_stale_lock(self) -> bool:
        """Un fichier de verrou existe déjà : vérifie si son détenteur est
        toujours actif. Si non (processus disparu) ou si le contenu est
        illisible/corrompu, le verrou est considéré périmé et repris —
        jamais laissé bloquer indéfiniment une sauvegarde légitime pour
        cette seule raison (voir la docstring de module)."""
        try:
            existing_pid = int(self._lock_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            existing_pid = -1
        if existing_pid > 0 and _process_is_running(existing_pid):
            return False
        try:
            self._lock_path.unlink()
        except OSError:
            return False
        return self.acquire()

    def release(self) -> None:
        """Libère le verrou si détenu par cette instance — sans effet
        sinon (jamais une erreur si déjà libéré, ou si cette instance ne
        l'a jamais acquis)."""
        if not self._acquired:
            return
        try:
            self._lock_path.unlink()
        except OSError:
            pass
        self._acquired = False

    def __enter__(self) -> "ProcessLock":
        if not self.acquire():
            raise ProcessLockHeldError(
                f"Une autre exécution détient déjà le verrou « {self._lock_path} »."
            )
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
