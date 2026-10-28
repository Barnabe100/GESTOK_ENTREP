"""Supprime la fenêtre de console visible qu'un sous-processus externe
(``pg_dump``/``pg_restore``, voir
``app.services.backups.postgresql_backup_engine``) ouvrirait sinon sous
Windows — jamais un problème sous Linux/macOS, où aucun sous-processus
``subprocess`` n'ouvre de fenêtre.

``CREATE_NO_WINDOW`` (``creationflags``) empêche la création de la console
elle-même ; ``STARTUPINFO`` avec ``STARTF_USESHOWWINDOW``/``SW_HIDE`` est la
protection complémentaire usuelle (certains environnements Windows,
notamment un sous-processus lancé depuis un service, peuvent ignorer
``creationflags`` seul) — les deux sont transmis ensemble, sans incidence
l'un sur l'autre. N'a aucun effet sur le code de retour, la capture de
sortie (``stdout``/``stderr``) ni le mot de passe transmis par
l'environnement du sous-processus (``PGPASSWORD``, voir
``postgresql_backup_engine._run``) — ne change que la visibilité de la
fenêtre."""
from __future__ import annotations

import subprocess
import sys
from typing import Any


def no_console_window_kwargs() -> dict[str, Any]:
    """Arguments supplémentaires à fusionner dans un appel
    ``subprocess.run``/``subprocess.Popen`` — un dictionnaire vide hors
    Windows (aucun argument ajouté, comportement inchangé sur les autres
    plateformes)."""
    if sys.platform != "win32":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}
