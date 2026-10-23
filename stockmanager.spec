# -*- mode: python ; coding: utf-8 -*-
"""Configuration PyInstaller de StockManager Desktop (§2-3 du cahier des
charges de la phase Packaging).

Mode retenu : ``onedir`` (voir packaging/README.md pour la justification
détaillée — fiabilité et diagnostic prioritaires sur la compacité pour une
V1 commerciale : démarrage plus rapide qu'onefile, pas d'extraction dans un
dossier temporaire à chaque lancement, fichier manquant plus facile à
diagnostiquer).

Construit UNIQUEMENT sur Windows (PyInstaller ne fait pas de
cross-compilation) :

    pip install -r requirements.txt -r requirements-build.txt
    python packaging/generate_icon.py
    python packaging/generate_version_info.py
    pyinstaller stockmanager.spec --clean

Sortie : dist/StockManager/ (dossier autonome, voir packaging/README.md).
"""
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import copy_metadata

block_cipher = None

# -- fichiers non-Python nécessaires au runtime (§2) --------------------------------
# Résolus à l'exécution via app.utils.runtime_paths.app_root(), qui pointe
# sur sys._MEIPASS une fois packagé — la disposition ci-dessous (chemin de
# destination) doit donc rester identique à la disposition du dépôt.
# Tree() produit des entrées de type TOC (dest, src, typecode) : elles
# s'ajoutent directement à COLLECT(), jamais à Analysis(datas=...) qui
# n'accepte que des paires (src, dest) simples (voir plus bas).
datas = [
    ("alembic.ini", "."),
]
migrations_tree = Tree("migrations", prefix="migrations", excludes=["__pycache__", "*.pyc"])
resources_tree = Tree("app/resources", prefix="app/resources", excludes=["__pycache__", "*.pyc"])

# Lot E (§E.1.2) : keyring sélectionne son backend par découverte de points
# d'entrée (``importlib.metadata.entry_points(group="keyring.backends")``),
# qui lit les métadonnées ``.dist-info`` du paquet installé — jamais
# embarquées automatiquement par l'analyse de PyInstaller (qui ne regarde
# que le code source, pas les métadonnées d'installation). Sans ceci, la
# découverte par points d'entrée échouerait silencieusement dans
# l'exécutable gelé (elle retournerait une liste vide, sans erreur) ; le
# code applicatif (app/security/credential_vault.py) s'en sortait jusqu'ici
# uniquement parce qu'il importe explicitement ``keyring.backends.Windows``
# avant d'appeler ``keyring.get_keyring()`` — effet de bord de l'ordre des
# imports, jamais garanti par aucun contrat de keyring. ``copy_metadata``
# rend ce mécanisme robuste indépendamment de cet ordre d'imports.
datas += copy_metadata("keyring")

# -- imports non détectés statiquement par l'analyse de PyInstaller -----------------
# SQLAlchemy résout chacun de ses dialectes (sqlite, postgresql) par chaîne
# de caractères (``__import__("sqlalchemy.dialects.%s" % nom)``, voir
# sqlalchemy/dialects/__init__.py::_auto_fn) — invisible à l'analyse
# statique des imports, jamais détecté automatiquement sans ces entrées
# explicites. ``sqlalchemy.dialects.postgresql`` et son sous-module
# ``psycopg`` manquaient jusqu'ici (seul le dialecte sqlite avait été
# ajouté) : un exécutable gelé configuré en PostgreSQL échouait donc dès
# ``create_engine()`` avec ``NoSuchModuleError``, avant même d'atteindre le
# coffre d'identifiants — confirmé par lecture du mécanisme de résolution
# dynamique de SQLAlchemy (aucune occurrence littérale de
# ``sqlalchemy.dialects.postgresql``/``psycopg`` nulle part dans ``app/``).
#
# keyring.backends.Windows (et son propre import conditionnel, protégé par
# un ``ExceptionTrap``, de win32ctypes/pywintypes/win32cred — voir le
# fichier source de ce module) : ajoutés explicitement plutôt que de
# compter sur la découverte automatique de PyInstaller pour un module dont
# les dépendances ne sont installées (``pywin32-ctypes``, marqueur
# ``sys_platform == "win32"``) que sur une construction Windows réelle.
# Sous Linux, ces entrées sont simplement introuvables (avertissement de
# PyInstaller, jamais un échec de build — vérifié par un build Linux de
# contrôle, voir packaging/README.md) : inoffensif, nécessaire uniquement
# pour la construction Windows réelle.
# keyring.backends.fail : backend de repli sûr de keyring lui-même
# (« aucun backend disponible »), déjà utilisé tel quel par les tests Linux
# de ce projet — ajouté explicitement pour qu'il soit également disponible,
# par cohérence, dans l'exécutable gelé.
#
# migrations/env.py n'est PAS suivi par Analysis() (c'est un fichier de
# données, exécuté par Alembic via un chargement de fichier à l'exécution,
# jamais importé normalement) : ses propres imports ne sont donc jamais vus
# par l'analyse statique. logging.config (repéré par un build de validation
# Linux : absent, échec immédiat au premier lancement avec
# "ModuleNotFoundError: logging.config") suit la même logique.
hiddenimports = [
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.dialects.postgresql.psycopg",
    "psycopg",
    "keyring.backends.Windows",
    "keyring.backends.fail",
    "win32ctypes.pywin32",
    "win32ctypes.core",
    "pywintypes",
    "win32cred",
    "logging.config",
]

a = Analysis(
    ["app/main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Modules Qt volumineux et non utilisés par StockManager Desktop
    # (aucun navigateur embarqué, aucune scène QML/3D, aucun média, aucune
    # base QtSql — l'application persiste exclusivement via SQLAlchemy) :
    # exclus pour ne pas embarquer inutilement des fichiers (§2/§23). Liste
    # volontairement prudente (jamais QtNetwork/QtOpenGL, dont dépendent
    # parfois QtWidgets/QtCharts selon la plateforme). QtSvg n'est plus
    # requis par l'icône de l'application depuis le lot Identité visuelle
    # (symbole officiel intégré en PNG, voir app/resources/branding/) mais
    # reste volontairement non exclu, par prudence — à revalider lors du
    # premier build réel sur Windows (voir packaging/README.md, section
    # limitations).
    excludes=[
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineQuick",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.QtBluetooth", "PySide6.QtSensors", "PySide6.QtPositioning", "PySide6.QtSerialPort",
        "PySide6.QtRemoteObjects", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtTest", "PySide6.QtNfc", "PySide6.QtScxml",
        "PySide6.QtSql",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StockManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX peut déclencher des faux positifs antivirus sur Windows — évité pour une V1 commerciale.
    console=False,  # application graphique : aucune console parasite (§13).
    icon="packaging/app_icon.ico",
    version="packaging/file_version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    migrations_tree,
    resources_tree,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="StockManager",
)
