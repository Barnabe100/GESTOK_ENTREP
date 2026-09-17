"""Version applicative — source unique (§17 du cahier des charges de la
phase Packaging).

Toute autre référence à la version (fenêtre principale, métadonnées de
l'exécutable Windows, installateur Inno Setup, journal applicatif) doit lire
cette constante plutôt que de la dupliquer :
- ``app/main.py`` (``QApplication.setApplicationVersion``, barre de statut) ;
- ``packaging/generate_version_info.py`` (métadonnées de version de
  l'exécutable Windows, régénérées à partir d'ici) ;
- ``packaging/inno_setup.iss`` (valeur à reporter manuellement dans
  ``MyAppVersion`` — Inno Setup n'exécute pas Python, voir le commentaire en
  tête de ce script).
"""
from __future__ import annotations

APP_NAME = "StockManager Desktop"
__version__ = "1.0.0"
