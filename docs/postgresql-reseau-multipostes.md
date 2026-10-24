# PostgreSQL en réseau local — 2 à 5 postes (Évolution H)

Ce document couvre le partage d'une **même base PostgreSQL 16.15** entre
plusieurs postes StockManager Desktop d'une boutique/bureau (2 à 5 postes
visés) : un poste héberge le serveur PostgreSQL, les autres s'y connectent
comme clients. Il complète `docs/postgresql-configuration.md` (configuration
*locale* du moteur sur un seul poste, déjà couverte) sans le dupliquer — la
procédure ci-dessous se concentre sur ce que l'exposition réseau ajoute :
identification du réseau réel, `postgresql.conf`/`pg_hba.conf`, pare-feu
Windows, rôle applicatif dédié, tests de connectivité, et les limites de
l'architecture actuelle en usage multi-postes.

**Aucune adresse IP, aucun sous-réseau ci-dessous n'est une valeur réelle** :
chaque exemple utilise la plage documentaire réservée RFC 5737
(`192.0.2.0/24`) ou des espaces réservés explicites (`<...>`), à remplacer
par les valeurs **effectivement observées sur le réseau du client** — jamais
une adresse supposée ou copiée telle quelle depuis ce document.

## 1. Architecture ciblée

```
                     Réseau local du magasin/bureau
                     (un seul sous-réseau, filaire ou Wi-Fi)

  Poste 1 (serveur)              Poste 2            Poste 3  ...  Poste 5
  ┌─────────────────┐        ┌───────────────┐   ┌───────────────┐
  │ PostgreSQL 16.15 │◄──────┤ StockManager  │   │ StockManager  │
  │ (service Windows)│◄──────┤ Desktop       │   │ Desktop       │
  │ StockManager      │        │ (moteur=      │   │ (moteur=      │
  │ Desktop (client   │        │  postgresql)  │   │  postgresql)  │
  │  local, optionnel)│        └───────────────┘   └───────────────┘
  └─────────────────┘
```

- Un seul serveur PostgreSQL central, une seule base partagée par tous les
  postes autorisés.
- StockManager Desktop reste installé **identiquement** sur chaque poste
  (aucune variante "client seul"/"serveur" du logiciel applicatif lui-même :
  seul PostgreSQL, lui, n'est installé que sur le poste serveur).
- Le poste serveur peut lui aussi faire tourner StockManager Desktop en
  client local (connexion à `127.0.0.1`, ou à sa propre adresse réseau —
  les deux fonctionnent, voir §7).
- SQLite reste disponible pour une installation autonome (un seul poste,
  aucun partage) : un poste qui n'a pas besoin de partager ses données n'a
  jamais besoin de suivre ce document.
- **Jamais de bascule silencieuse** : chaque poste a son propre fichier de
  configuration active (voir `docs/postgresql-configuration.md`, §3) —
  rien ici n'automatise le choix du moteur ni ne le change pour un poste
  qui n'a pas été explicitement configuré.

## 2. Ce que ce lot ne fait jamais

- **N'ouvre jamais le port PostgreSQL sur Internet.** Toute la procédure
  ci-dessous restreint `pg_hba.conf` et le pare-feu Windows au seul
  sous-réseau local réel du magasin/bureau (§4, §5) — jamais `0.0.0.0/0`.
- **N'expose jamais le rôle superutilisateur `postgres`** aux postes
  clients : un rôle applicatif dédié, non superutilisateur, est créé pour
  StockManager Desktop (§4.3).
- **Ne crée jamais automatiquement** le serveur PostgreSQL, la base ou les
  rôles : chaque étape ci-dessous est une action explicite de
  l'administrateur réseau/PostgreSQL, jamais un comportement automatique de
  StockManager Desktop.
- **N'est pas une architecture client/serveur applicative.** Chaque poste
  continue de dialoguer **directement** avec PostgreSQL (protocole
  PostgreSQL natif, pilote `psycopg`), exactement comme en configuration
  locale à un seul poste — il n'existe aucun serveur d'application ni API
  intermédiaire StockManager. Les limites de concurrence documentées au §9
  découlent de ce choix, pas d'un défaut d'implémentation réseau.

---

## 3. Étape 1 — Identifier le réseau réel du poste serveur

Sur le **poste qui hébergera PostgreSQL**, ouvrir une invite de commandes et
exécuter :

```
ipconfig
```

Repérer la section de l'adaptateur réellement utilisé pour le réseau local
du magasin/bureau (Ethernet ou Wi-Fi — ignorer les adaptateurs virtuels
type VPN/hyperviseur) et noter :

- **Adresse IPv4** (ex. affichée `Adresse IPv4. . . . . . . . . . . : 10.X.X.X` —
  la valeur réelle, jamais `10.X.X.X` lui-même).
- **Masque de sous-réseau** (ex. `255.255.255.0`).

Convertir masque + adresse en notation CIDR (ex. `255.255.255.0` =
`/24`) pour obtenir le sous-réseau complet, par exemple
`<adresse-reseau-reelle>/24` — c'est **cette valeur réelle**, jamais un
exemple de ce document, qui sera utilisée aux §4 et §5.

En cas de doute sur le sous-réseau réel (plusieurs adaptateurs, réseau
segmenté), consulter l'administrateur réseau du site plutôt que de
deviner : une valeur de sous-réseau trop large exposerait PostgreSQL à des
postes non autorisés (§2).

## 4. Étape 2 — Configurer PostgreSQL pour accepter des connexions réseau

Sur le **poste serveur**, localiser `postgresql.conf` et `pg_hba.conf`
(typiquement `C:\Program Files\PostgreSQL\16\data\`).

### 4.1. `postgresql.conf` — écouter sur l'interface réseau

Par défaut, PostgreSQL n'écoute que sur `localhost` — inutilisable depuis
un autre poste. Modifier (ou ajouter) :

```
listen_addresses = '*'
```

`'*'` écoute sur toutes les interfaces locales (y compris `localhost`) ;
c'est `pg_hba.conf` (§4.2), pas `listen_addresses`, qui restreint réellement
*qui* peut se connecter — ne pas confondre les deux. Une alternative plus
restrictive, si le poste serveur n'a qu'une seule interface réseau
pertinente, est de lister explicitement l'adresse IPv4 relevée au §3 à la
place de `*` (ex. `listen_addresses = 'localhost,<adresse-ipv4-reelle>'`).

### 4.2. `pg_hba.conf` — autoriser uniquement le sous-réseau local réel

Ajouter une ligne dédiée à StockManager Desktop, **jamais** une règle
`0.0.0.0/0` ni `trust` :

```
# StockManager Desktop — postes autorisés du réseau local uniquement
hostssl stockmanager_prod stockmanager_app <sous-reseau-reel-du-site>/24 scram-sha-256
```

- `stockmanager_prod` : nom de la base applicative (adapter au nom réel
  configuré, voir `docs/postgresql-configuration.md`, §3 — jamais `all`,
  qui autoriserait aussi les autres bases éventuellement présentes sur ce
  serveur).
- `stockmanager_app` : le rôle applicatif dédié créé au §4.3 — jamais
  `postgres` (§2).
- `<sous-reseau-reel-du-site>/24` : la valeur relevée au §3, jamais un
  exemple de ce document.
- `hostssl` (plutôt que `host`) force une connexion chiffrée TLS entre
  chaque poste client et le serveur — PostgreSQL génère par défaut un
  certificat auto-signé suffisant pour un réseau local fermé ; un
  certificat signé par une autorité interne au site, si disponible, reste
  préférable mais n'est pas requis ci-dessous.
- `scram-sha-256` : méthode d'authentification par mot de passe actuelle de
  PostgreSQL (jamais `trust`, qui n'exigerait aucun mot de passe, ni
  `password`, qui le transmettrait en clair sans `hostssl`).

Conserver les lignes déjà présentes pour `127.0.0.1/32`/`::1/128` (accès
local au poste serveur lui-même, déjà couvert par
`docs/postgresql-configuration.md`) — cette procédure n'en retire aucune,
elle n'ajoute que l'accès réseau.

### 4.3. Rôle applicatif dédié, non superutilisateur

Sur le poste serveur, dans `psql` (ou pgAdmin) :

```sql
CREATE ROLE stockmanager_app WITH LOGIN PASSWORD '<mot-de-passe-robuste>';
GRANT ALL PRIVILEGES ON DATABASE stockmanager_prod TO stockmanager_app;
\c stockmanager_prod
GRANT ALL ON SCHEMA public TO stockmanager_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO stockmanager_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO stockmanager_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO stockmanager_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO stockmanager_app;
```

`stockmanager_app` n'est **jamais** `SUPERUSER` ni `CREATEDB`/`CREATEROLE` —
seuls les privilèges nécessaires au fonctionnement applicatif (lecture/
écriture des tables, séquences, et schéma pour les migrations Alembic, qui
créent/modifient des tables) lui sont accordés. C'est ce rôle, jamais
`postgres`, qui est saisi dans l'assistant de configuration StockManager de
chaque poste (§7).

### 4.4. Redémarrer PostgreSQL

Les deux fichiers modifiés nécessitent un redémarrage du service :

```
services.msc
```

Rechercher le service `postgresql-x64-16` (ou équivalent), clic droit →
Redémarrer. Confirmer ensuite dans le journal PostgreSQL
(`C:\Program Files\PostgreSQL\16\data\log\`) l'absence d'erreur au
démarrage.

## 5. Étape 3 — Pare-feu Windows (poste serveur uniquement)

Sur le **poste serveur**, créer une règle entrante restreinte au seul
sous-réseau local réel — jamais une règle ouverte à tout le réseau ni à
Internet :

```powershell
New-NetFirewallRule -DisplayName "PostgreSQL StockManager (reseau local)" `
    -Direction Inbound -Protocol TCP -LocalPort 5432 `
    -RemoteAddress <sous-reseau-reel-du-site>/24 `
    -Action Allow
```

(Équivalent via l'interface graphique : *Pare-feu Windows Defender avec
sécurité avancée* → *Règles de trafic entrant* → *Nouvelle règle* → Port →
TCP 5432 → *Adresses IP distantes spécifiques* → saisir le sous-réseau réel
du §3 → Autoriser.)

Ne jamais créer de règle équivalente sur un profil **Public** si le poste
serveur bascule parfois sur ce profil réseau (ex. portable) — restreindre
la règle au profil **Privé/Domaine** correspondant au réseau du magasin.

## 6. Étape 4 — Tests de connectivité depuis chaque poste client

Avant de configurer StockManager Desktop lui-même sur un poste client,
valider la connectivité réseau brute :

```
Test-NetConnection -ComputerName <adresse-ipv4-reelle-du-serveur> -Port 5432
```

`TcpTestSucceeded : True` confirme que le réseau et le pare-feu (§5)
laissent bien passer la connexion. Un résultat `False` indique un problème
réseau/pare-feu **avant** PostgreSQL lui-même — à résoudre avant de
poursuivre (vérifier le câblage/Wi-Fi, le profil de pare-feu actif, et que
le sous-réseau saisi au §5 couvre bien l'adresse du poste client testé).

Si `psql` est également installé sur le poste client (ex. client
PostgreSQL requis pour `pg_dump`/`pg_restore`, voir
`docs/postgresql-configuration.md`, §6), une validation applicative directe
est possible :

```
psql -h <adresse-ipv4-reelle-du-serveur> -p 5432 -U stockmanager_app -d stockmanager_prod
```

Une invite de mot de passe suivie d'une connexion réussie confirme
`pg_hba.conf` (§4.2) et l'authentification du rôle applicatif.

## 7. Étape 5 — Configurer StockManager Desktop sur chaque poste client

Suivre intégralement `docs/postgresql-configuration.md` (§3, assistant de
première configuration ou écran d'administration) sur **chaque poste**,
avec :

- **Hôte** : l'adresse IPv4 réelle du poste serveur relevée au §3 (jamais
  `localhost`/`127.0.0.1` sur un poste qui n'est pas le serveur lui-même).
- **Port** : `5432` (sauf changement explicite du côté serveur).
- **Base** : `stockmanager_prod` (ou le nom réel configuré au §4.3).
- **Utilisateur** : `stockmanager_app` (jamais `postgres`, §2).
- **Mot de passe** : celui défini au §4.3, saisi une fois par poste et
  stocké par le Gestionnaire d'informations d'identification Windows de
  **ce poste** (jamais partagé en clair entre postes, jamais inscrit dans
  un fichier de configuration — voir `docs/postgresql-configuration.md`,
  §4).

Chaque poste doit utiliser la **même base** (`stockmanager_prod`) pour que
les données soient réellement partagées — une erreur de frappe sur le nom
de la base isolerait silencieusement ce poste sur une base vide ou
inexistante plutôt que de le faire échouer de façon visible ; vérifier le
nom affiché à l'écran de résumé de l'assistant avant de valider.

## 8. Étape 6 — Vérifier le moteur actif après redémarrage

Le changement de moteur actif nécessite un redémarrage complet de
StockManager Desktop (jamais à chaud, voir le mandat — déjà le
comportement actuel, non modifié par ce lot). Après redémarrage de chaque
poste :

1. Se connecter normalement.
2. Écran d'administration de la base (Administrateur) → vérifier que le
   moteur actif affiché est bien **PostgreSQL**, avec l'hôte/port/base
   attendus (jamais le mot de passe, qui n'y est jamais affiché).
3. Créer un enregistrement de test depuis **ce** poste (ex. un article) et
   confirmer son apparition **immédiate** sur un **autre** poste déjà
   ouvert, après un simple retour sur l'écran concerné (comportement
   attendu depuis les Incidents B/C de ce même plan, et déjà valable pour
   les mouvements de stock, ventes, etc. — voir §9 pour les limites
   connues en usage simultané).

## 9. Étape 7 — Tests simultanés multi-postes

Avec au moins deux postes connectés à la même base, dérouler en parallèle
(un opérateur par poste, ou un seul opérateur alternant rapidement entre
deux sessions) :

- **Ventes** : créer une vente sur chaque poste en même temps, sur des
  articles différents puis sur le **même** article — confirmer que le
  stock final reflète bien la somme des deux ventes (jamais l'écrasement
  de l'une par l'autre, voir §10.1 : déjà garanti par construction).
- **Mouvements de stock** : une entrée sur un poste et une sortie sur
  l'autre, simultanément, sur le même article — même vérification.
- **Inventaires** : un inventaire en cours sur un poste ne doit jamais
  empêcher les opérations courantes (ventes, entrées/sorties) sur les
  autres postes sur des articles non concernés par cet inventaire.
- **Locations** : un départ de location sur un poste et un retour sur un
  autre, sur des lignes différentes d'une même location, puis vérification
  de la cohérence du statut final.
- **Création de client/article depuis un poste** : visible immédiatement
  sur les autres (Incidents B/C) sans reconnexion.

Consigner tout comportement inattendu (message d'erreur, délai anormal,
incohérence de stock) pour investigation ciblée avant mise en production —
ne jamais le contourner par une nouvelle tentative silencieuse.

## 10. Limites de l'architecture actuelle en usage multi-postes

Analyse du code existant (``app/services/stock/stock_service.py``,
``app/db/session.py``, ``app/db/init_db.py``) au regard d'un usage à
plusieurs postes simultanés — ce que l'architecture garantit déjà, et ce
qui reste une discipline opérationnelle plutôt qu'une protection
automatique.

### 10.1. Concurrence sur le stock — déjà sûre, y compris sous PostgreSQL

`StockService.apply_movement` applique toute variation de stock par une
unique instruction SQL ``UPDATE ... SET stock_actuel = stock_actuel + :delta
WHERE ... RETURNING`` (correctif P0-1, déjà en place avant ce lot) : deux
postes qui modifient simultanément le stock du **même** article sont
sérialisés par le verrou de ligne que PostgreSQL acquiert pour la durée de
la transaction en cours — la seconde écriture attend la fin de la première,
puis s'applique sur la valeur réellement à jour, jamais sur une valeur
obsolète. C'est le même résultat que le verrou d'écriture, plus large,
qu'utilise SQLite pour obtenir cette garantie à un seul poste — PostgreSQL
l'obtient ici de façon plus fine (verrou par ligne, jamais par base
entière), ce qui autorise en plus deux postes à modifier **deux articles
différents** sans qu'aucun n'attende l'autre. **Aucun correctif requis** :
ce mécanisme, conçu à l'origine pour un seul poste, s'étend correctement au
cas multi-postes sans modification.

### 10.2. Migrations Alembic au démarrage — risque réel si plusieurs postes démarrent en même temps après une mise à jour

`app/db/init_db.py::init_database` exécute ``alembic upgrade head`` à
chaque démarrage de StockManager Desktop (idempotent : sans effet si le
schéma est déjà à jour). Si la base est déjà à la dernière version, ceci
est sans risque, quel que soit le nombre de postes démarrés simultanément.

**Risque documenté** : juste après le déploiement d'une mise à jour de
StockManager Desktop sur tous les postes (nouvelle version du logiciel,
donc de nouvelles migrations Alembic à appliquer), si **plusieurs postes
sont rallumés en même temps**, chacun tenterait d'exécuter les migrations
manquantes contre la **même** base au même instant — Alembic ne pose ici
aucun verrou consultatif (``pg_advisory_lock``) autour de l'exécution des
migrations ; deux processus concurrents appliquant des ``CREATE TABLE``/
``ALTER TABLE`` sur le même schéma peuvent se bloquer mutuellement ou
échouer avec une erreur de contention, selon le minutage exact.

**Correctif ciblé recommandé (procédure, pas de code)** : après toute mise
à jour de StockManager Desktop touchant plusieurs postes partageant une
base PostgreSQL, démarrer **un seul poste d'abord**, attendre la fin du
démarrage (écran de connexion affiché = migrations terminées), **puis**
démarrer les autres postes. Cette discipline élimine entièrement le risque
sans modification du code — une solution par verrou applicatif
(``pg_advisory_lock`` autour de l'appel à ``command.upgrade``) reste
possible dans un lot ultérieur si cette discipline s'avère insuffisante en
pratique, mais représente un changement de code plus large, hors périmètre
de ce lot (examen + procédure).

### 10.3. Restauration PostgreSQL — jamais avec un autre poste connecté

`restore_database_from_backup` (``app/services/backups/
postgresql_backup_engine.py``) exécute ``pg_restore --clean --if-exists
--single-transaction`` : chaque table est supprimée puis recréée au sein
d'une unique transaction. Si un **autre poste** est connecté et actif
pendant cette opération, ses requêtes sur les tables concernées
attendraient la fin de la transaction de restauration (verrou exclusif sur
``DROP TABLE``) ou échoueraient si la restauration intervient entre deux de
ses propres opérations.

**Correctif ciblé recommandé (procédure, pas de code)** : une restauration
PostgreSQL ne doit **jamais** être déclenchée tant qu'un autre poste a
StockManager Desktop ouvert et connecté à la même base — fermer
StockManager Desktop sur tous les autres postes avant de restaurer, le
rouvrir seulement après confirmation du succès de la restauration. À
documenter explicitement dans l'écran de restauration lui-même dans un lot
ultérieur si ce rappel procédural s'avère insuffisant (hors périmètre de ce
lot).

### 10.4. Nombre de connexions — sans risque réel à l'échelle visée (2 à 5 postes)

Chaque poste ouvre son propre moteur SQLAlchemy avec le pool de connexions
par défaut (5 connexions de base, jusqu'à 10 supplémentaires en pointe) —
jusqu'à 15 connexions par poste dans le pire cas, soit au plus 75 pour 5
postes. La limite par défaut de PostgreSQL (``max_connections = 100``)
couvre largement cette échelle. **Aucun correctif requis** pour la cible de
ce lot (2 à 5 postes) ; au-delà d'une dizaine de postes, revoir
``max_connections`` côté serveur deviendrait pertinent — hors périmètre
actuel.

### 10.5. Ce lot n'est pas une architecture serveur d'application

Chaque poste dialogue directement avec PostgreSQL (§2) : il n'existe aucune
couche métier centralisée côté serveur qui validerait une règle une seule
fois pour tous les postes. Chaque instance de StockManager Desktop
réapplique indépendamment les mêmes règles métier (déjà le cas avant ce
lot, inchangé) ; les contraintes PostgreSQL (clés étrangères, contraintes
``CHECK``, et le verrouillage de ligne du §10.1) restent le filet de
sécurité commun final, partagé par construction entre tous les postes
puisqu'ils ciblent la même base — aucune règle métier ne peut donc être
contournée par un poste sans que PostgreSQL lui-même ne la fasse
respecter.

---

## 11. Sauvegarde/restauration en contexte multi-postes

Suivre `docs/postgresql-configuration.md` (§6) pour la mécanique de
sauvegarde/restauration elle-même (inchangée par ce lot) — s'exécute
depuis **n'importe quel poste** disposant de `pg_dump`/`pg_restore` et
d'une connectivité réseau vers le serveur (§6 ci-dessus), pas
nécessairement le poste serveur lui-même. Pour la restauration
spécifiquement, voir l'avertissement du §10.3 : fermer StockManager Desktop
sur tous les postes avant de restaurer.
