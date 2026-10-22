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

## 6. Retour à SQLite sans perte de données

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

## 7. Notes pour les développeurs

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

## 8. Limites connues (à lever avant toute mise en production)

- **Aucune validation sur un poste Windows réel** : le comportement de
  `keyring`/Windows Credential Manager et l'empaquetage PyInstoller de la
  dépendance `keyring` n'ont été vérifiés que par des tests automatisés sous
  Linux (où le coffre est, par construction, toujours indisponible — voir
  `tests/test_credential_vault.py`).
- **Aucune validation contre PostgreSQL 18.x** (cible officielle du projet) :
  tous les tests d'intégration de ce lot, comme ceux des lots précédents,
  ont été exécutés contre PostgreSQL 16.15.
- Un échec de connexion au démarrage affiche un message générique sans
  rediriger automatiquement vers l'écran d'administration (qui nécessite
  une connexion réussie à la base pour authentifier un administrateur) —
  la correction manuelle du fichier de configuration (§6) reste le seul
  recours si l'application ne démarre plus du tout.
