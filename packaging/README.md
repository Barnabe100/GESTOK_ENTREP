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

## Mission « Sauvegarde automatique et restauration » : agent auxiliaire et tâche planifiée Windows

Cette mission ajoute une protection externe optionnelle (copie quotidienne
vers clé USB/disque externe) et la tâche Windows qui l'exécute — ainsi que
la sauvegarde locale elle-même — même lorsque StockManager est fermé. Deux
points d'attention pour le packaging :

- **Aucun artefact PyInstaller distinct** : l'agent auxiliaire
  (`app/backup_external_agent_cli.py`) est invoqué en production via le
  **même exécutable** `StockManager.exe`, avec l'option `--run-backup-agent`
  interceptée tout au début de `app/main.py` (avant toute importation/
  instanciation de `QApplication`/Qt). `ExternalBackupService.configure_scheduled_task`
  enregistre cette ligne de commande exacte (``sys.executable`` déjà résolu
  vers `StockManager.exe` une fois gelé, voir `resolve_agent_invocation()`)
  dans la tâche planifiée — un seul exécutable à construire, signer et
  maintenir, jamais un second `.exe`/script séparé à embarquer.
- **Aucune dépendance supplémentaire à empaqueter** : la tâche Windows est
  administrée via `schtasks.exe` (outil système déjà présent sur tout poste
  Windows, invoqué en sous-processus — même convention que `pg_dump`/
  `pg_restore` ci-dessus), jamais `pywin32`/l'API COM `ITaskService`.
  L'identification du support externe utilise un fichier marqueur
  (`app/services/backups/external_media.py`), jamais `pywin32`/WMI. Le
  chiffrement optionnel des archives (`cryptography`, déjà présent dans
  `requirements.txt` pour d'autres besoins) stocke sa clé dans le coffre
  Windows via le même mécanisme `keyring` que les identifiants PostgreSQL
  (voir « Lot E » ci-dessus, aucune troisième dépendance de coffre). Aucun
  changement de `hiddenimports`/`datas` de `stockmanager.spec` n'a donc été
  nécessaire pour cette mission.
- **Droits Windows** : la tâche planifiée est créée pour l'utilisateur
  courant (aucune option `/ru`/`/rp` de `schtasks.exe`), jamais avec des
  droits administrateur permanents — cohérent avec le reste du packaging,
  qui n'exige déjà aucune élévation pour l'installation utilisateur standard.

**Non revérifié sous Windows réel** (voir « Tests obligatoires sous Windows »
ci-dessous, points 7 à 9) : la création effective de la tâche planifiée
depuis l'exécutable packagé, son exécution alors que StockManager est
fermé, et la copie externe réelle vers une clé USB — seule la logique a été
validée sous Linux (voir les tests unitaires et d'intégration dédiés,
`tests/test_scheduled_task_manager_windows_integration.py` entre autres,
tous ignorés automatiquement hors Windows).

## Mission corrective « Fiabilisation du module de sauvegarde »

Aucune dépendance d'exécution supplémentaire introduite (ni dans
`requirements.txt`, ni dans `hiddenimports`/`datas` de `stockmanager.spec`) :
tout ce qui suit réutilise exclusivement des modules déjà empaquetés
(`cryptography` pour la dérivation de clé PBKDF2 du transfert de clé de
chiffrement, `alembic`/SQLAlchemy déjà embarqués pour la détection de
compatibilité de version, bibliothèque standard pour le reste).

- **Récupération autonome (`--recover`)** : même principe que
  `--run-backup-agent` ci-dessus — un second drapeau intercepté dans
  `app/main.py` avant toute initialisation Qt/base de données, toujours servi
  par le même exécutable unique `StockManager.exe`. Volontairement
  indépendant de toute session SQLAlchemy/base active (voir
  `app/services/backups/recovery.py`) : conçu pour fonctionner même lorsque
  la base de données elle-même est inaccessible ou corrompue, cas où le
  reste de l'application ne démarre plus.
- **Second déclencheur de tâche planifiée (« à l'ouverture de session »)** :
  `ExternalBackupService.configure_scheduled_task` enregistre désormais DEUX
  tâches `schtasks.exe` (la tâche quotidienne existante, inchangée, plus une
  seconde au déclencheur `onlogon`, pointant vers la même ligne de commande)
  — toujours aucune dépendance `pywin32`/API COM, même mécanisme déjà
  documenté ci-dessus pour la tâche quotidienne.

**Non revérifié sous Windows réel** (s'ajoute à la liste « Tests obligatoires
sous Windows » ci-dessous, point 7) : la création effective des DEUX tâches
planifiées (quotidienne et à l'ouverture de session) depuis l'exécutable
packagé, et le comportement réel de `StockManager.exe --recover` exécuté
depuis une invite de commande sur un poste où la base de données a été
rendue délibérément inaccessible.

## Mission corrective « Correction et validation du module de sauvegarde sous Windows »

Six anomalies constatées lors d'un test Windows réel du module précédent
(support USB déclaré inaccessible juste après configuration, tâche
planifiée échouant avec le code 1, export de clé refusant une clé pourtant
configurée, entre autres) ont été corrigées. Aucune dépendance
supplémentaire introduite (ni `requirements.txt`, ni `hiddenimports`/`datas`
de `stockmanager.spec`) :

- **Création de la tâche planifiée via un fichier XML**, plus via une
  ligne de commande `/tr` construite à la main : la cause du code 1 était
  un double échappement des guillemets par `subprocess.list2cmdline`
  lorsque la valeur `/tr` contenait elle-même un chemin entre guillemets
  (reproduit et confirmé en isolant l'appel). `scheduled_task_manager.py`
  construit désormais la définition complète de la tâche avec
  `xml.etree.ElementTree` (échappement XML standard, jamais de guillemets
  imbriqués) et l'enregistre via `schtasks /create /xml <fichier> /f` —
  toujours aucune dépendance `pywin32`/API COM.
- **Énumération réelle des lecteurs** (`external_media.list_drives_with_info`) :
  remplace l'ancien sélecteur de dossier générique par une liste des
  lecteurs Windows réellement montés (`GetDriveTypeW`/
  `GetVolumeInformationW` via `ctypes`, toujours aucune dépendance WMI/
  `pywin32`), avec une vérification d'écriture réelle avant toute
  confirmation — cause du bug « support configuré puis déclaré
  inaccessible » : un chemin de lettre de lecteur sans barre finale
  (`Path("E:")`) est, sous Windows, relatif au répertoire courant de ce
  lecteur pour le processus, jamais sa racine — corrigé par
  `normalize_drive_root`.
- **Empreinte de clé de chiffrement persistée** (`archive_encryption.fingerprint_of`,
  SHA-256 de la clé, jamais la clé elle-même) : permet de détecter qu'une
  clé a déjà été utilisée sur ce poste même si les archives qu'elle
  protège ont depuis été déplacées vers un autre support ou un autre
  ordinateur — sans cette empreinte, une installation ayant perdu sa clé
  mais déplacé ses archives ailleurs aurait pu voir StockManager générer
  une nouvelle clé de remplacement, rendant les anciennes archives
  illisibles. Stockée comme un paramètre applicatif ordinaire
  (`ParameterRepository`), jamais dans le coffre d'identifiants.

**Non revérifié sous Windows réel** (s'ajoute à la liste « Tests
obligatoires sous Windows » ci-dessous, points 7 à 10) : la création
réelle de la tâche planifiée via le nouveau mécanisme XML depuis
l'exécutable packagé (chemin contenant des espaces compris), la
sélection d'un support externe parmi les lecteurs réellement détectés
sur un poste de test, et l'export/import de la clé de chiffrement avec
affichage temporaire du mot de passe.

## Mission corrective ciblée « Erreur Accès refusé de la tâche planifiée Windows »

Après déploiement de la correction XML ci-dessus, un test Windows réel a
révélé un NOUVEAU refus d'accès (code 1), cette fois limité à la tâche
« à l'ouverture de session » (la tâche quotidienne, elle, se créait déjà
sans problème). Aucune dépendance supplémentaire introduite.

- **Cause exacte** : la définition XML ne précisait jamais `<UserId>` —
  ni dans `<Principal>`, ni dans `<LogonTrigger>`. Un `<LogonTrigger>`
  sans `<UserId>` surveille l'ouverture de session de N'IMPORTE QUEL
  utilisateur du poste (une capacité de surveillance système réservée à
  un compte administrateur), alors qu'un `<LogonTrigger>` scopé à
  l'utilisateur courant est une capacité que tout compte standard
  possède pour lui-même — exactement ce que produit la construction
  d'un déclencheur « à l'ouverture de session » depuis l'interface
  graphique du Planificateur de tâches par un utilisateur standard.
  C'est pour cela que seule la tâche quotidienne (`CalendarTrigger`,
  purement temporelle, sans ambiguïté d'utilisateur) échappait au
  problème.
- **Correction** (`scheduled_task_manager.py` uniquement) : l'identité
  Windows qualifiée du compte exécutant StockManager (`USERDOMAIN`\\
  `USERNAME`, résolue par `_default_current_user_id`, jamais stockée,
  jamais transmise via `/ru`/`/rp`) est désormais inscrite explicitement
  dans `<Principal><UserId>` et dans `<LogonTrigger><UserId>`.
- **Relecture obligatoire après création** (`_verify_task_registered`) :
  la tâche n'est plus jamais déclarée configurée avec succès sur le seul
  code de retour 0 de `schtasks /create` — son existence réelle est
  revérifiée (`schtasks /query`), et sa définition complète (commande,
  type de déclencheur) est relue en meilleur effort pour détecter une
  éventuelle incohérence, sans jamais faire échouer l'opération sur un
  simple problème de lecture (encodage console, version de Windows).
- **Messages d'erreur distingués** (`_classify_schtasks_failure`,
  `_describe_existing_task_conflict`) : un refus d'accès, une définition
  XML invalide, et une tâche déjà existante enregistrée sous un AUTRE
  compte Windows (jamais supprimée automatiquement — uniquement signalée,
  l'utilisateur devant la vérifier lui-même dans `taskschd.msc`) sont
  désormais présentés par des phrases distinctes, toujours accompagnées
  du détail Windows brut.
- Stockage de l'exécutable/manifeste (`stockmanager.spec`) et agent
  auxiliaire (`backup_external_agent_cli.py`) examinés et confirmés sans
  rapport avec cette erreur : aucune demande d'élévation UAC n'est
  déclarée dans le manifeste de l'exécutable (`asInvoker` implicite,
  jamais `requireAdministrator`), et l'agent auxiliaire ne fait que
  recevoir l'appel — la cause était entièrement dans la définition XML de
  la tâche elle-même.

**Non revérifié sous Windows réel** : la création réelle de la tâche
« à l'ouverture de session » depuis une session Windows **standard**
(non administrateur) avec le `<UserId>` désormais explicite — c'est
précisément le scénario qui échouait avant cette correction (voir
« Tests obligatoires sous Windows » ci-dessous, points 12 à 15).

## Mission « Gestion complète de la planification des sauvegardes Windows »

Ajoute la gestion complète de la planification depuis l'écran Sauvegardes
(fréquences hebdomadaire multi-jours et mensuelle, déclenchement
d'ouverture de session indépendant, consultation détaillée de la tâche
réelle). Aucune dépendance supplémentaire introduite, aucune migration de
base de données (nouveaux paramètres stockés comme les existants, dans la
table `parametres` déjà utilisée).

- **`scheduled_task_manager.py`** : `_build_task_xml` construit désormais
  `<ScheduleByWeek>` (un élément `<DaysOfWeek>` par jour sélectionné) et
  `<ScheduleByMonth>` (`<DaysOfMonth><Day>N</Day></DaysOfMonth>` pour un
  jour fixe, ou `<RunOnLastDayOfMonth>true</RunOnLastDayOfMonth>` — élément
  dédié du schéma Task Scheduler, utilisé par l'option native « dernier
  jour » de l'interface graphique Windows — pour éviter tout décalage
  silencieux sur les mois courts). `parse_task_definition`/
  `query_task_definition` (nouveaux, publics) relisent cette même
  définition pour l'affichage et la vérification post-création
  (`_verify_task_registered` compare désormais aussi les jours/le jour du
  mois effectivement enregistrés, pas seulement le type de déclencheur).
- **`backup_service.py`** : `BackupConfig` porte désormais `weekly_days`
  (ensemble de `date.weekday()`), `monthly_day`, `monthly_last_day`. Le
  calcul d'échéance (`_is_due_as_of`) est réécrit autour d'une fonction
  pure (`_most_recent_scheduled_date`) consciente des jours réels — un
  jour de mois absent d'un mois donné (ex. 31 dans un mois de 30 jours,
  ou 29 février hors année bissextile) fait sauter ce mois entièrement,
  jamais un report vers un autre jour.
- **`external_backup_service.py`** : le déclenchement à l'ouverture de
  session devient un réglage persisté indépendant
  (`is_onlogon_enabled`/`_KEY_ONLOGON_ENABLED`, activé par défaut sur une
  installation neuve) — `configure_scheduled_task` ne supprime/recrée que
  la tâche complémentaire correspondante selon ce réglage, jamais la
  tâche principale. Nouvelles méthodes `scheduled_task_details()`
  (relevé structuré pour l'affichage) et
  `scheduled_task_sync_warnings()` (comparaison définition Windows
  réelle ↔ configuration StockManager).
- **`backups_page.py`** : sélection des jours de la semaine/du jour du
  mois (visibles uniquement pour la fréquence concernée), case
  d'activation du déclencheur d'ouverture de session, section repliable
  « Détails de la tâche planifiée Windows » (relevé complet + boutons
  Actualiser/Ouvrir le Planificateur de tâches Windows via
  `os.startfile("taskschd.msc")`).

**Non revérifié sous Windows réel** (s'ajoute à la liste « Tests
obligatoires sous Windows » ci-dessous, points 17-19) : la création
réelle d'une tâche hebdomadaire multi-jours et d'une tâche mensuelle
(jour fixe et dernier jour) depuis l'exécutable packagé, la bascule du
déclencheur d'ouverture de session sans recréation de la tâche
principale, et l'ouverture effective du Planificateur de tâches Windows
depuis le bouton dédié.

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

## Incident résolu : « Failed to load Python DLL » au premier lancement

Constaté lors du tout premier build Windows réel (Python 3.11.9, installation
par utilisateur sous `...\AppData\Local\Programs\Python\Python311\`) :
`StockManager.exe` se construisait sans erreur, mais refusait de démarrer
avec `Failed to load Python DLL '...\_internal\python311.dll'. LoadLibrary:
Le module spécifié est introuvable.` — `dist\StockManager\_internal\` ne
contenait ni `python311.dll` ni `python3.dll`.

**Cause confirmée** : sous Windows, PyInstaller localise les dépendances
binaires de `python.exe` (donc `python3XX.dll`) via l'ordre de recherche de
DLL standard de Windows — le répertoire de l'exécutable, les répertoires
système, puis le `PATH` du processus qui exécute `pyinstaller`. Un
répertoire d'installation Python par utilisateur n'y figure que si l'option
« Add python.exe to PATH » a été cochée à l'installation ; activer un
environnement virtuel (`.venv\Scripts\activate`) n'y ajoute jamais le
répertoire d'installation de base lui-même (qui seul contient la DLL —
confirmé : `.venv` ne contient jamais `python3XX.dll`). Si ce répertoire est
absent du `PATH` effectif au moment du build, PyInstaller échoue
silencieusement à localiser la DLL (un simple avertissement dans le journal
de build, jamais un échec de build) et l'omet du dossier figé.

**Correctif appliqué** (`stockmanager.spec`) : `python3.dll`/`python3XX.dll`
sont désormais résolues explicitement via `sys.base_prefix` (qui pointe
toujours sur l'installation Python réelle, même exécuté depuis un
environnement virtuel) et déclarées directement dans
`Analysis(binaries=...)` — la recherche de dépendances par PyInstaller
devient alors inutile pour ces deux fichiers précis, donc indépendante du
`PATH` effectif au moment du build, quel que soit l'emplacement
d'installation de Python. Sans effet sous Linux/macOS (liste vide, aucun
fichier de ce nom dans `sys.base_prefix`) — revérifié par un build de
contrôle Linux après ce correctif : `dist/StockManager/_internal/` contient
toujours `libpython3.11.so.1.0` (équivalent Linux), build inchangé par
ailleurs.

**Non revérifié** : ce correctif élimine la cause identifiée mais n'a pas
encore été testé par un nouveau build Windows réel — à faire avant de
considérer l'incident définitivement clos (voir « Tests obligatoires sous
Windows » ci-dessous, point 1).

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
7. Depuis l'écran Sauvegardes de l'exécutable packagé (installé sur un
   chemin contenant un espace, ex. `C:\Program Files\StockManager\`),
   « Configurer/réparer la tâche planifiée Windows… » crée réellement DEUX
   tâches visibles dans le Planificateur de tâches Windows (`taskschd.msc`,
   définition désormais créée via un fichier XML, voir « Mission corrective
   — Correction et validation… » ci-dessus) — l'une quotidienne, l'autre au
   déclencheur « à l'ouverture de session » — toutes deux pointant vers
   `StockManager.exe --run-backup-agent` avec le chemin complet correctement
   interprété malgré l'espace ; « Supprimer la tâche planifiée… » les retire
   proprement toutes les deux.
8. **StockManager fermé, session Windows ouverte**, déclencher manuellement
   cette tâche depuis le Planificateur de tâches (ou attendre l'heure
   programmée) : une nouvelle sauvegarde locale apparaît bien dans le
   dossier de destination configuré, sans qu'aucune fenêtre StockManager ne
   s'ouvre. Puis, **en fermant la session Windows** avant l'heure programmée :
   vérifier qu'aucune sauvegarde n'est créée tant qu'aucune session n'est
   ouverte, et qu'elle est rattrapée dès la prochaine ouverture de session
   (déclencheur « à l'ouverture de session »).
9. « Sélectionner/modifier le support… » affiche réellement les lecteurs
   détectés sur le poste de test (clé USB *et*, séparément, un disque dur
   externe se déclarant comme disque fixe) avec leur lettre et leur
   étiquette de volume ; le support sélectionné est immédiatement rapporté
   accessible par « Tester l'accessibilité du support », sans jamais
   l'inverse juste après une configuration réussie.
10. Avec la protection externe activée et un support sélectionné comme en 9,
    la tâche planifiée copie bien la dernière sauvegarde locale validée sur
    le support ; le débrancher avant l'exécution planifiée ne doit supprimer
    aucune sauvegarde externe déjà présente (voir « Garanties » dans le
    manuel utilisateur, chapitre Sauvegardes).
11. Avec le chiffrement activé, « Exporter la clé de chiffrement… » puis
    « Importer la clé de chiffrement… » (sur un second profil ou après
    suppression du coffre local) réussissent avec le bon mot de passe,
    échouent explicitement avec un mauvais mot de passe, et la case
    « Afficher le mot de passe » révèle bien la saisie dans les deux
    fenêtres.
12. **Depuis une session Windows standard (compte membre du groupe
    Utilisateurs, PAS Administrateurs)**, « Configurer/réparer la tâche
    planifiée Windows… » crée réellement les DEUX tâches (quotidienne et
    « à l'ouverture de session ») sans aucune invite UAC ni message
    d'erreur — c'est précisément le scénario qui échouait avec le code 1
    « Accès refusé » avant la correction du `<UserId>` explicite (voir
    « Mission corrective ciblée… » ci-dessus). Vérifier dans
    `taskschd.msc` que les deux tâches affichent bien le compte standard
    comme « Exécuter en tant que », jamais SYSTEM ni un autre compte.
13. **Depuis une session Windows administrateur**, la même action réussit
    également, et la tâche créée s'exécute toujours sous le compte
    administrateur courant (jamais SYSTEM) — `RunLevel=LeastPrivilege`
    n'élève jamais les droits de la tâche au-delà de ceux du compte qui
    l'a créée.
14. **Mise à jour d'une tâche déjà existante** (créée par un essai
    précédent, avec cette version corrigée) : « Configurer/réparer… » la
    recrée sans erreur, avec l'heure éventuellement modifiée dans
    l'intervalle correctement reflétée.
15. **Tâche appartenant à un autre compte** (scénario volontairement
    simulé : créer manuellement dans `taskschd.msc`, sous un autre compte
    ou avec `/ru`/`/rp`, une tâche nommée exactement
    `StockManager - Sauvegarde`, puis cliquer sur « Configurer/
    réparer… » depuis le compte StockManager habituel) : l'erreur
    affichée nomme explicitement le compte propriétaire de la tâche en
    conflit, et cette tâche n'est à aucun moment supprimée
    automatiquement — seule une suppression manuelle dans
    `taskschd.msc`, puis un nouvel essai, doit permettre de la reprendre.
16. « Supprimer la tâche planifiée… » réussit aussi bien depuis un compte
    standard que depuis un compte administrateur, pour une tâche créée
    par le même compte.
17. Configurer une fréquence **hebdomadaire avec plusieurs jours** (ex.
    lundi et jeudi) : la tâche créée déclenche bien aux deux jours
    indiqués (vérifier dans `taskschd.msc`, onglet Déclencheurs), jamais
    un seul des deux.
18. Configurer une fréquence **mensuelle**, d'abord avec un jour fixe
    (ex. 31), puis avec « Dernier jour du mois » : vérifier dans
    `taskschd.msc` que le déclencheur mensuel correspondant est bien
    enregistré (`DaysOfMonth` ou `RunOnLastDayOfMonth` selon le cas), et
    que décocher « Enregistrer » avec un mois sans jour 31 (avril, par
    exemple, visible dans le calcul de prochaine exécution) ne provoque
    jamais d'erreur ni de décalage vers un autre jour.
19. Décocher puis recocher **« Déclencher également au démarrage de
    session Windows »** sans toucher à la fréquence : seule la tâche
    « (ouverture de session) » disparaît/réapparaît dans `taskschd.msc`,
    la tâche principale reste inchangée (vérifier sa dernière
    modification). La section « Détails de la tâche planifiée Windows »
    (bouton « Actualiser les informations ») reflète ce changement
    immédiatement, et le bouton « Ouvrir le Planificateur de tâches
    Windows » ouvre bien `taskschd.msc` sans modifier la tâche.

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
