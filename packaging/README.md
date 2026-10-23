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

## Lot E : PostgreSQL, keyring et sauvegarde/restauration

Le Lot D (configuration PostgreSQL utilisateur) a introduit une dépendance
d'exécution (`keyring`, coffre d'identifiants Windows) et un second moteur de
base de données (PostgreSQL, via `psycopg`) sans que ce dossier de packaging
n'ait été mis à jour en conséquence — corrigé par le Lot E :

- **Dialecte PostgreSQL de SQLAlchemy** : SQLAlchemy résout chacun de ses
  dialectes (`sqlite`, `postgresql`) par une construction dynamique de
  chaîne de caractères (`__import__("sqlalchemy.dialects.%s" % nom)`),
  invisible à l'analyse statique de PyInstaller — exactement le même
  mécanisme déjà documenté dans `stockmanager.spec` pour `sqlite`, jamais
  répété jusqu'ici pour `postgresql`. Sans `hiddenimports` explicites
  (`sqlalchemy.dialects.postgresql`, `sqlalchemy.dialects.postgresql.psycopg`,
  `psycopg`), un exécutable gelé configuré en PostgreSQL échouait dès
  `create_engine()` avec `NoSuchModuleError` — **confirmé et corrigé** (voir
  « Validé sous Linux » ci-dessous).
- **Découverte du backend `keyring`** : `keyring` sélectionne son backend par
  points d'entrée (`importlib.metadata.entry_points(group="keyring.backends")`),
  qui lisent les métadonnées `.dist-info` du paquet installé — jamais
  embarquées automatiquement par PyInstaller (qui n'examine que le code
  source, pas les métadonnées d'installation). `stockmanager.spec` appelle
  désormais explicitement `copy_metadata("keyring")` pour les embarquer, et
  déclare en `hiddenimports` le module `keyring.backends.Windows` (et ses
  propres dépendances conditionnelles `win32ctypes.pywin32`/`pywintypes`/
  `win32cred`, présentes uniquement sur une construction Windows réelle —
  `pywin32-ctypes` étant un paquet conditionné par `sys_platform == "win32"`)
  plutôt que de compter sur l'ordre des imports du code applicatif (c'était
  le cas jusqu'ici : `app/security/credential_vault.py` importe
  `keyring.backends.Windows` avant d'appeler `keyring.get_keyring()`, ce qui
  masquait fortuitement l'absence des métadonnées — un effet de bord, jamais
  un contrat garanti par `keyring`).

**Validé sous Linux** (mécanismes génériques de PyInstaller, jamais une
validation de l'exécutable Windows — voir « Limitations connues ») : un
build `pyinstaller stockmanager.spec --clean` exécuté sous Linux après ces
changements a produit un dossier `dist/StockManager/` contenant
`keyring-25.7.0.dist-info` (métadonnées bien copiées) et tous les
sous-modules `sqlalchemy.dialects.postgresql.*`/`psycopg`/`psycopg_binary`
(aucun avertissement « missing module » les concernant). L'exécutable Linux
ainsi produit a ensuite été exécuté réellement (hors chaîne de compilation)
contre un serveur PostgreSQL 16.15 local de test : démarrage, migrations
Alembic, création du moteur SQLAlchemy PostgreSQL, amorçage des données de
référence et du compte administrateur — tous réussis sans aucune erreur de
chargement de module. Le même exécutable a aussi été revérifié en mode
SQLite (comportement historique) pour écarter toute régression. Ceci
démontre que l'inclusion des modules fonctionne, **pas** que
`WinVaultKeyring` est réellement sélectionné sur Windows ni que
l'installateur Inno Setup produit un paquet fonctionnel — ces deux derniers
points restent à vérifier sur un poste Windows réel (voir
`docs/postgresql-configuration.md`, section « Procédure de validation
Windows »).

## Sauvegarde et restauration PostgreSQL (`pg_dump`/`pg_restore`)

La sauvegarde/restauration PostgreSQL (voir
`app/services/backups/postgresql_backup_engine.py`) invoque les outils
officiels `pg_dump`/`pg_restore` comme processus externes — **jamais
embarqués** dans le package StockManager (pas de redistribution binaire,
pas de contrainte de licence ou de compatibilité de version supplémentaire
pour l'application). Consé­quence directe pour le déploiement : un poste
Windows qui doit utiliser la sauvegarde/restauration PostgreSQL doit avoir
le client PostgreSQL (`pg_dump.exe`/`pg_restore.exe`, généralement installé
avec le client officiel PostgreSQL ou récupérable séparément) sur son
`PATH` — StockManager le vérifie explicitement et refuse clairement
l'opération sinon (jamais un échec confus de sous-processus), mais ne
l'installe jamais lui-même. En cas d'échec réel (identifiants refusés,
serveur inaccessible, version incompatible…), le détail technique exact
est journalisé (jamais affiché à l'écran, jamais le mot de passe) dans le
journal applicatif du poste — voir `docs/postgresql-configuration.md`,
§6.5, pour le diagnostic. Voir
`docs/postgresql-configuration.md` pour le détail des prérequis, formats
et procédures.

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
   (uniquement si app/version.py ou le symbole source ont changé,
   voir app/resources/branding/README.md) :
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
- `app/resources/` (feuille de style Qt, identité visuelle officielle —
  voir `app/resources/branding/README.md`) ;
- `keyring-<version>.dist-info/` (Lot E, via `copy_metadata("keyring")`) —
  métadonnées de paquet nécessaires à la découverte du backend Windows de
  `keyring` (voir « Lot E : PostgreSQL, keyring et sauvegarde/restauration »
  ci-dessus) — jamais une donnée métier, uniquement un fichier de métadonnées
  d'installation Python ;
- clé publique de licence : embarquée par construction, c'est du code Python
  (`app/services/licensing/public_key.py`), pas un fichier de données —
  collectée automatiquement par l'analyse PyInstaller comme tout le reste du
  package `app`.

Jamais embarqués (choix délibéré, voir « Sauvegarde et restauration
PostgreSQL » ci-dessus) : les exécutables `pg_dump`/`pg_restore` — prérequis
du poste client, jamais redistribués par StockManager.

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

## Tests obligatoires sous Windows

Un build Linux (même réussi, même exécuté avec succès — voir « Lot E »
ci-dessus) ne remplace jamais ces vérifications : un exécutable ELF ne
valide pas l'exécutable Windows. Avant de considérer un build Windows prêt
pour un client, vérifier au minimum (checklist détaillée, reproductible :
`docs/postgresql-configuration.md`, section « Procédure de validation
Windows ») :

1. Le dossier `dist\StockManager\` démarre (`StockManager.exe`) sans boîte
   de dialogue d'erreur, en mode SQLite (installation neuve) comme avec une
   base SQLite existante.
2. L'assistant de première configuration et l'écran d'administration de la
   base de données s'affichent et fonctionnent (Lot D, non réimplémenté par
   le Lot E — seulement revérifié dans le contexte packagé).
3. Une connexion PostgreSQL réelle réussit depuis l'exécutable packagé.
4. `keyring.get_keyring()` retourne bien `WinVaultKeyring` (jamais un autre
   backend, jamais une exception masquée) une fois un mot de passe
   PostgreSQL enregistré depuis l'assistant/l'écran d'administration.
5. Une sauvegarde puis une restauration PostgreSQL réelles réussissent
   depuis l'écran Sauvegardes de l'exécutable packagé (nécessite
   `pg_dump`/`pg_restore` installés sur le poste de test, voir « Sauvegarde
   et restauration PostgreSQL » ci-dessus).
6. L'installateur Inno Setup s'installe, se désinstalle, et préserve les
   données utilisateur (`%APPDATA%\StockManager`) dans les deux cas.

## Limitations connues de la configuration actuelle (à revalider sous Windows)

- La liste `excludes` de modules Qt (`stockmanager.spec`) a été choisie de
  façon prudente (QtWebEngine, QtQml/Quick, QtMultimedia, etc. — clairement
  inutilisés par StockManager Desktop) mais **n'a été vérifiée que sur un
  build Linux** ; à revalider sur le premier build Windows réel (un module
  Qt manquant se manifesterait par une erreur au lancement, pas par un échec
  du build lui-même).
- La taille du build Linux de validation est d'environ 247 Mo (mesurée après
  les ajouts du Lot E — `sqlalchemy.dialects.postgresql`, `psycopg`/
  `psycopg_binary`, métadonnées `keyring` ; dominée par PySide6, ~132 Mo) ;
  la taille réelle du build Windows sera différente (pas de bibliothèques
  X11/GTK, mais ses propres DLL Qt et, le cas échéant, `pywin32-ctypes`) — à
  mesurer sur le premier build Windows.
- `win32ctypes.pywin32`/`win32ctypes.core`/`pywintypes`/`win32cred` (Lot E,
  dépendances de `keyring.backends.Windows`) sont déclarés en
  `hiddenimports` mais **introuvables sous Linux** par construction
  (`pywin32-ctypes` n'y est jamais installé, marqueur `sys_platform ==
  "win32"`) : PyInstaller l'y signale par un avertissement, jamais un échec
  de build — confirmé lors du build Linux de validation de ce lot. Leur
  inclusion réelle (fichiers présents dans `dist\StockManager\` sous
  Windows) reste donc à vérifier sur le premier build Windows réel.
