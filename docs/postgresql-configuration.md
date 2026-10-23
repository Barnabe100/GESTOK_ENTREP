# Configuration PostgreSQL — StockManager Desktop (Lot D)

Ce document couvre la configuration du moteur PostgreSQL ajoutée par le Lot D :
prérequis, procédure (assistant de première configuration et écran
d'administration), fonctionnement du coffre d'identifiants, erreurs
fréquentes, et retour à SQLite sans perte de données. Il s'adresse à la fois
à l'administrateur qui configure le poste et au développeur qui doit
comprendre/maintenir ce mécanisme.

**Avertissement important :** à la date de rédaction, le comportement du
coffre d'identifiants Windows Credential Manager et le packaging de la
dépendance `keyring` n'ont été vérifiés que par du code et des tests
automatisés — **jamais sur un poste Windows réel**. Ne pas présenter la
configuration PostgreSQL comme prête pour la production tant que cette
vérification n'a pas été faite (voir « Limites connues » ci-dessous).

## 1. Prérequis

- **SQLite reste le moteur par défaut** : aucune action n'est nécessaire pour
  continuer à utiliser StockManager tel qu'avant ce lot.
- Pour utiliser PostgreSQL, un **serveur PostgreSQL 16.15 déjà installé et
  accessible sur le réseau** est nécessaire. StockManager ne crée **jamais**
  automatiquement la base, le rôle (utilisateur) ou le serveur PostgreSQL
  lui-même — ces éléments doivent être préparés à l'avance par un
  administrateur PostgreSQL :
  - une base de données dédiée à StockManager ;
  - un rôle (utilisateur) PostgreSQL disposant des droits nécessaires sur
    cette base ;
  - le serveur accessible depuis le poste StockManager (hôte/port, règles
    réseau/pare-feu).
- Sous Windows, le **Gestionnaire d'identifiants Windows (Windows Credential
  Manager)** doit être disponible — c'est le seul endroit où StockManager
  enregistre le mot de passe PostgreSQL. Si ce service Windows est désactivé
  ou indisponible, StockManager refuse d'enregistrer un mot de passe
  PostgreSQL (voir « Erreurs fréquentes »).
- Pour utiliser la **sauvegarde/restauration PostgreSQL** (Lot E, voir plus
  bas) : les outils clients officiels **`pg_dump` et `pg_restore`**
  (généralement installés avec le client PostgreSQL complet, ou
  téléchargeables séparément sur postgresql.org) doivent être présents sur
  le poste et accessibles depuis le `PATH`. StockManager ne les installe
  jamais lui-même et ne les embarque jamais dans son propre exécutable —
  leur absence est détectée explicitement et affichée clairement, jamais un
  échec confus. Le mode SQLite n'a jamais besoin de ces outils.

## 2. Un seul moteur actif à la fois

StockManager utilise toujours exactement un moteur de base de données
(SQLite ou PostgreSQL). Il n'y a **aucune synchronisation, copie ou
migration automatique de données entre les deux moteurs**. Changer de
moteur ne touche jamais aux données de l'ancien moteur (un fichier SQLite
existant n'est jamais supprimé ni modifié lors du passage à PostgreSQL).

## 3. Configurer PostgreSQL

### 3.1. Assistant de première configuration

Au tout premier lancement sur un poste n'ayant jamais été configuré (ni
fichier de configuration, ni base SQLite déjà créée), un assistant propose
de choisir SQLite (par défaut) ou PostgreSQL. Si PostgreSQL est choisi :

1. Renseignez l'hôte, le port, le nom de la base, l'utilisateur et le mot de
   passe fournis par votre administrateur PostgreSQL.
2. Cliquez sur **Tester la connexion** avant d'enregistrer — cela permet de
   détecter une erreur de saisie sans rien enregistrer.
3. Cliquez sur **Terminer** : la configuration est enregistrée comme
   *configuration en attente*. StockManager continue d'utiliser SQLite
   pour la session en cours.
4. **Redémarrez complètement StockManager Desktop** pour que la
   configuration PostgreSQL soit réellement utilisée.

### 3.2. Écran d'administration (Administrateur uniquement)

Une fois connecté avec un compte Administrateur, l'entrée de navigation
**Base de données** permet de :

- consulter la configuration active (moteur, et pour PostgreSQL : hôte,
  port, base, utilisateur — **jamais le mot de passe**, qui n'est jamais
  affiché nulle part) ;
- consulter une éventuelle configuration en attente ;
- préparer une nouvelle configuration (SQLite ou PostgreSQL), avec test de
  connexion ;
- annuler une configuration en attente — sans jamais toucher à la
  configuration active ni à aucune base existante.

**Important : aucun changement de moteur n'est jamais appliqué en cours de
session.** Toute configuration préparée depuis cet écran ne devient active
qu'au prochain redémarrage complet de l'application.

## 4. Coffre d'identifiants (mot de passe PostgreSQL)

Le mot de passe PostgreSQL n'est **jamais** écrit en clair dans un fichier,
une base de données ou les journaux. Sous Windows, il est stocké
exclusivement dans **Windows Credential Manager**, via la bibliothèque
`keyring`. StockManager vérifie explicitement, à chaque opération, que le
coffre réellement utilisé est bien Windows Credential Manager — si un autre
mécanisme de stockage était sélectionné ou si le coffre est indisponible,
StockManager **refuse** l'opération plutôt que de basculer silencieusement
vers un stockage moins sûr.

Le fichier de configuration externe (`db_config.json`, dans le répertoire de
données de l'application) ne contient jamais le mot de passe — seulement un
identifiant technique (`credential_key`) permettant de retrouver le mot de
passe correspondant dans le coffre. Si ce fichier et le coffre ne
correspondent plus (coffre vidé manuellement, profil copié d'un autre
poste), StockManager ne tente aucune reconstruction automatique du secret :
la connexion échoue explicitement, et l'administrateur doit reconfigurer le
mot de passe depuis l'écran d'administration.

## 5. Erreurs fréquentes

| Message/situation | Cause probable | À faire |
|---|---|---|
| « Connexion impossible : vérifiez l'hôte, le port... » | Serveur inaccessible, mauvais port, mauvais identifiants, pare-feu | Vérifier les paramètres réseau et les identifiants auprès de l'administrateur PostgreSQL |
| « PostgreSQL indisponible sur ce poste : ... » | Windows Credential Manager désactivé ou inaccessible | Vérifier que le service Windows correspondant est démarré ; contacter le support informatique si le problème persiste |
| Démarrage de l'application impossible, message générique au lancement | Configuration PostgreSQL devenue invalide (serveur éteint, identifiants changés côté serveur) | Voir « Retour à SQLite » ci-dessous, ou corriger la configuration PostgreSQL puis redémarrer |
| Mot de passe introuvable dans le coffre pour un profil donné | Fichier de configuration et coffre désynchronisés (voir §4) | Reconfigurer le mot de passe depuis l'écran d'administration |

## 6. Sauvegarde et restauration PostgreSQL (Lot E)

L'écran **Sauvegardes** (même écran que pour SQLite, voir
`app/views/pages/backups_page.py`) affiche toujours le moteur actif et
adapte ses actions en conséquence — jamais une sauvegarde SQLite présentée
comme une sauvegarde PostgreSQL, ni l'inverse.

### 6.1. Méthode et format

Les sauvegardes PostgreSQL utilisent les outils officiels `pg_dump`/
`pg_restore` (format personnalisé `-Fc`), jamais une bibliothèque tierce ni
une copie de fichier brute. Le fichier produit porte l'extension `.dump`
(préfixe `stockmanager_backup_pg_AAAAMMJJ_HHMMSS`), toujours distinct des
sauvegardes SQLite (`.db`) — les deux types peuvent coexister dans le même
dossier de destination (ex. un poste ayant changé de moteur) sans jamais
être confondus : l'historique affiche le moteur de chaque entrée, et seule
une sauvegarde correspondant au moteur **actif** peut être restaurée.

### 6.2. Sauvegarde

Une sauvegarde manuelle (ou planifiée, mêmes réglages que pour SQLite)
appelle `pg_dump` avec les identifiants de la configuration active
(mot de passe résolu depuis le coffre d'identifiants, jamais écrit en
clair). Le mot de passe n'est jamais transmis en argument de ligne de
commande ni journalisé — il est fourni uniquement via la variable
d'environnement `PGPASSWORD` du sous-processus `pg_dump`/`pg_restore`
concerné, jamais celle du processus StockManager. Le fichier est d'abord
écrit dans un fichier temporaire du dossier de destination, puis renommé de
façon atomique vers son nom final — uniquement après un code de retour nul
**et** un fichier non vide ; en cas d'échec, le fichier temporaire est
supprimé, jamais laissé en place. La sauvegarde créée est ensuite
systématiquement revérifiée (`pg_restore --list`, lecture seule) avant
d'être présentée comme réussie.

### 6.3. Restauration

La restauration est toujours précédée d'une confirmation explicite côté
interface, puis, côté service :

1. vérification structurelle de l'archive (`pg_restore --list`, sans jamais
   se connecter à aucun serveur) et des tables attendues ;
2. comparaison de la version de schéma embarquée dans l'archive avec celle
   de la base active — version différente, restauration refusée ;
3. sauvegarde de sécurité de la base active (même convention que pour
   SQLite, préfixe `stockmanager_prerestore_pg_...`) ;
4. restauration proprement dite, avec `pg_restore --single-transaction
   --clean --if-exists --no-owner --no-privileges` : l'ensemble de
   l'opération s'exécute dans **une seule transaction SQL côté serveur** —
   tout échec en cours de restauration annule l'intégralité de la
   transaction, la base active n'est alors jamais modifiée (contrairement à
   SQLite, où un remplacement de fichier partiel est en théorie possible,
   d'où la sauvegarde de secours systématique de ce moteur). `--no-owner
   --no-privileges` garantit qu'aucun rôle ni permission serveur n'est
   jamais créé ou modifié par une restauration.

La restauration cible toujours la base déjà désignée par la configuration
active : StockManager ne crée **jamais** automatiquement de base ni de rôle
PostgreSQL pour une restauration — la base cible doit déjà exister,
préparée par un administrateur PostgreSQL (même règle que pour la
configuration de connexion elle-même, §1).

### 6.4. Si `pg_dump`/`pg_restore` sont absents

StockManager vérifie leur présence avant toute tentative et affiche un
message explicite indiquant lequel des deux outils manque — jamais une
erreur de sous-processus confuse. Installez le client PostgreSQL
correspondant à la version du serveur, puis réessayez.

### 6.5. Diagnostiquer un échec de sauvegarde/restauration (Lot E.7)

Le message affiché à l'écran en cas d'échec reste volontairement générique
(jamais de détail technique, jamais de secret). Pour diagnostiquer la
cause réelle, consultez le **journal applicatif** (voir §8) : chaque échec
de `pg_dump`/`pg_restore` y est désormais journalisé avec le message
d'erreur réel renvoyé par l'outil (ex. identifiants refusés, serveur
inaccessible, espace disque insuffisant) ainsi que la version locale de
l'outil utilisé — utile en particulier pour corréler une éventuelle
incompatibilité de version entre le client `pg_dump`/`pg_restore` installé
sur le poste et le serveur PostgreSQL cible, que StockManager ne tente
jamais de vérifier par avance (voir §10, « Limites connues »). Le mot de
passe PostgreSQL n'apparaît jamais dans ce journal.

## 7. Retour à SQLite sans perte de données

Le retour à SQLite ne supprime jamais ni la base PostgreSQL, ni un éventuel
fichier SQLite déjà présent sur le poste :

1. Depuis l'écran d'administration (si l'application démarre normalement),
   sélectionnez **SQLite** puis **Enregistrer comme configuration en
   attente**, puis redémarrez l'application.
2. Si l'application ne démarre plus (serveur PostgreSQL devenu
   inaccessible), un administrateur technique peut éditer manuellement le
   fichier `db_config.json` (répertoire de données de l'application) et
   remplacer son contenu par :
   ```json
   {"version": 1, "active": {"backend": "sqlite", "postgresql": null}, "pending": null}
   ```
   puis redémarrer l'application. Le fichier SQLite précédemment utilisé
   (s'il existe) est repris tel quel, sans aucune perte.

## 8. Notes pour les développeurs

- `app/config/db_config_store.py` : persistance JSON versionnée,
  actif/en attente, jamais de secret, écriture atomique, tolérante à tout
  fichier absent/corrompu/incompatible (repli SQLite systématique).
- `app/security/credential_vault.py` : interface `CredentialVault` +
  implémentation Windows (`keyring`, backend vérifié explicitement à
  chaque opération). Hors Windows, `get_credential_vault()` refuse
  toujours explicitement — jamais de repli vers un autre backend.
- `app/services/database_admin/database_admin_service.py` : logique
  métier (fonctions `*_unchecked`, réutilisées sans vérification de
  permission par l'assistant pré-authentification) + façade
  `DatabaseAdminService` (vérifie `DATABASE_CONFIG_VIEW`/
  `DATABASE_CONFIG_UPDATE` côté service, jamais seulement côté interface).
- `app/main.py` : `QApplication` créée avant toute initialisation risquée ;
  `apply_pending_db_config_if_any()` promeut une configuration en attente
  **une seule fois**, avant le premier appel à `get_settings()` du
  processus — jamais en cours de session.
- `app/views/database_setup_wizard.py` (pré-authentification) et
  `app/views/pages/database_admin_page.py` (post-authentification,
  Administrateur) : deux interfaces distinctes réutilisant la même logique
  de service.
- `app/services/backups/postgresql_backup_engine.py` (Lot E) : mécanique
  pure `pg_dump`/`pg_restore` (sauvegarde, vérification d'archive,
  restauration), pendant PostgreSQL de `backup_engine.py` (SQLite) —
  `app/services/backups/backup_service.py` orchestre les deux (permissions,
  audit, choix du moteur) sans jamais les mélanger.
- `stockmanager.spec` (Lot E) : `hiddenimports` couvre désormais
  explicitement `sqlalchemy.dialects.postgresql`/`psycopg` (résolution
  dynamique de dialecte, invisible à l'analyse statique de PyInstaller —
  même mécanisme que `sqlite`, précédemment seul couvert) et
  `keyring.backends.Windows` + ses dépendances conditionnelles ; `datas`
  inclut `copy_metadata("keyring")` (découverte de backend par points
  d'entrée, également invisible à l'analyse statique). Voir
  `packaging/README.md`, section « Lot E ».
- `app/services/backups/postgresql_backup_engine.py` (Lot E.7, §6.5) :
  chaque échec de `pg_dump`/`pg_restore` est désormais journalisé avec le
  détail technique réel (`stderr`, tronqué à 4000 caractères) et la version
  locale de l'outil — jamais le mot de passe, jamais affiché à
  l'utilisateur (message générique côté `BackupService`/`BackupsPage`).
  `app/views/pages/backups_page.py` affiche également l'hôte/le port/la
  base PostgreSQL cibles (jamais le mot de passe) dans le bandeau « moteur
  actif » et la confirmation de restauration — lecture seule de la
  configuration déjà active, jamais un moyen de choisir une autre base.

## 9. Procédure de validation Windows (checklist reproductible)

Référencée depuis `packaging/README.md` (« Tests obligatoires sous
Windows »). Chaque étape suppose la précédente réussie ; s'arrêter et
corriger avant de continuer si une étape échoue — ne jamais présenter une
étape suivante comme validée si une étape antérieure a échoué.

1. `pip install -r requirements-build.txt` dans un environnement Windows
   propre (Python 3.11.x).
2. `python packaging\generate_icon.py` puis
   `python packaging\generate_version_info.py` (uniquement si
   `app/version.py` ou le symbole source ont changé).
3. `pyinstaller stockmanager.spec --clean` — build réussi, pas d'erreur
   fatale (des avertissements « hidden import not found » n'apparaissant
   que sous Linux, voir `packaging/README.md`, ne doivent plus apparaître
   ici).
4. Lancer `dist\StockManager\StockManager.exe` sur un poste n'ayant jamais
   eu StockManager installé : l'assistant de première configuration
   s'affiche, SQLite fonctionne par défaut.
5. Depuis l'assistant ou l'écran d'administration (après un premier
   démarrage en SQLite), configurer PostgreSQL vers un serveur de test
   réel : le test de connexion réussit, un mot de passe est enregistré.
6. Vérifier, par un moyen de diagnostic (log applicatif, ou un petit script
   Python exécuté dans le même environnement que l'exécutable) que
   `keyring.get_keyring()` retourne bien une instance de
   `keyring.backends.Windows.WinVaultKeyring` — jamais un autre backend,
   jamais `keyring.backends.fail.Keyring`.
7. Redémarrer l'application : la configuration PostgreSQL devient active,
   la connexion réussit.
8. Depuis l'écran Sauvegardes : créer une sauvegarde PostgreSQL (nécessite
   `pg_dump`/`pg_restore` installés sur ce poste), puis la restaurer dans la
   même base de test — vérifier que les données attendues sont bien
   présentes après restauration, pas seulement que l'opération se termine
   sans erreur.
9. Compiler l'installateur Inno Setup (`ISCC.exe packaging\inno_setup.iss`),
   l'installer, le désinstaller : les données utilisateur
   (`%APPDATA%\StockManager`) doivent survivre à la désinstallation.
10. Réinstaller par-dessus une installation existante (mise à jour) :
    les données utilisateur et la configuration active doivent être
    préservées à l'identique.

Tant que cette checklist n'a pas été exécutée sur un poste Windows réel,
aucune étape ci-dessus ne doit être présentée comme validée — voir « Limites
connues » ci-dessous.

## 10. Limites connues (à lever avant toute mise en production)

- **Aucune validation sur un poste Windows réel** : le comportement de
  `keyring`/Windows Credential Manager et l'empaquetage PyInstaller de la
  dépendance `keyring` n'ont été vérifiés que par des tests automatisés sous
  Linux (où le coffre est, par construction, toujours indisponible — voir
  `tests/test_credential_vault.py`) et par un build/exécution PyInstoller
  **Linux** (Lot E — voir `packaging/README.md`, section « Lot E ») : ce
  dernier démontre que les modules et métadonnées nécessaires sont bien
  inclus dans l'archive gelée, **pas** que `WinVaultKeyring` est réellement
  sélectionné ni que l'installateur Windows fonctionne. La checklist du §9
  ci-dessus reste entièrement à exécuter sur un poste Windows réel.
- **Aucune validation contre PostgreSQL 18.x** (cible officielle du projet) :
  tous les tests d'intégration de ce lot, comme ceux des lots précédents,
  ont été exécutés contre PostgreSQL 16.15.
- **Aucune vérification préalable de compatibilité de version** entre le
  client `pg_dump`/`pg_restore` installé sur le poste et le serveur
  PostgreSQL cible (Lot E.7, §6.5) : décision délibérée (une telle
  vérification côté client serait fragile), pas une garantie — seul un
  diagnostic *a posteriori*, via le journal applicatif, est fourni en cas
  d'échec réel.
- Un échec de connexion au démarrage affiche un message générique sans
  rediriger automatiquement vers l'écran d'administration (qui nécessite
  une connexion réussie à la base pour authentifier un administrateur) —
  la correction manuelle du fichier de configuration (§7) reste le seul
  recours si l'application ne démarre plus du tout.
- **Sauvegarde/restauration PostgreSQL** (Lot E) : validée par des tests
  automatisés contre un serveur PostgreSQL 16.15 réel sous Linux (y compris
  une restauration réelle comparée à des données représentatives avant/
  après, pas seulement la création d'une archive — voir le rapport de
  phase), mais **jamais exécutée depuis l'exécutable Windows packagé**, ni
  avec les versions de `pg_dump`/`pg_restore` qu'un client installerait
  réellement (version du client PostgreSQL potentiellement différente de
  celle du serveur).
