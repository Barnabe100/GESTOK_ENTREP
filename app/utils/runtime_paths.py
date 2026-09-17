"""Chemins d'exécution, cohérents en développement et dans un exécutable
PyInstaller (§2/§11 du cahier des charges de la phase Packaging).

En développement, la racine du projet se déduit de l'arborescence source
(``Path(__file__)``). Dans un exécutable packagé, ce n'est plus valable : le
code Python est le plus souvent embarqué dans une archive compressée (PYZ),
et ``__file__`` ne correspond alors à aucun fichier réel sur disque. La
seule référence fiable pour localiser les fichiers non-Python embarqués
explicitement comme données (ressources Qt, ``alembic.ini``, ``migrations/``
— voir ``stockmanager.spec``) est ``sys._MEIPASS``, positionnée par le
bootloader PyInstaller aussi bien en mode ``onedir`` (dossier de
l'exécutable) qu'en mode ``onefile`` (dossier d'extraction temporaire).

N'utiliser cette fonction que pour retrouver des fichiers embarqués en
lecture seule avec l'application (ressources, migrations) — jamais pour les
données utilisateur, qui suivent une logique totalement différente
(``app.config.settings._default_app_data_dir``, déjà séparée du répertoire
d'installation).
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Racine à partir de laquelle résoudre les fichiers non-Python
    embarqués avec l'application — la racine du dépôt en développement, le
    dossier bootloader PyInstaller une fois packagé (identique en onedir et
    onefile, voir docstring de module)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]
