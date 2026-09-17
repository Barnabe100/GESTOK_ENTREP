# StockManager Desktop — Packaging Windows

Ce dossier contient tout ce qui est nécessaire pour produire une version
Windows distribuable de StockManager Desktop : configuration PyInstaller
(`../stockmanager.spec`), installateur Inno Setup (`inno_setup.iss`), et les
scripts qui génèrent les fichiers dérivés (icône, métadonnées de version).

## Contrainte importante : ce dossier a été préparé sur Linux

PyInstaller ne fait pas de cross-compilation : un exécutable Windows ne peut
être produit qu'en exécutant PyInstaller **sur Windows**. L'environnement de
développement utilisé pour préparer cette phase est Linux ; tout ce qui suit
a donc été **préparé et partiellement validé** ici (voir
`../Cahier_des_charges_final_StockManager.md` phase Packaging pour le détail
exact de ce qui est validé vs. à refaire sous Windows), jamais présenté comme
un test réel de l'exécutable Windows.

## Mode retenu : `onedir`

Pour une V1 commerciale, la fiabilité et la facilité de diagnostic priment
sur la compacité :

- démarrage plus rapide (`onefile` extrait toute l'application dans un
  dossier temporaire à *chaque* lancement) ;
- un fichier manquant ou un chemin cassé se diagnostique en inspectant
  directement le dossier `dist/StockManager/` ;
- moins de faux positifs antivirus qu'un `onefile` autoextractible (source
  fréquente de tickets support pour une distribution commerciale) ;
- compatible avec un installateur Inno Setup classique (copie de dossier).

Coût accepté : un dossier à distribuer plutôt qu'un fichier unique — géré
par l'installateur Inno Setup (`inno_setup.iss`), qui copie l'intégralité du
dossier `onedir` et ne présente à l'utilisateur qu'un raccourci.

## Procédure de build (à exécuter sur Windows)

```text
1. Installer Python 3.11 (voir version exacte utilisée en développement :
   python --version, actuellement 3.11.15)
2. Créer et activer un environnement virtuel :
       python -m venv .venv
       .venv\Scripts\activate
3. Installer les dépendances de build (inclut requirements.txt) :
       pip install -r requirements-build.txt
4. Régénérer l'icône Windows et les métadonnées de version
   (uniquement si app/version.py ou l'icône SVG source ont changé) :
       python packaging\generate_icon.py
       python packaging\generate_version_info.py
5. Construire l'exécutable :
       pyinstaller stockmanager.spec --clean
   Sortie : dist\StockManager\ (dossier onedir autonome).
6. Tester le dossier produit (voir "Tests obligatoires sous Windows"
   ci-dessous) avant de construire l'installateur.
7. Construire l'installateur (nécessite Inno Setup, https://jrsoftware.org/isinfo.php) :
       "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\inno_setup.iss
   Sortie : packaging\installer_output\StockManager-Setup-1.0.0.exe
```

## Build reproductible (§22)

- Python : 3.11.15 (version utilisée en développement — toute 3.11.x récente
  convient, non testé avec d'autres majeures).
- PyInstaller : 6.22.3 (`requirements-build.txt`).
- Dépendances runtime : `requirements.txt` (PySide6, SQLAlchemy, alembic,
  argon2-cffi, cryptography — versions figées).
- Fichier de configuration : `stockmanager.spec` (racine du dépôt, versionné).
- Commande de build : `pyinstaller stockmanager.spec --clean`.
- Sortie : `dist/StockManager/` (`.gitignore` exclut déjà `dist/`/`build/`).

## Fichiers embarqués dans le package client (§2)

Déclarés explicitement dans `stockmanager.spec` (`datas`) :

- `alembic.ini` et `migrations/` (schéma de base — nécessaire à chaque
  démarrage, voir `app/db/init_db.py`) ;
- `app/resources/` (feuille de style Qt, icône SVG de la fenêtre) ;
- clé publique de licence : embarquée par construction, c'est du code Python
  (`app/services/licensing/public_key.py`), pas un fichier de données —
  collectée automatiquement par l'analyse PyInstaller comme tout le reste du
  package `app`.

Résolution des chemins à l'exécution : `app/utils/runtime_paths.app_root()`
(voir ce module) — jamais `Path(__file__).resolve().parents[N]` une fois
packagé, invalide dans un exécutable figé (voir "Problèmes rencontrés"
ci-dessous).

## Ce qui ne doit JAMAIS être dans le package (§8, §23)

- `license_generator/` (outil de génération, clé privée) — jamais importé
  par aucun module de `app/`, donc structurellement absent de l'archive
  PyInstaller (confirmé par inspection du PYZ généré, voir le rapport de
  phase) ;
- `license_generator/keys/private_key.pem` — jamais suivi par git
  (`.gitignore`), jamais copié manuellement ;
- `tests/`, `.git/`, caches `__pycache__`, environnement virtuel de
  développement, `.env` — aucun n'est référencé par `stockmanager.spec`.

## Limitations connues de la configuration actuelle (à revalider sous Windows)

- La liste `excludes` de modules Qt (`stockmanager.spec`) a été choisie de
  façon prudente (QtWebEngine, QtQml/Quick, QtMultimedia, etc. — clairement
  inutilisés par StockManager Desktop) mais **n'a été vérifiée que sur un
  build Linux** ; à revalider sur le premier build Windows réel (un module
  Qt manquant se manifesterait par une erreur au lancement, pas par un échec
  du build lui-même).
- La taille du build Linux de validation est d'environ 211 Mo (dominée par
  PySide6, ~132 Mo) ; la taille réelle du build Windows sera différente
  (pas de bibliothèques X11/GTK, mais ses propres DLL Qt) — à mesurer sur le
  premier build Windows.
