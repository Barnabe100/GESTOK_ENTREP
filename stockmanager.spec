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

# -- imports non détectés statiquement par l'analyse de PyInstaller -----------------
# SQLAlchemy résout son dialecte (sqlite) par chaîne de caractères
# (importlib), invisible à l'analyse statique des imports — jamais détecté
# automatiquement sans cette liste explicite.
#
# migrations/env.py n'est PAS suivi par Analysis() (c'est un fichier de
# données, exécuté par Alembic via un chargement de fichier à l'exécution,
# jamais importé normalement) : ses propres imports ne sont donc jamais vus
# par l'analyse statique. Le seul import non déjà couvert par ailleurs est
# logging.config (repéré par un build de validation Linux : absent, échec
# immédiat au premier lancement avec "ModuleNotFoundError: logging.config").
hiddenimports = [
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
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
