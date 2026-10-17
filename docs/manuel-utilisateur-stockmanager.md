# Manuel utilisateur — StockManager Desktop

**Document de travail — source de rédaction**
Ce document Markdown est la source de contenu du futur manuel utilisateur. Il est destiné à être transformé en document DOCX professionnel, puis en PDF. Il ne contient pas encore de captures d'écran réelles : chaque emplacement de capture est signalé par un marqueur `[CAPTURE NN — TITRE]` à remplacer lors de la mise en forme finale.

Toutes les informations de ce document ont été vérifiées dans le code actuel de l'application. Lorsqu'une information ne peut pas être confirmée, elle est marquée **[À CONFIRMER]**. Lorsqu'une information doit être fournie par le client, un **placeholder** explicite est utilisé (`[NOM DE L'ENTREPRISE]`, `[ADRESSE]`, etc.) — aucune donnée client n'a été inventée.

---

## Sommaire

1. Page de couverture
2. Présentation de StockManager
3. Prérequis
4. Installation sous Windows
5. Premier lancement et guide de démarrage
6. Connexion et sécurité du compte
7. Tableau de bord
8. Paramètres de l'entreprise
9. Utilisateurs et rôles
10. Gestion du catalogue
11. Gestion du stock
12. Ventes et clients
13. Inventaires
13.5. Location d'articles (module Locations)
14. Rapports
15. Sauvegardes, restauration et réinitialisation des données métier
16. Journal d'audit
17. Licence
18. À propos et support
19. Bonnes pratiques
20. Dépannage
21. Glossaire
22. Annexe — Matrice complète des permissions
23. Annexe — Liste des captures d'écran à réaliser

---

# 1. Page de couverture

**StockManager Desktop**
Manuel utilisateur

Éditeur : TechNova
Client : [NOM DE L'ENTREPRISE]
Version du document : 1.0 — brouillon de travail
Version de l'application couverte : voir écran « À propos » (`app/version.py`)

[LOGO CLIENT]

---

# 2. Présentation de StockManager

StockManager Desktop est une application de gestion de stock installée directement sur un ordinateur (« application de bureau »), sans connexion Internet obligatoire pour fonctionner au quotidien.

Elle permet de :

- gérer un catalogue d'articles, de catégories et de fournisseurs ;
- suivre les mouvements de stock (entrées, sorties, ventes, inventaires) ;
- enregistrer des ventes et gérer une liste de clients ;
- gérer des **locations d'articles** (module Locations — réservation, départ, retour, facturation, caution ; voir le chapitre 13.5 pour le détail complet) pour les articles configurés dans ce mode de gestion ;
- consulter des tableaux de bord et des rapports ;
- sauvegarder et restaurer les données ;
- gérer les comptes des utilisateurs et leurs droits d'accès.

**Version actuelle** : StockManager est conçu pour être utilisé sur **un seul poste de travail**, avec une base de données stockée localement sur cet ordinateur (technologie SQLite). Il ne s'agit pas, dans cette version, d'une application partagée en réseau entre plusieurs ordinateurs.

> **Important** — Cette version ne synchronise pas les données entre plusieurs postes. Si plusieurs personnes doivent utiliser StockManager, elles doivent se connecter avec leur propre compte utilisateur **sur le même ordinateur**.

---

# 3. Prérequis

- Un ordinateur fonctionnant sous **Windows**.
- Les droits d'installation ne sont pas nécessairement des droits administrateur (l'installation se fait par défaut dans un dossier propre à l'utilisateur — voir chapitre 4).
- Un fichier de licence (`.lic`) fourni par votre éditeur ou intégrateur, pour débloquer les fonctionnalités de l'application au-delà de la simple connexion (voir chapitre 17).
- Aucune connexion Internet n'est nécessaire pour l'utilisation quotidienne ni pour l'activation de la licence.

---

# 4. Installation sous Windows

> **[À VALIDER SUR ENVIRONNEMENT WINDOWS]** — Le mécanisme d'installation décrit ci-dessous (exécutable généré par PyInstaller, installateur généré par Inno Setup) est en place dans le projet mais n'a pas encore été construit ni testé sur une machine Windows réelle au moment de la rédaction de ce document. Cette section devra être revérifiée et complétée une fois cette validation effectuée.

## Objectif
Installer StockManager Desktop sur un poste Windows.

## Procédure prévue

1. Récupérer le programme d'installation `StockManager-Setup-<version>.exe` fourni par votre éditeur ou administrateur système.
2. Lancer ce programme.
3. L'installation prévue ne nécessite pas de droits administrateur : elle s'effectue par défaut dans un dossier propre à l'utilisateur courant.
4. À la fin de l'installation, un raccourci est créé dans le menu Démarrer (et, selon l'option choisie, sur le Bureau).

## Emplacement des données

Les données de l'application (base de données, sauvegardes, journaux) sont conservées **séparément** du dossier d'installation, afin qu'une mise à jour ne les efface jamais :

| Donnée | Emplacement prévu (Windows) |
|---|---|
| Base de données | `%APPDATA%\StockManager\stockmanager.db` |
| Sauvegardes | `%APPDATA%\StockManager\backups\` (dossier modifiable dans Administration → Sauvegardes) |
| Journaux de diagnostic | `%APPDATA%\StockManager\logs\stockmanager.log` |

## Mise à jour et désinstallation

- **Mise à jour** : installer la nouvelle version par-dessus l'ancienne. Les données (`%APPDATA%\StockManager\`) ne sont jamais remplacées par une mise à jour.
- **Désinstallation** : depuis le Panneau de configuration Windows. Les données ne sont **jamais** supprimées automatiquement — à retirer manuellement si elles ne sont plus nécessaires.

---

# 5. Premier lancement et guide de démarrage

## Objectif
Comprendre ce qui se passe la toute première fois que StockManager est lancé, et suivre le parcours de mise en route recommandé.

## Ce qui se passe automatiquement au premier lancement

1. L'application crée automatiquement sa base de données locale.
2. Un compte **Administrateur** initial est créé automatiquement :
   - identifiant : `admin` ;
   - mot de passe : généré automatiquement de façon aléatoire.
3. Ce mot de passe temporaire est affiché **une seule fois**, dans le journal de démarrage de l'application (fichier de diagnostic — voir chapitre 20). Il n'est jamais réaffiché ensuite.

> **Attention** — Notez ce mot de passe temporaire dès le premier démarrage, ou demandez à la personne en charge de l'installation de vous le communiquer. Il devra de toute façon être changé dès la première connexion (voir ci-dessous).

## Parcours recommandé après installation

1. Se connecter avec le compte `admin` et le mot de passe temporaire (chapitre 6).
2. Changer immédiatement ce mot de passe (obligatoire, l'application l'impose).
3. Suivre le **guide de démarrage** qui s'affiche automatiquement à cette première connexion (voir ci-dessous).
4. Renseigner les informations de l'entreprise (chapitre 8).
5. Choisir la devise utilisée (chapitre 8).
6. Ajouter le logo de l'entreprise si souhaité (chapitre 8).
7. Créer les comptes des autres utilisateurs (chapitre 9).
8. Vérifier/activer la licence (chapitre 17).
9. Effectuer une première sauvegarde (chapitre 15).
10. Commencer l'utilisation normale de l'application (catalogue, stock, ventes...).

## Le guide de démarrage (fenêtre « Bien démarrer avec StockManager »)

Ce guide s'affiche **automatiquement, une seule fois**, à la toute première connexion réussie du compte administrateur initial (`admin`). Il ne réapparaît pas automatiquement aux connexions suivantes, y compris pour un autre compte administrateur créé plus tard.

Il présente une liste d'étapes recommandées, chacune avec :
- un état **« Terminé »** ou **« À faire »**, calculé en fonction de ce qui a déjà été configuré ;
- un bouton (« Configurer » ou « Ouvrir ») qui ouvre directement l'écran concerné.

Les étapes proposées (selon les droits du compte connecté) :
- Informations de l'entreprise et devise
- Logo de l'entreprise (optionnel)
- Utilisateurs
- Licence
- Première sauvegarde

Fermer ce guide (bouton « Fermer » ou croix de fermeture) ne bloque jamais l'utilisation de l'application — vous pouvez le fermer à tout moment, même sans avoir terminé toutes les étapes.

**Il peut être rouvert à tout moment** grâce au bouton **« Guide de démarrage »**, situé dans la barre supérieure de l'application (visible pour les comptes ayant accès aux Paramètres).

**Capture à insérer** : `[CAPTURE 03 — GUIDE DE DÉMARRAGE]`

---

# 6. Connexion et sécurité du compte

## Objectif
Se connecter à l'application et protéger son compte.

## Accès
Écran affiché automatiquement à l'ouverture de l'application.

## Description de l'écran
Deux champs : **Identifiant**, **Mot de passe**. Un bouton **« Se connecter »**.

## Procédure — Se connecter

1. Lancer StockManager Desktop.
2. Saisir votre identifiant et votre mot de passe.
3. Cliquer sur « Se connecter ».

## Résultat attendu
Le tableau de bord s'affiche (ou le guide de démarrage, s'il s'agit de la première connexion du compte administrateur initial — voir chapitre 5).

## Procédure — Changer son mot de passe (à tout moment)

1. Depuis n'importe quel écran, cliquer sur **« Changer le mot de passe »** dans la barre supérieure.
2. Renseigner le mot de passe actuel, puis le nouveau mot de passe (deux fois, pour confirmation).
3. Valider.

## Règles métier

- Un mot de passe doit contenir au moins **8 caractères**.
- Après une réinitialisation par un administrateur, ou lors de la création d'un nouveau compte, un changement de mot de passe est **obligatoire** à la prochaine connexion.

## Messages importants

| Situation | Message affiché |
|---|---|
| Identifiant ou mot de passe erroné | « Identifiant ou mot de passe incorrect. » (le message ne précise jamais lequel des deux est en cause, pour des raisons de sécurité) |
| Compte désactivé | « Ce compte est désactivé. » |
| Les deux mots de passe saisis ne correspondent pas | « Les deux mots de passe ne correspondent pas. » |

## Afficher le mot de passe saisi

Chaque champ de saisie de mot de passe (connexion, changement de mot de passe, création/réinitialisation d'un compte) comporte une icône « œil » permettant d'afficher temporairement le mot de passe en clair pendant la saisie, pour vérifier qu'il a été tapé correctement.

## Procédure — Récupérer l'accès à un compte Administrateur (sans autre administrateur disponible)

Un compte **Administrateur** qui ne peut plus se connecter (mot de passe oublié) peut récupérer l'accès par lui-même, à condition qu'un **code de récupération** ait été généré au préalable pour ce compte (voir chapitre 8, section « Code de récupération administrateur »).

1. Sur l'écran de connexion, cliquer sur **« Mot de passe oublié ? »**.
2. Saisir l'identifiant du compte, le code de récupération, puis le nouveau mot de passe (deux fois).
3. Valider.

**Règles et limites** :
- Cette récupération n'est possible que pour un compte de rôle **Administrateur**, actif, et disposant déjà d'un code de récupération généré.
- Le code est à **usage unique** : il est invalidé dès qu'il a servi (avec succès ou après un trop grand nombre d'échecs), et doit être régénéré pour être réutilisé.
- Après **5 tentatives échouées**, le compte est temporairement verrouillé (15 minutes) avant de pouvoir réessayer.
- Pour des raisons de sécurité, le message d'erreur affiché est **toujours identique** quelle que soit la cause réelle de l'échec (identifiant inconnu, compte non administrateur, code absent, incorrect, déjà utilisé, ou compte verrouillé) — il ne donne aucune indication permettant de deviner si un identifiant existe.
- Il n'existe **aucune** fonctionnalité de récupération en libre-service pour les comptes non-Administrateur (Gestionnaire de stock, Vendeur, Consultation) : seul un administrateur peut réinitialiser leur mot de passe (chapitre 9).

## Points d'attention
- Ne partagez jamais votre mot de passe avec un autre utilisateur (voir chapitre 19 — Bonnes pratiques).
- Ne partagez pas davantage un code de récupération administrateur généré : il permet de redéfinir le mot de passe du compte sans autre vérification.

**Capture à insérer** : `[CAPTURE 01 — CONNEXION]`, `[CAPTURE 02 — PREMIER MOT DE PASSE]`

---

# 7. Tableau de bord

## Objectif
Obtenir en un coup d'œil une vision synthétique de l'activité et de l'état du stock.

## Qui peut l'utiliser
Tous les comptes (les sections dont les données ne sont pas accessibles au rôle connecté affichent un tiret « — » plutôt qu'une erreur).

## Accès
Premier écran affiché après connexion (module « Dashboard » dans le menu de gauche).

## Description de l'écran

### Filtre de période
Deux champs de date (« Du » / « Au »), toujours renseignés. Par défaut : du premier jour du mois en cours à aujourd'hui. Un bouton « Actualiser » applique la période choisie.

### Première ligne d'indicateurs (KPI)
| Indicateur | Signification |
|---|---|
| Articles actifs | Nombre d'articles actuellement actifs dans le catalogue |
| Valeur du stock | Valeur totale du stock (quantité × coût moyen pondéré de chaque article) |
| Stock faible | Nombre d'articles dont le stock est au niveau ou en dessous du seuil minimum défini |
| Ruptures | Nombre d'articles dont le stock est à zéro |
| Chiffre d'affaires (période) | Montant total des ventes validées sur la période sélectionnée |

### Deuxième ligne d'indicateurs (KPI)
| Indicateur | Signification |
|---|---|
| Quantité en stock | Quantité totale (toutes unités confondues) actuellement en stock |
| Entrées (période) | Nombre d'entrées de stock validées sur la période |
| Sorties (période) | Nombre de sorties de stock validées sur la période |
| Ventes (période) | Nombre de ventes validées sur la période (à distinguer du chiffre d'affaires, qui est un montant) |
| Inventaires (période) | Nombre d'inventaires validés sur la période |

### Graphiques
Trois graphiques, avec **infobulle au survol de la souris** affichant la valeur exacte :

- **Évolution des ventes** : montant des ventes validées, regroupé par jour, semaine ou mois selon la durée de la période choisie.
- **Répartition des mouvements** : nombre de mouvements de stock par type (entrée, sortie, vente, ajustement, annulation), sous forme de camembert.
- **Valeur du stock par catégorie** : valeur du stock de chaque catégorie de produits.

Si aucune donnée n'existe pour la période, un message clair remplace le graphique (jamais un graphique vide ou un « 0 » trompeur).

### Listes
- **Articles en stock faible** : les articles les plus critiques, triés par sévérité.
- **Activité récente** : les derniers mouvements de stock enregistrés.

### Accès rapides
Des boutons permettent d'accéder directement aux écrans Ventes, Entrées, Sorties, Mouvements et Rapports (uniquement affichés si le compte connecté y a accès).

### Cas particulier du rôle Vendeur
Le rôle Vendeur ne dispose pas de l'accès aux Rapports (`REPORT_VIEW`), mais voit malgré tout les indicateurs et le graphique liés aux ventes (nombre de ventes, chiffre d'affaires, évolution des ventes), via son propre accès à l'écran Ventes (`SALE_VIEW`). Les autres sections (stock, entrées, sorties, inventaires, mouvements, valorisation), elles, restent masquées pour ce rôle.

## Règles métier
- Les montants affichés respectent toujours la devise configurée dans les Paramètres (chapitre 8).
- Le tableau de bord n'affiche jamais que des ventes/entrées/sorties/inventaires **validés** — jamais des documents en brouillon.
- Aucune action effectuée depuis le tableau de bord ne modifie le stock : c'est un écran de consultation uniquement.

**Capture à insérer** : `[CAPTURE 04 — DASHBOARD]`

---

# 8. Paramètres de l'entreprise

## Objectif
Renseigner les informations de votre entreprise, la devise utilisée pour l'affichage des montants, et le logo qui apparaîtra sur les documents (reçus).

## Qui peut l'utiliser
Administrateur uniquement.

## Accès
Menu **Paramètres**.

## Description de l'écran

### Informations de l'entreprise
| Champ | Obligatoire |
|---|---|
| Nom de l'entreprise | Oui |
| Adresse | Non |
| Téléphone | Non |
| Email | Non (doit contenir « @ » si renseigné) |
| Devise | Oui |

Devises actuellement disponibles : **XOF, XAF, EUR, USD**.

### Logo de l'entreprise
Un aperçu du logo actuel, avec deux boutons : **« Choisir un logo… »** et **« Supprimer le logo »**. Formats acceptés : PNG, JPG, JPEG.

> **Important** — Ce logo est celui de **votre entreprise cliente**, destiné aux documents (reçus). Il est totalement distinct du logo StockManager (identité du produit lui-même), qui ne peut pas être remplacé.

## Procédure — Renseigner les informations de l'entreprise

1. Ouvrir le menu Paramètres.
2. Renseigner le nom, l'adresse, le téléphone, l'email de l'entreprise.
3. Choisir la devise dans la liste.
4. Cliquer sur « Enregistrer ».

## Procédure — Ajouter/changer le logo

1. Cliquer sur « Choisir un logo… ».
2. Sélectionner une image (PNG/JPG).
3. Le logo est immédiatement enregistré et prévisualisé.

## Code de récupération administrateur

### Objectif
Permettre à un compte Administrateur de retrouver l'accès à l'application s'il oublie son mot de passe, sans dépendre d'un autre administrateur (voir chapitre 6, procédure de récupération).

### Qui peut l'utiliser
Un compte Administrateur, pour générer **son propre** code uniquement — jamais celui d'un autre compte.

### Procédure

1. Depuis l'écran Paramètres, cliquer sur **« Générer un nouveau code de récupération »**.
2. Confirmer (un code déjà existant, s'il y en a un, est immédiatement invalidé et remplacé).
3. Le nouveau code s'affiche **une seule fois**, dans une fenêtre dédiée — il n'est jamais réaffiché ensuite.

> **Important** — Notez ce code immédiatement et conservez-le en lieu sûr (il n'est stocké par l'application que sous une forme qui ne permet pas de le retrouver). S'il est perdu, il faudra en générer un nouveau en étant déjà connecté.

## Paramètres **non disponibles** dans la version actuelle

Pour éviter toute ambiguïté, les paramètres suivants **n'existent pas** dans la version actuelle de StockManager et ne doivent pas être présentés comme disponibles :

- numérotation des documents configurable (les numéros d'entrées/sorties/ventes/inventaires suivent un format fixe) ;
- seuil de stock global configurable pour toute l'entreprise (le seuil « stock faible » se règle uniquement article par article, voir chapitre 10) ;
- paramètres système additionnels (langue, thème, etc.).

Ces éléments ne doivent pas être annoncés au client comme des fonctionnalités futures garanties.

**Capture à insérer** : `[CAPTURE 05 — PARAMÈTRES]`

---

# 9. Utilisateurs et rôles

## Objectif
Créer des comptes pour les personnes qui utilisent StockManager, et contrôler ce que chacune peut faire.

## Qui peut l'utiliser
Administrateur uniquement (pages Utilisateurs et Rôles).

## Accès
Menus **Utilisateurs** et **Rôles**.

## Les quatre rôles

StockManager propose quatre rôles fixes. Il n'est pas possible d'en créer de nouveaux, ni de renommer ou supprimer les rôles existants — seules leurs permissions peuvent être ajustées (voir plus bas).

| Rôle | Usage typique |
|---|---|
| **Administrateur** | Accès complet à l'application, y compris l'administration (utilisateurs, rôles, paramètres, sauvegardes, audit, licence). |
| **Gestionnaire de stock** | Gestion du catalogue (articles, catégories, fournisseurs) et des mouvements de stock (entrées, sorties, inventaires), consultation des rapports. |
| **Vendeur** | Création et validation des ventes, gestion des clients. |
| **Consultation** | Accès en lecture seule à une partie des données (catalogue, mouvements, rapports, tableau de bord). |

### Matrice fonctionnelle simplifiée

| Fonctionnalité | Administrateur | Gestionnaire de stock | Vendeur | Consultation |
|---|:-:|:-:|:-:|:-:|
| Tableau de bord | ✓ | ✓ | ✓ | ✓ |
| Catalogue — Consulter : Catégories | ✓ | ✓ | — | ✓ |
| Catalogue — Consulter : Fournisseurs | ✓ | ✓ | — | ✓ |
| Catalogue — Consulter : Articles | ✓ | ✓ | ✓ | ✓ |
| Catalogue — Consulter : Motifs de sortie | ✓ | — | — | — |
| Catalogue (créer/modifier) | ✓ | ✓ | — | — |
| Entrées / Sorties de stock | ✓ | ✓ | — | — |
| Annulation d'une entrée/sortie validée | ✓ | — | — | — |
| Inventaires | ✓ | ✓ | — | — |
| Ventes | ✓ | — | ✓ | — |
| Annulation d'une vente validée | ✓ | — | — | — |
| Ventes — Enregistrer un paiement (crédit/paiement partiel) | ✓ | — | ✓ | — |
| Créances clients (consultation) | ✓ | — | ✓ | — |
| Clients | ✓ | ✓ | Création/modification (pas activer/désactiver) | — |
| Mouvements (consultation) | ✓ | ✓ | — | ✓ |
| Rapports (consulter) | ✓ | ✓ | — | ✓ |
| Rapports (exporter) | ✓ | ✓ | — | — |
| Utilisateurs / Rôles | ✓ | — | — | — |
| Paramètres | ✓ | — | — | — |
| Sauvegardes | ✓ | — | — | — |
| Réinitialiser les données métier | ✓ | — | — | — |
| Journal d'audit | ✓ | — | — | — |
| Licence | ✓ | — | — | — |
| Locations (consulter) | ✓ | ✓ | ✓ | ✓ |
| Locations (créer/gérer le cycle de vie, paiements, caution) | ✓ | ✓ | ✓ | — |
| Annuler une location (avant départ uniquement) | ✓ | — | — | — |

> Cette matrice est une **présentation simplifiée**. Le détail complet des permissions (75 permissions réelles) figure en annexe (chapitre 22) — c'est ce détail qui fait foi en cas de doute. Le fonctionnement détaillé du module Locations (réservation, départ, retours partiels/complets, facturation, caution) est couvert au chapitre 13.5.

> **Important** — Les droits d'accès sont vérifiés à deux niveaux : au niveau de l'écran (un bouton non autorisé n'est pas affiché ou est désactivé) **et** au niveau du programme lui-même. Un utilisateur ne peut donc jamais contourner ses droits, même en essayant d'accéder à une fonctionnalité par un autre moyen.

## Procédure — Créer un utilisateur

1. Ouvrir le menu Utilisateurs.
2. Cliquer sur « Ajouter un utilisateur ».
3. Renseigner : nom d'utilisateur, mot de passe, au moins un **rôle** (une case à cocher par rôle disponible — voir « Plusieurs rôles par utilisateur » ci-dessous), et cocher « Compte actif » si le compte doit être immédiatement utilisable.
4. Valider.

**Résultat attendu** : le compte est créé. Son titulaire devra changer ce mot de passe dès sa première connexion.

## Plusieurs rôles par utilisateur

Un utilisateur **peut posséder plusieurs rôles à la fois** (ex. Vendeur et Gestionnaire de stock). Il garde toujours un seul identifiant et un seul mot de passe ; ses permissions effectives sont l'**union** des permissions de tous ses rôles. Chaque utilisateur doit avoir au moins un rôle — impossible d'en enregistrer un sans aucune case cochée.

## Procédure — Modifier les rôles d'un utilisateur

1. Sélectionner l'utilisateur dans la liste.
2. Cliquer sur « Modifier ».
3. Cocher/décocher les rôles souhaités (les rôles déjà attribués sont pré-cochés).
4. Valider.

> Seuls les rôles peuvent être modifiés ici — pas le nom d'utilisateur ni le mot de passe.

## Procédure — Réinitialiser un mot de passe

1. Sélectionner l'utilisateur.
2. Cliquer sur « Réinitialiser le mot de passe ».
3. Confirmer (« Réinitialiser le mot de passe de « [utilisateur] » ? Ce compte devra en choisir un nouveau à sa prochaine connexion. »).
4. Saisir le nouveau mot de passe temporaire.

## Procédure — Activer / désactiver un compte

1. Sélectionner l'utilisateur.
2. Cliquer sur « Activer / désactiver le compte sélectionné ».

> Un compte désactivé n'est jamais supprimé : son historique reste consultable, mais il ne peut plus se connecter.

## Règle particulière — Protection du dernier Administrateur actif

Pour éviter de se retrouver sans aucun administrateur, StockManager empêche systématiquement :

| Tentative | Résultat |
|---|---|
| Désactiver le dernier compte Administrateur actif | Refusé : « Impossible de désactiver le dernier compte Administrateur actif. » |
| Retirer son propre rôle Administrateur | Refusé : « Vous ne pouvez pas retirer votre propre rôle Administrateur. » |
| Retirer le rôle Administrateur du dernier administrateur actif (par un autre utilisateur) | Refusé : « Impossible de retirer le rôle Administrateur du dernier compte Administrateur actif. » |

## Procédure — Modifier les permissions d'un rôle

1. Ouvrir le menu Rôles.
2. Sélectionner un rôle, cliquer sur « Modifier les permissions ».
3. Cocher/décocher les permissions souhaitées (regroupées par thème).
4. Enregistrer.

> Certaines permissions du rôle Administrateur (consultation/modification des rôles et des utilisateurs) sont grisées et ne peuvent jamais être retirées — l'application resterait sinon impossible à administrer.

**Capture à insérer** : `[CAPTURE 06 — UTILISATEURS]`, `[CAPTURE 07 — RÔLES]`

---

# 10. Gestion du catalogue

## 10.1 Catégories

### Objectif
Regrouper les articles par famille (ex. « Boissons », « Épicerie »).

### Qui peut l'utiliser
Administrateur, Gestionnaire de stock (création/modification) ; consultation également ouverte au rôle Consultation.

### Procédure — Créer une catégorie
1. Menu Catégories → « Ajouter ».
2. Saisir le nom.
3. Valider.

### Règle métier
Le nom d'une catégorie doit être **unique**. Une catégorie n'est jamais supprimée : elle peut seulement être désactivée (bouton « Activer / désactiver »), auquel cas elle n'est plus proposée pour un nouvel article mais reste visible dans l'historique.

## 10.2 Fournisseurs

### Champs
Nom (obligatoire), Contact, Téléphone, Email, Adresse, Ville, Pays, Observations.

### Règle métier
Contrairement aux catégories, **le nom d'un fournisseur n'a pas besoin d'être unique** : deux fournisseurs distincts peuvent légitimement porter le même nom commercial.

### Procédure
Même principe que les catégories (Ajouter / Modifier / Activer-désactiver).

## 10.3 Motifs de sortie

### Objectif
Qualifier la raison d'une sortie de stock qui n'est pas une vente (ex. « Casse », « Don », « Usage interne »).

### Qui peut l'utiliser
**Administrateur uniquement** — y compris pour la simple consultation.

### Champs
Libellé (obligatoire), Description.

### Règle métier
Le libellé doit être unique (espaces et majuscules/minuscules ignorés dans la comparaison). Jamais de suppression physique, uniquement une désactivation.

## 10.4 Articles

### Objectif
Gérer la fiche de chaque produit géré en stock.

### Qui peut l'utiliser
Consultation : tous les rôles. Création/modification : Administrateur et Gestionnaire de stock.

### Champs disponibles

| Champ | Obligatoire | Remarque |
|---|:-:|---|
| Référence | Oui | Doit être unique |
| Désignation | Oui | |
| Catégorie | Oui | |
| Fournisseur principal | Non | |
| Unité | Oui | |
| Prix d'achat | Oui | |
| Prix de vente | Oui | |
| Stock minimum | Oui | Seuil déclenchant l'alerte « stock faible » |
| Stock maximum | Non | |
| Stock initial | Uniquement à la création | Quantité de départ |
| Emplacement | Non | |
| Code-barres | Non | Doit être unique parmi les articles **actifs** (un article désactivé peut conserver son code sans bloquer un nouvel article actif qui le reprendrait) |
| Description | Non | |

### Le CMUP (Coût Moyen Unitaire Pondéré)

Le CMUP est **affiché** sur la fiche article (en modification et dans le détail) mais **n'est jamais saisi manuellement**. Il est calculé automatiquement par le système à chaque entrée de stock validée, selon la formule :

> nouveau CMUP = ((stock avant × CMUP avant) + (quantité entrée × prix d'achat)) ÷ (stock avant + quantité entrée)

Les sorties, ventes et annulations ne modifient jamais le CMUP.

### Statut actif/inactif

Un article désactivé :
- reste visible dans l'historique (mouvements, ventes, rapports passés) ;
- **ne peut plus être sélectionné** pour une nouvelle entrée, sortie, vente ou inventaire.

Aucun article n'est jamais supprimé physiquement.

### Procédure — Créer un article

1. Menu Articles → « Ajouter ».
2. Renseigner référence, désignation, catégorie, unité, prix d'achat, prix de vente, stock minimum.
3. Renseigner éventuellement le stock initial, le fournisseur, le code-barres, l'emplacement, la description.
4. Enregistrer.

### Recherche et scan par code-barres

Le champ de recherche libre du catalogue (menu Articles) trouve également un article par son code-barres, en plus de la référence, de la désignation et du nom de catégorie.

Dans les écrans **Ventes** (chapitre 12) et **Inventaires** (chapitre 13), un champ dédié « Scanner / code-barres » permet d'identifier rapidement un article :

- placez le curseur dans ce champ ;
- scannez le code-barres avec un lecteur USB, ou saisissez-le au clavier ;
- le lecteur de code-barres se comporte comme un clavier (« keyboard wedge ») : il tape le code puis envoie automatiquement la touche **Entrée** — aucun pilote ni logiciel supplémentaire n'est nécessaire ;
- si un article actif correspond, il est ajouté directement à la vente (quantité 1, prix de vente actuel) ou pré-sélectionné dans le formulaire de ligne d'inventaire ;
- si aucun article actif ne correspond, un message clair l'indique et **rien n'est ajouté** — ni ligne invalide, ni impact sur le stock.

> Un article désactivé n'est jamais retrouvé par le scan, même si son code-barres reste affiché dans son historique.

**Capture à insérer** : `[CAPTURE 08 — CATÉGORIES]`, `[CAPTURE 09 — ARTICLES]`, `[CAPTURE 10 — FOURNISSEURS]`

---

# 11. Gestion du stock

## Principe général

Toute opération de stock (entrée, sortie, vente, inventaire) suit le même cycle :

**BROUILLON → VALIDÉE → (éventuellement) ANNULÉE**

- Un document en **brouillon ne modifie jamais le stock**. Il peut être librement modifié ou supprimé.
- Seule la **validation** modifie réellement le stock : elle génère un ou plusieurs **mouvements de stock**, journal permanent et non modifiable de toute variation de stock.
- **Le stock ne peut jamais devenir négatif.** Si une opération ferait passer le stock en dessous de zéro, elle est refusée avec le message : *« Cette opération est refusée : le stock de « [référence] » deviendrait négatif ([valeur]). »*
- L'**annulation** d'un document déjà validé (lorsqu'elle est autorisée) crée un mouvement inverse qui restaure le stock — elle ne supprime jamais le document d'origine.

## 11.1 Entrées

### Objectif
Enregistrer une réception de marchandise, généralement en provenance d'un fournisseur.

### Qui peut l'utiliser
Administrateur, Gestionnaire de stock.

### Procédure — Créer et valider une entrée

1. Menu Entrées → nouvelle entrée.
2. Choisir le fournisseur, la date, une référence de document (bon de livraison, facture...) et un commentaire si utile.
3. Ajouter une ou plusieurs lignes (article, quantité, prix unitaire).
4. Enregistrer en brouillon.
5. Une fois vérifiée, cliquer sur « Valider ». Confirmation demandée : *« Voulez-vous vraiment valider cette entrée ? Cette action met à jour le stock et n'est pas réversible autrement que par annulation. »*

### Résultat attendu
Le stock de chaque article concerné augmente, et son CMUP est recalculé.

### Annulation
Bouton « Annuler » (Administrateur uniquement), disponible uniquement pour une entrée déjà validée. Une boîte de dialogue demande de saisir un **motif d'annulation obligatoire** (au moins 5 caractères, ni vide ni composé uniquement d'espaces) : sans motif valide, l'annulation est refusée. Le stock est restauré à son niveau précédent via un mouvement inverse, et le motif saisi reste consultable définitivement dans le détail de l'entrée.

## 11.2 Sorties

### Objectif
Enregistrer une sortie de stock qui n'est **pas** une vente (casse, perte, usage interne, don...).

### Qui peut l'utiliser
Administrateur, Gestionnaire de stock.

### Procédure

1. Menu Sorties → nouvelle sortie.
2. Choisir un **motif** (obligatoire), la date, éventuellement un bénéficiaire/service et une référence.
3. Ajouter les lignes (article, quantité) — le coût affiché à titre indicatif est le CMUP courant de l'article, non modifiable.
4. Enregistrer en brouillon, puis valider.

### Annulation
Identique aux entrées (Administrateur uniquement, uniquement après validation, motif d'annulation obligatoire — voir 11.1).

## 11.3 Mouvements

### Objectif
Consulter l'historique complet et non modifiable de toutes les variations de stock.

### Description
Il s'agit d'un **journal de consultation uniquement** : aucune création, modification ou suppression n'est possible depuis cet écran. Filtres disponibles : recherche libre, période (case à cocher + date, permettant de laisser une borne ouverte), type de mouvement.

**Capture à insérer** : `[CAPTURE 11 — ENTRÉE]`, `[CAPTURE 12 — SORTIE]`, `[CAPTURE 16 — MOUVEMENTS]`

---

# 12. Ventes et clients

## Vente ≠ Sortie

Il est important de bien distinguer ces deux opérations, qui ont pourtant toutes deux pour effet de diminuer le stock :

| | Vente | Sortie |
|---|---|---|
| Nature | Transaction commerciale | Sortie de stock sans facturation |
| Prix | Prix de vente, librement ajustable | Pas de prix — coût = CMUP courant |
| Client | Optionnel | Sans objet |
| Motif | Sans objet | Obligatoire |
| Mouvement généré | VENTE | SORTIE |

## 12.1 Clients

### Champs
Nom (obligatoire), Téléphone, Email, Adresse, Observations.

### Procédure — Créer/modifier un client
Menu Clients → « Ajouter » ou sélectionner un client existant → « Modifier ».

### Activation / désactivation
Un client désactivé :
- reste sélectionnable dans les filtres de l'historique des ventes (son historique passé reste consultable, libellé « Nom (inactif) ») ;
- **n'est plus proposé** pour une nouvelle vente.

## 12.2 Création d'une vente

### Trois cas possibles
1. **Vente comptant** — sans client associé.
2. **Client existant** — sélectionné dans la liste.
3. **Nouveau client créé à la volée** — bouton « Nouveau client… » directement depuis le formulaire de vente, sans quitter la saisie en cours.

### Procédure

1. Menu Ventes → nouvelle vente.
2. Choisir la date.
3. Choisir un client existant, laisser vide (vente comptant), ou créer un nouveau client via « Nouveau client… ».
4. Ajouter les lignes de vente : soit manuellement (article, quantité, prix unitaire — pré-rempli avec le prix catalogue, modifiable), soit par **scan d'un code-barres** (voir chapitre 10.4) — moyen rapide et complémentaire à la sélection manuelle, jamais un remplacement obligatoire.
5. Enregistrer en brouillon.

### Calcul du total
Le total de la vente est la somme des lignes (quantité × prix unitaire saisi). Le prix effectivement facturé (historisé sur la ligne) sert toujours de référence, même si le prix catalogue de l'article change ensuite.

## 12.3 Validation d'une vente

Bouton « Valider » (visible uniquement pour une vente en brouillon). La validation :
- diminue le stock des articles vendus ;
- génère un mouvement de type VENTE (dont le coût de valorisation interne est le CMUP courant — distinct du prix facturé au client) ;
- rend la vente définitive (elle ne peut plus être modifiée, seulement annulée) ;
- fixe le **mode de règlement** initial : comptant (paiement du montant total au moment même de la validation) ou à crédit (aucun paiement, ou un acompte partiel) — voir 12.6 pour le détail du suivi des paiements.

> Un paiement ne peut jamais être enregistré sur une vente en brouillon (dont le total peut encore changer) : c'est pourquoi le mode de règlement se décide au moment de la validation, jamais avant.

## 12.4 Annulation

Bouton « Annuler » (Administrateur uniquement), uniquement pour une vente déjà validée. Comme pour les entrées et sorties (11.1), une boîte de dialogue demande un **motif d'annulation obligatoire** (au moins 5 caractères) avant de confirmer. Le stock vendu est restauré, et le motif reste consultable définitivement dans le détail de la vente.

> Une vente en brouillon, elle, peut être **supprimée directement** — c'est le seul type de document de l'application autorisant une suppression physique, et uniquement tant qu'il n'a jamais été validé.

## 12.5 Reçus

### Objectif
Fournir un justificatif imprimable au client, pour une vente déjà validée.

### Formats disponibles
- **PDF au format A4**
- **Ticket thermique au format 80 mm**

(Le format 58 mm n'est pas disponible.)

### Impression
Trois actions possibles depuis le détail d'une vente validée :
- **Imprimer le reçu** (ouvre la sélection d'imprimante Windows) ;
- **Exporter en PDF (A4)** ;
- **Exporter en PDF (Ticket 80 mm)**.

### Contenu du reçu
Informations de l'entreprise (nom, coordonnées, logo — tels que renseignés dans les Paramètres), informations du client si renseignées, lignes de la vente, total, date/heure, et — depuis la prise en charge des ventes à crédit — le **montant payé**, le **reste à payer** et le **statut de paiement**, affichés systématiquement (y compris pour une vente comptant, où le reste à payer affiché est alors 0).

> Il n'existe pas, dans la version actuelle, d'archivage automatique des reçus PDF générés : chaque export doit être enregistré manuellement à l'endroit choisi par l'utilisateur.

**Capture à insérer** : `[CAPTURE 13 — VENTE]`, `[CAPTURE 14 — CLIENT]`

## 12.6 Ventes à crédit, paiements partiels et créances

### Objectif
Permettre une vente sans exiger le paiement intégral immédiat, suivre les paiements reçus au fil du temps, et consulter les sommes restant dues par client.

### Qui peut l'utiliser
Enregistrer un paiement : Administrateur, Vendeur. Consulter (historique des paiements, créances) : Administrateur, Vendeur (mêmes droits que la consultation des ventes).

### Statut de paiement d'une vente

Chaque vente validée porte un statut de paiement, recalculé automatiquement à chaque paiement enregistré :

| Statut | Condition |
|---|---|
| **Non payée** | Aucun paiement enregistré |
| **Partiellement payée** | Au moins un paiement enregistré, reste à payer strictement positif |
| **Payée** | Reste à payer = 0 (y compris une vente comptant, payée intégralement dès la validation) |

Le **reste à payer** (total de la vente moins la somme des paiements) n'est jamais négatif.

### Procédure — Enregistrer un paiement ultérieur

1. Ouvrir le détail d'une vente validée dont le reste à payer est supérieur à 0.
2. Cliquer sur « Enregistrer un paiement ».
3. Le total de la vente, le montant déjà payé et le reste à payer sont rappelés avant la saisie.
4. Saisir le montant du paiement (et, en option, le mode de paiement, une référence, un commentaire).
5. Valider.

**Règles** :
- Un paiement dont le montant dépasse le reste à payer est **refusé**, rien n'est enregistré.
- Une vente déjà intégralement payée refuse tout nouveau paiement.
- Un paiement ne modifie **jamais** le stock : c'est une opération strictement financière, distincte de la validation de la vente (qui a déjà diminué le stock).
- Chaque paiement est conservé individuellement dans un historique — jamais fusionné dans un simple total : l'historique complet d'une vente (« Paiement 1 — 20/09, Paiement 2 — 25/09... ») reste toujours consultable, y compris après une éventuelle annulation de la vente.

### Reçu de paiement

Depuis l'historique des paiements d'une vente, chaque paiement peut faire l'objet d'un export PDF dédié (« Reçu du paiement sélectionné ») indiquant : référence de la vente, client, montant du paiement, total payé après ce paiement, reste à payer, date, utilisateur ayant enregistré le paiement. Ce document est distinct du reçu de vente (12.5).

### Annulation d'une vente déjà payée

> **Point important** — L'annulation d'une vente (12.4) reste possible même si des paiements ont déjà été enregistrés. Les paiements déjà enregistrés ne sont **jamais** modifiés, supprimés, ni automatiquement remboursés : ils restent visibles comme trace historique de ce qui a réellement été perçu. **Aucun remboursement n'est généré automatiquement** — un remboursement éventuel reste un processus à gérer manuellement en dehors de l'application.

### Écran Créances clients

Menu **Créances** : liste des ventes validées avec leur montant total, montant payé, reste à payer et statut de paiement. Filtres disponibles : recherche par numéro de vente, client, statut de paiement (« En cours » par défaut, « Toutes », ou un statut précis : Non payée / Partiellement payée / Payée), période. En sélectionnant un client dans le filtre, un résumé s'affiche : total facturé, total payé et reste à payer pour ce client (sur ses ventes validées — une vente annulée ne compte plus comme une créance active).

> **Filtre par défaut** — À l'ouverture de l'écran, seules les ventes **non intégralement payées** (non payées + partiellement payées) sont affichées : c'est un écran de créances, pas un historique complet des ventes. Choisir « Toutes (non annulées) » ou « Payée » dans le filtre de statut pour voir également les ventes déjà réglées.

> Cet écran n'est pas un tableau de bord financier complet : il présente uniquement les ventes et leur état de paiement.

**Capture à insérer** : `[CAPTURE 22 — CRÉANCES]`

---

# 13. Inventaires

## Objectif
Comparer le stock réellement compté physiquement au stock théorique enregistré par l'application, et ajuster le stock en conséquence.

## Qui peut l'utiliser
Administrateur, Gestionnaire de stock.

## Procédure

1. Menu Inventaires → nouvel inventaire.
2. Choisir la date.
3. Ajouter une ligne par article à compter : sélectionner l'article (parmi les articles actifs) — manuellement, ou en le retrouvant par **scan de son code-barres** (voir chapitre 10.4), qui pré-sélectionne directement l'article dans le formulaire de ligne —, puis saisir le **stock compté**.
4. Le **stock théorique** de chaque ligne est capturé automatiquement au moment de l'ajout ; l'**écart** (compté − théorique) est calculé et affiché.
5. Une fois toutes les lignes saisies, cliquer sur « Valider ». Une confirmation détaille, ligne par ligne, le théorique/compté/écart, et précise que l'opération est définitive.

## Résultat attendu
Pour chaque écart non nul, un mouvement d'ajustement est généré automatiquement, portant le stock réel de chaque article à la valeur comptée.

> **Point important** — **Une fois un inventaire validé, il ne peut pas être annulé** dans cette version de StockManager. Vérifiez soigneusement les quantités comptées avant de valider. Une correction ultérieure nécessitera un nouvel inventaire ou une autre opération de stock.

**Capture à insérer** : `[CAPTURE 15 — INVENTAIRE]`

---

# 13.5 Location d'articles (module Locations)

> Ce chapitre est inséré avec un numéro décimal (13.5) plutôt qu'en renumérotant les chapitres suivants, afin de ne pas invalider les renvois « voir chapitre N » déjà présents ailleurs dans ce manuel.

## Objectif et différence avec une vente

Le module Locations permet de louer temporairement des articles à un client : contrairement à une **vente**, qui transfère définitivement la propriété d'un article contre un prix, une **location** ne fait que sortir physiquement un article du stock pour une durée indéterminée à l'avance, avec une obligation de restitution (totale ou partielle) et une facturation calculée **au moment du retour**, en fonction du nombre de jours écoulés.

## Mode de gestion d'un article : Vente ou Location

Chaque article porte un **mode de gestion** exclusif : **Vente** (valeur par défaut à la création) ou **Location**. Les deux modes sont mutuellement exclusifs :

- un article en mode **Vente** ne peut jamais figurer sur une location (refusé par le formulaire, qui ne propose même pas ces articles) ;
- un article en mode **Location** ne peut jamais être vendu — message exact si on tente malgré tout de l'ajouter à une vente : *« L'article « [référence] » est en mode Location : il ne peut pas être vendu. »*

### Conditions pour qu'un article puisse être loué

- l'article doit être **actif** ;
- son mode de gestion doit être **Location** ;
- un **tarif de location journalier** doit être disponible, soit déjà renseigné sur la fiche article (champ « Tarif de location (par jour) », sans objet en mode Vente), soit saisi manuellement au moment de l'ajout de la ligne de location — l'un des deux est obligatoire, sinon la ligne est refusée.

### Changer le mode de gestion d'un article

Depuis le module Articles, bouton **« Mode de gestion… »** (permission `ARTICLE_UPDATE`) : ouvre un dialogue dédié indiquant le mode actuel et proposant de basculer vers l'autre mode, avec un bouton **« Confirmer la bascule »**. Ce changement n'est **jamais** un simple champ du formulaire d'édition habituel : chaque bascule (dans les deux sens) est conservée définitivement dans un historique dédié, consultable par programme mais sans écran de consultation dédié dans cette version.

**Restriction** : il est impossible de rebasculer un article de **Location** vers **Vente** tant qu'il reste concerné par une ligne de location **physiquement en cours** (quantité « en location » non nulle sur au moins une location non retournée). À l'inverse, une quantité simplement **réservée** (location en brouillon ou confirmée, pas encore partie) n'empêche jamais la bascule — seule une sortie physique du stock la bloque.

## Permissions du module Locations

| Permission | Administrateur | Gestionnaire de stock | Vendeur | Consultation |
|---|:-:|:-:|:-:|:-:|
| Consulter les locations | ✓ | ✓ | ✓ | ✓ |
| Créer une location | ✓ | ✓ | ✓ | — |
| Modifier une location en brouillon | ✓ | ✓ | ✓ | — |
| Confirmer une location | ✓ | ✓ | ✓ | — |
| Enregistrer le départ d'une location | ✓ | ✓ | ✓ | — |
| Enregistrer un retour (total ou partiel) | ✓ | ✓ | ✓ | — |
| Définir et restituer la caution | ✓ | ✓ | ✓ | — |
| Enregistrer un paiement sur une location | ✓ | ✓ | ✓ | — |
| Annuler une location (avant départ uniquement) | ✓ | — | — | — |

Le rôle Vendeur dispose donc des mêmes droits opérationnels que le Gestionnaire de stock sur ce module (hormis l'annulation, réservée à l'Administrateur) — cohérent avec son rôle déjà existant sur les Ventes.

## Cycle de vie d'une location

### Statuts

Brouillon → Confirmée → En cours → Retournée, ou Brouillon/Confirmée → Annulée. **Une location ne peut plus jamais être annulée après son départ** : une fois le stock physiquement sorti, seule une suite de retours permet de la clore.

### 1. Création (Brouillon)

Menu **Locations** → bouton **« Nouvelle location »**.

- Champs : **Date** (obligatoire, jamais dans le futur), **Client** (obligatoire — une location, à la différence d'une vente, n'a pas d'équivalent « comptant/sans client » : un client identifié est toujours exigé), Commentaire (facultatif).
- Lignes : bouton **« Ajouter une ligne »** ouvre un formulaire dédié — **Article** (uniquement les articles actifs en mode Location), **Quantité** (strictement positive), **Tarif journalier** (pré-rempli depuis le tarif catalogue de l'article choisi, librement modifiable). Bouton **« Supprimer la ligne »** pour retirer une ligne sélectionnée.
- Bouton **« Enregistrer en brouillon »**.

**Aucun effet sur le stock à ce stade** : la quantité demandée est seulement enregistrée comme « réservée », une information de confort, jamais décomptée d'`Article.stock_actuel` (exactement comme une vente en brouillon). Seule une location en **Brouillon** peut être modifiée (bouton « Modifier ») ou **supprimée physiquement** (bouton « Supprimer ») — ce sont les deux seules actions disponibles directement depuis la liste ; tout le reste du cycle de vie se pilote depuis l'écran de détail (bouton « Détails »).

### 2. Confirmation

Depuis le détail de la location, bouton **« Confirmer »** (actif uniquement en Brouillon). Revérifie que chaque article de la location est toujours actif et toujours en mode Location (sa situation peut avoir changé depuis la création du brouillon) et qu'il y a au moins une ligne. **N'a toujours aucun effet sur le stock.** Passe au statut **Confirmée**.

### 3. Départ

Bouton **« Enregistrer le départ »** (actif uniquement en Confirmée) ouvre un dialogue demandant la **Date de départ** (jamais dans le futur, jamais antérieure à la date de la location), avec un bouton **« Confirmer le départ »**.

C'est le **seul moment** où le stock est physiquement décrémenté : pour chaque ligne, la quantité réservée devient « en location » et un mouvement de stock est généré (consultable comme n'importe quel mouvement — voir la mise en garde ci-dessous sur son libellé). La date de départ, une fois enregistrée, n'est plus jamais modifiée : elle sert de point de départ au calcul des frais à chaque retour.

### 4. Consultation du détail et de l'état

Bouton **« Détails »**, disponible quel que soit le statut. Affiche : numéro, date, client, créée par, statut, date de départ (si déjà partie), motif d'annulation (si annulée), commentaire, puis trois zones :
- un tableau des **lignes** (article, quantité prévue, réservée, en location, immobilisée, tarif/jour, montant déjà facturé) ;
- un historique des **retours** (date, ligne concernée, quantité en bon état, quantité immobilisée, montant facturé, utilisateur) ;
- les montants **Total facturé / Payé / Reste à payer**, suivis d'un historique des **paiements** (date, montant, mode, référence, utilisateur) ;
- la **caution** (montant, restitué/retenu).

### 5. Retours (partiels puis complet)

Bouton **« Enregistrer un retour »** (actif uniquement en Statut En cours). Ouvre un formulaire listant uniquement les lignes dont la quantité « en location » est encore positive — si aucune ligne n'est éligible, le message *« Aucune ligne n'est encore en location. »* s'affiche à la place.

Champs : **Ligne** (affiche la quantité encore en location, en lecture seule), **Date de retour** (jamais dans le futur, jamais antérieure à la date de départ), **Quantité en bon état**, **Quantité immobilisée (non remise en stock)**, Commentaire. Au moins l'une des deux quantités doit être strictement positive, et leur somme ne peut pas dépasser la quantité encore en location de la ligne choisie.

Chaque retour est un **événement indépendant et historisé** (jamais modifié ni supprimé ensuite) :
- la quantité remise en **bon état** régénère du stock disponible (mouvement de stock, voir plus bas) ;
- la quantité **immobilisée** ne redevient jamais disponible (voir « Effets sur le stock et les articles » ci-dessous) ;
- un **retour partiel peut être suivi d'autres retours** sur la même ligne, jusqu'à épuisement complet de la quantité partie.

**Pourquoi une location reste « En cours » après un retour partiel** : une location peut porter sur plusieurs lignes (plusieurs articles différents). Le statut global ne passe à **Retournée** que lorsque **toutes** les lignes de la location ont une quantité « en location » revenue à zéro — il n'existe pas de statut intermédiaire par ligne, seules les quantités affichées par ligne permettent de suivre l'avancement.

### 6. Annulation

Bouton **« Annuler la location »** (actif uniquement en Brouillon ou Confirmée — jamais après le départ). Comme pour les entrées, sorties et ventes, une boîte de dialogue demande un **motif d'annulation obligatoire** (au moins 5 caractères). Aucun mouvement de stock n'est généré par l'annulation elle-même : rien n'a encore été sorti du stock avant le départ.

### 7. Facturation, encaissement et historiques

Le montant facturé n'existe qu'à partir du **premier retour enregistré** (voir « Calcul des frais » ci-dessous) — avant cela, le total facturé affiché est 0.

Bouton **« Paiement… »** (actif dès le statut En cours, et aussi en Retournée). Affiche Total facturé / Déjà payé / Reste à payer, puis demande **Montant du paiement** (obligatoire), Mode de paiement (champ libre, suggestions « Espèces, Mobile Money, Virement… »), Référence, Commentaire. **Tout paiement qui dépasserait le montant déjà facturé est refusé** — concrètement, avant le premier retour, le montant facturé est encore nul et aucun paiement, même minime, ne peut donc être enregistré tant qu'aucun retour n'a eu lieu. Chaque paiement est conservé individuellement dans l'historique des paiements, jamais fusionné — et ce journal est **totalement indépendant** du journal des paiements des ventes (`Paiement`) : encaisser une location n'a aucun effet sur les créances/paiements d'une vente, et réciproquement.

## Calcul des frais

### Règle

- Le **tarif journalier** d'une ligne est enregistré dès la création de celle-ci (pré-rempli depuis le tarif catalogue de l'article, mais librement modifiable à la saisie). Il reste modifiable tant que la location est en **Brouillon** (en la rouvrant via « Modifier »). **À partir de la confirmation de la location, ce tarif est figé** : aucune étape suivante du cycle de vie (départ, retour, annulation, paiement) ne le modifie plus.
- **Une modification ultérieure du tarif de location de l'article au catalogue ne change jamais le tarif déjà retenu sur une ligne existante** — c'est la valeur historisée sur la ligne qui compte, jamais le tarif catalogue courant.
- À **chaque retour**, le montant dû pour cet événement est calculé **une seule fois** et conservé définitivement (jamais recalculé ensuite) selon la formule :

> montant du retour = tarif journalier de la ligne × nombre de jours entre la date de départ et la date de ce retour (**minimum 1 jour**) × quantité traitée lors de cet événement (bon état **+** immobilisée confondues — les deux dues également, un article immobilisé a quand même été loué pendant sa durée de sortie)

- Les frais des **retours successifs s'accumulent** : le montant total facturé d'une ligne est la somme des montants de tous ses événements de retour ; le montant total facturé d'une location est la somme de celui de toutes ses lignes.

### Exemple numérique (illustratif, conforme à la règle ci-dessus)

Article loué à 500 (unité monétaire configurée) par jour, quantité louée : 5, départ le 1er janvier.

| Événement | Date | Jours écoulés depuis le départ | Quantité traitée | Montant de l'événement |
|---|---|:-:|:-:|---:|
| Retour partiel n°1 | 2 janvier | max(1, 1) = 1 | 2 (bon état) | 500 × 1 × 2 = **1 000** |
| Retour final n°2 | 5 janvier | max(4, 1) = 4 | 3 (bon état) | 500 × 4 × 3 = **6 000** |

**Total facturé pour cette location : 1 000 + 6 000 = 7 000.** Le retour n°1 ne clôt pas la location (il reste 3 unités en location) ; le retour n°2 ramène la quantité en location à 0 sur cette ligne, ce qui fait passer la location à **Retournée**.

### Limites de cette méthode de calcul

- La durée facturée se compte en **jours entiers uniquement** — aucune proratisation à l'heure : un retour le jour même du départ facture quand même un jour plein (minimum 1 jour).
- **Aucune distinction entre jours calendaires et jours ouvrés** : la méthode compte des jours calendaires simples, sans paramètre pour exclure les week-ends ou jours fériés, et ce choix n'est pas configurable.
- Chaque article d'une même ligne loué à des quantités différentes partage le même tarif journalier unique saisi sur cette ligne — il n'existe pas de tarif dégressif selon la quantité ou la durée.

## Cautions

La caution est **entièrement distincte** des frais de location (montant facturé via les retours) et des paiements de location (journal `LocationPaiement`) — trois montants suivis séparément sur une même location, sans aucun lien de calcul automatique entre eux.

### Versement et modification du montant

Bouton **« Caution… »** dans le détail de la location (disponible quel que soit le statut, sous réserve de la permission). Avant le départ (Brouillon ou Confirmée), le champ proposé est **« Nouveau montant de la caution »** : il remplace entièrement le montant actuel (ce n'est jamais un calcul, seulement une saisie manuelle), et ne peut pas être réduit en dessous de ce qui a déjà été restitué.

### Restitution ou retenue

Une fois le départ effectué (En cours ou Retournée) — et aussi après une annulation —, le même bouton propose à la place **« Montant à restituer/retenir »** : chaque saisie s'ajoute au cumul déjà enregistré (`Restituée/retenue`, affiché dans le détail), **jamais une soustraction ni un remboursement automatique**. Rien dans l'application ne calcule ce qu'il « faudrait » restituer à partir des frais ou de l'état des articles retournés : c'est une décision et une saisie entièrement manuelles de l'utilisateur.

### Contrôle

Toute restitution/retenue qui ferait dépasser le montant total de la caution versée est refusée.

### Limite de l'historique

Le détail d'une location n'affiche que **deux totaux cumulés** (montant de la caution, et restitué/retenu) — contrairement aux retours et aux paiements, il n'existe **pas** de tableau listant chaque restitution/retenue individuelle avec sa date et son utilisateur.

## Effets sur le stock et les articles

| Étape | Effet sur le stock | Mouvement généré |
|---|---|---|
| Départ | `stock_actuel` diminue de la quantité réservée de chaque ligne | Un mouvement par ligne (quantité négative) |
| Retour — quantité en bon état | `stock_actuel` augmente de cette quantité | Un mouvement (quantité positive) |
| Retour — quantité immobilisée | **Aucun effet** : ne revient jamais en stock disponible | Aucun mouvement |

Ni l'un ni l'autre de ces deux mouvements ne recalcule le CMUP de l'article (seule une Entrée de stock le recalcule).

> **À noter sur leur consultation dans l'écran Mouvements** — Ces deux mouvements sont bien consultables comme tout autre mouvement (écran Mouvements, et filtre « Type de mouvement » des Rapports), mais ils s'affichent sous leur **libellé technique brut** (« LOCATION_SORTIE » / « LOCATION_RETOUR »), à la différence des types Entrée/Sortie/Vente/Ajustement/Annulation qui bénéficient d'un libellé traduit en français dans l'écran Mouvements. Ce n'est pas un défaut documenté comme corrigé : c'est le libellé réellement affiché dans la version actuelle.

### Immobilisation : pas de remise en état ni de mise au rebut

Une quantité marquée « immobilisée » lors d'un retour ne redevient **jamais** disponible dans cette version : il n'existe **aucun écran ni aucune action** permettant de la remettre en stock vendable/louable, ni de la sortir formellement par une mise au rebut. C'est une limitation connue et acceptée de cette version, pas un oubli d'affichage.

### Exclusivité Vente/Location (rappel)

Voir « Mode de gestion d'un article » ci-dessus : un article en mode Location ne peut jamais être vendu, et toute bascule de mode est historisée de façon permanente et consultable par un changement jamais effectué en simple modification de fiche.

## Statuts, erreurs et contrôles

### Transitions autorisées

Brouillon → Confirmée → En cours → Retournée (automatique, jamais déclenchée manuellement) ; Brouillon → Annulée ; Confirmée → Annulée. Toute autre tentative de transition est refusée (par exemple : confirmer une location déjà confirmée, faire partir une location encore en brouillon, annuler une location déjà partie).

### Contrôles de quantité et de disponibilité réellement appliqués

- Toute quantité saisie doit être strictement positive (quantité de ligne, quantité de paiement, montant de caution) ou au moins non négative selon le champ (quantités d'un retour) ; un retour doit porter sur une quantité totale strictement positive.
- Un retour ne peut jamais dépasser la quantité encore en location de la ligne concernée.
- Les dates de location, de départ et de retour ne peuvent jamais être dans le futur ; la date de départ ne peut pas précéder la date de la location ; la date d'un retour ne peut pas précéder la date de départ.
- Un article doit être actif pour être ajouté à une ligne, et sa situation (actif + toujours en mode Location) est revérifiée à la confirmation ; au départ, seul son caractère actif est revérifié (pas son mode de gestion).
- Un client doit être actif pour être sélectionné.

### Contrôle de concurrence (mécanisme interne, pas une procédure utilisateur)

Lorsque deux retours sont enregistrés en même temps sur deux lignes différentes d'une même location, la mise à jour des quantités et le passage automatique au statut Retournée sont chacun calculés par une instruction unique évaluée directement par la base de données au moment de l'écriture, et non à partir d'une valeur déjà chargée en mémoire — ceci afin qu'aucune mise à jour concurrente ne soit perdue et que le passage à « Retournée » ne soit jamais manqué. C'est un mécanisme de fiabilité interne : il n'implique aucune action ni aucun écran supplémentaire côté utilisateur.

### Contrôles d'intégrité

La base de données garantit en plus, au niveau du schéma : qu'une caution restituée/retenue ne peut jamais dépasser la caution versée ni être négative ; que les quantités d'une ligne (prévue, réservée, en location, immobilisée) et le tarif journalier ne sont jamais négatifs (la quantité prévue devant être strictement positive) ; qu'un événement de retour porte toujours sur une quantité totale strictement positive et un montant facturé non négatif.

---

# 14. Rapports

## Objectif
Obtenir des états détaillés et exportables sur le stock et l'activité.

## Qui peut l'utiliser
Consultation : Administrateur, Gestionnaire de stock, Consultation. Export : Administrateur, Gestionnaire de stock uniquement.

## Accès
Menu Rapports — un menu déroulant permet de choisir le rapport souhaité ; les filtres affichés changent automatiquement selon le rapport choisi.

## Les 9 rapports disponibles

| Rapport | Objectif | Filtres disponibles | Période | Export |
|---|---|---|---|---|
| État du stock | Vue complète du catalogue avec stock, CMUP et valeur | Recherche, Catégorie, Inclure inactifs | Non | CSV, Excel |
| Stock faible | Articles au niveau ou en dessous du seuil minimum | Recherche, Catégorie | Non | CSV, Excel |
| Ruptures | Articles à stock zéro | Recherche, Catégorie | Non | CSV, Excel |
| Mouvements | Historique des mouvements de stock | Article, Type de mouvement | Oui | CSV, Excel |
| Entrées | Historique des entrées | Statut | Oui | CSV, Excel |
| Sorties | Historique des sorties | Motif, Statut | Oui | CSV, Excel |
| Ventes | Historique des ventes | Statut | Oui | CSV, Excel |
| Inventaires | Résumé par inventaire (écarts, quantité ajustée) | Statut | Oui | CSV, Excel |
| Valorisation | Valeur du stock (stock × CMUP) et valeur totale | Recherche, Catégorie, Inclure inactifs | Non | CSV, Excel |

> Le rapport Inventaires présente un **résumé par inventaire** (nombre de lignes, écarts positifs/négatifs, quantité totale ajustée) — pas le détail ligne à ligne, qui reste consultable dans le détail de chaque inventaire.

## Export

- **Deux formats sont disponibles** : CSV et **Excel (.xlsx)**. Il n'existe pas d'export PDF pour les rapports.
- Boutons « Exporter CSV » et « Exporter Excel ».
- Format CSV : séparateur `;`, encodage compatible Excel (BOM UTF-8) — pensé pour une ouverture directe correcte dans Excel en français.
- Format Excel : fichier `.xlsx` directement exploitable (colonnes typées — montants et quantités en valeurs numériques, pas en texte), même contenu que l'export CSV du même rapport.
- Si le rapport ne contient aucune donnée, l'export (CSV ou Excel) est bloqué avec le message : « Aucune donnée à exporter. »

**Capture à insérer** : `[CAPTURE 17 — RAPPORTS]`

---

# 15. Sauvegardes, restauration et réinitialisation des données métier

## Objectif
Protéger les données de l'entreprise contre une perte (panne, erreur, incident).

## Qui peut l'utiliser
Administrateur uniquement.

## Accès
Menu Sauvegardes.

## Sauvegarde manuelle

Bouton **« Sauvegarder maintenant »** : crée immédiatement une copie de sécurité de la base de données, dans le dossier de destination configuré.

## Sauvegarde automatique

Un formulaire de configuration permet de définir :

| Paramètre | Détail |
|---|---|
| Activation | Case à cocher (désactivée par défaut) |
| Fréquence | Quotidienne ou Hebdomadaire (quotidienne par défaut) |
| Heure d'exécution | Format HH:MM (02:00 par défaut) |
| Dossier de destination | Modifiable (bouton « Parcourir… ») |
| Sauvegardes à conserver | Nombre de sauvegardes conservées avant suppression automatique des plus anciennes (10 par défaut) |

> La sauvegarde automatique ne peut s'exécuter que lorsque l'application est ouverte.

## Restauration

Bouton **« Restaurer la sauvegarde sélectionnée »**, disponible pour toute sauvegarde présente dans l'historique.

### Procédure

1. Sélectionner une sauvegarde dans l'historique.
2. Cliquer sur « Restaurer la sauvegarde sélectionnée ».
3. Confirmer — le message affiché est explicite :
   > *« Voulez-vous vraiment restaurer cette sauvegarde ? La base de données actuelle sera remplacée (une sauvegarde de sécurité de l'état actuel sera créée automatiquement avant toute modification). L'application devra être redémarrée après une restauration réussie. Cette action est irréversible sans cette sauvegarde de sécurité. »*
4. Après une restauration réussie, **redémarrer l'application**.

> **Important — Une restauration remplace entièrement la base de données actuelle.** Toute donnée saisie après la date de la sauvegarde restaurée sera perdue (sauf dans la sauvegarde de sécurité créée automatiquement juste avant la restauration).

**Capture à insérer** : `[CAPTURE 18 — SAUVEGARDES]`

## Réinitialisation des données métier

### Objectif
Permettre, après une période de test du logiciel, de repartir avec une base métier propre pour l'exploitation réelle — sans désinstaller StockManager et sans perdre la configuration déjà en place.

### Qui peut l'utiliser
**Administrateur uniquement.**

### Accès
Bas de l'écran Sauvegardes, section « Zone dangereuse — Réinitialisation des données métier ».

### Données supprimées définitivement
Articles, catégories, fournisseurs, motifs de sortie, clients, entrées, sorties, ventes, paiements, inventaires, et tous les mouvements de stock.

### Données conservées
Utilisateurs, rôles et permissions, paramètres de l'entreprise (dont le logo et la devise), licence active, et l'intégralité du journal d'audit — y compris l'événement de la réinitialisation elle-même.

### Procédure

1. Cliquer sur « Réinitialiser les données métier… ».
2. Un message d'avertissement détaille précisément ce qui sera supprimé et ce qui sera conservé.
3. Recopier exactement le mot **RÉINITIALISER** dans le champ de confirmation — le bouton de confirmation ne s'active qu'à cette condition, pour éviter toute suppression accidentelle.
4. Valider.

### Déroulement interne (sécurité)

1. Une **sauvegarde de sécurité** est créée et vérifiée automatiquement.
2. **Si cette sauvegarde échoue, la réinitialisation est intégralement annulée** — aucune donnée n'est supprimée.
3. Si la sauvegarde réussit, la suppression des données métier est effectuée.
4. Un événement est inscrit dans le journal d'audit, que la réinitialisation réussisse ou échoue.

> **Important** — Cette opération est irréversible autrement que par une restauration manuelle de la sauvegarde de sécurité créée à l'étape 1 (voir « Restauration » ci-dessus). Elle est réservée à un usage précis (fin d'une période de test) et ne doit jamais être utilisée à la légère.

---

# 16. Journal d'audit

## Objectif
Assurer la traçabilité : savoir qui a fait quoi, et quand.

## Qui peut l'utiliser
Administrateur uniquement.

## Accès
Menu Audit.

## Description de l'écran
Un tableau listant chaque événement (date/heure, utilisateur, action, entité concernée, référence, résultat succès/échec). Filtres : recherche libre, période (par défaut, les **30 derniers jours** — les cases de date peuvent être décochées pour consulter tout l'historique), entité concernée.

Double-cliquer sur une ligne ouvre le détail complet de l'événement.

## Règle métier
Le journal d'audit est un enregistrement **permanent** : aucun événement n'est jamais modifié ni supprimé. Il n'existe pas, dans la version actuelle, de fonction d'export du journal d'audit.

**Capture à insérer** : `[CAPTURE 19 — AUDIT]`

---

# 17. Licence

## Objectif
Consulter l'état de la licence active de l'application, et en activer une nouvelle si nécessaire.

## Qui peut l'utiliser
Administrateur uniquement.

## Accès
Menu Licences.

## Description de l'écran
Statut de la licence, client, édition, identifiant de licence, dates d'émission/d'expiration, nombre maximum d'utilisateurs, nombre maximum de postes, liste des fonctionnalités activées, identifiant du poste actuel. Bouton **« Importer / activer une licence… »**.

## États possibles de la licence

| État affiché | Signification |
|---|---|
| Valide | La licence est active et en cours de validité |
| Expirée | La date d'expiration de la licence est dépassée |
| Aucune licence activée | Aucune licence n'a encore été importée |
| Invalide | La licence ne correspond pas au format attendu ou sa signature ne peut pas être vérifiée |
| Corrompue | Le fichier de licence enregistré est illisible |

## Procédure — Activer une licence

1. Ouvrir le menu Licences.
2. Cliquer sur « Importer / activer une licence… ».
3. Sélectionner le fichier de licence (`.lic`) fourni par votre éditeur.
4. La page affiche alors le détail de la licence activée.

> Aucune connexion Internet n'est nécessaire pour activer ou vérifier une licence : tout se passe localement sur le poste.

## Éditions

Quatre éditions existent dans le logiciel : **DEMO, STANDARD, PROFESSIONAL, ENTREPRISE**.

> **Important — Ces éditions ne constituent pas un engagement commercial définitif dans ce document.** Les fonctionnalités associées à chaque édition, listées ci-dessous à titre indicatif, correspondent aux valeurs par défaut définies dans le logiciel au moment de la rédaction de ce manuel. **C'est toujours le contenu réel de la licence signée qui fait foi**, pas cette description. Les conditions commerciales précises doivent être confirmées avec votre éditeur. **[À CONFIRMER commercialement avant diffusion au client]**

Indicatif (valeurs par défaut du générateur de licence) :
- **DEMO** : catalogue (articles, catégories, fournisseurs) et mouvements de stock (entrées, sorties, mouvements) uniquement.
- **STANDARD** : DEMO + ventes, inventaires, rapports.
- **PROFESSIONAL** : STANDARD + export des rapports, sauvegardes (dont la réinitialisation des données métier, chapitre 15, qui réutilise techniquement les sauvegardes), journal d'audit.
- **ENTREPRISE** : toutes les fonctionnalités, y compris la gestion de plusieurs comptes utilisateurs.

**Capture à insérer** : `[CAPTURE 20 — LICENCE]`

---

# 18. À propos et support

## Objectif
Retrouver rapidement les informations de version du logiciel et savoir où trouver de l'aide.

## Accès
Bouton **« À propos »**, dans la barre supérieure de l'application (accessible à tous les comptes connectés).

## Contenu affiché

- Le **logo officiel complet** de StockManager (symbole + nom + slogan), affiché sans déformation
- Nom du produit : **StockManager Desktop**
- Version installée
- Éditeur : **TechNova**
- Section Licence (état et édition), visible uniquement pour les comptes autorisés à consulter la licence (Administrateur)
- Section Support :
  > *« Pour obtenir de l'aide, consultez la documentation utilisateur et les fichiers de diagnostic/log de l'application. »*

> **Important** — StockManager n'affiche, dans sa version actuelle, **aucune adresse email, numéro de téléphone ou site web de support**. Le présent manuel ne doit donc en mentionner aucun qui ne soit pas explicitement fourni par vous. Coordonnées de support à ajouter par le client si souhaité : [EMAIL], [TÉLÉPHONE].

**Capture à insérer** : `[CAPTURE 21 — À PROPOS]`

---

# 19. Bonnes pratiques

- **Vérifiez avant de valider.** Une entrée, une sortie, une vente ou un inventaire validé ne peut plus être modifié — seule une annulation (quand elle est possible) permet de revenir en arrière.
- **Vérifiez les quantités et les articles saisis** avant toute validation, en particulier pour les inventaires (non annulables).
- **Effectuez des sauvegardes régulières**, idéalement en activant la sauvegarde automatique, et vérifiez de temps en temps que l'historique des sauvegardes se remplit bien.
- **Protégez vos comptes.** Ne partagez jamais votre mot de passe, même entre collègues. Chaque personne doit disposer de son propre compte.
- **N'utilisez pas le compte Administrateur pour les tâches quotidiennes** (ventes, saisie de stock) si un compte au rôle plus restreint suffit — cela limite les risques d'erreur.
- **Vérifiez régulièrement les inventaires et l'écran Mouvements** pour repérer d'éventuels écarts anormaux.
- **Utilisez le journal d'audit** en cas de doute sur une action effectuée dans l'application (qui a fait quoi, et quand).

---

# 20. Dépannage

| Problème | Cause possible | Solution |
|---|---|---|
| « Identifiant ou mot de passe incorrect » | Identifiant ou mot de passe mal saisi | Vérifier la saisie ; en cas de doute, demander à un administrateur de réinitialiser le mot de passe |
| « Ce compte est désactivé » | Le compte a été désactivé par un administrateur | Contacter un administrateur pour réactiver le compte |
| Mot de passe temporaire perdu (tout premier démarrage) | Le mot de passe généré au premier lancement n'a été affiché qu'une seule fois, dans le journal de démarrage | Consulter le fichier de journal (voir chapitre 4/18) ; si introuvable, [À CONFIRMER — procédure de récupération à définir avec votre éditeur] |
| Opération refusée « le stock deviendrait négatif » | La quantité demandée dépasse le stock disponible | Vérifier le stock réel de l'article (écran Articles ou Mouvements) avant de retenter l'opération |
| Un article n'apparaît pas dans la liste de sélection | L'article est désactivé | Le réactiver depuis l'écran Articles si nécessaire |
| Un client n'apparaît pas dans la liste de sélection d'une nouvelle vente | Le client est désactivé | Le réactiver depuis l'écran Clients si nécessaire |
| Impossible d'annuler un inventaire validé | Fonctionnalité non disponible dans cette version (comportement normal) | Effectuer un nouvel inventaire ou une autre opération de correction |
| Bouton grisé / action impossible | Le rôle du compte connecté ne dispose pas de la permission nécessaire | Vérifier la matrice des rôles (chapitre 9) ou contacter un administrateur |
| Licence affichée comme « Expirée », « Invalide » ou « Aucune licence activée » | Licence expirée, corrompue, ou jamais activée | Contacter votre éditeur pour obtenir un nouveau fichier de licence, puis l'importer (chapitre 17) |
| Échec d'une restauration de sauvegarde | Fichier de sauvegarde corrompu ou version de base de données incompatible | Vérifier les journaux / contacter le support |
| Problème non listé ici | Cause à diagnostiquer | Vérifier les journaux de diagnostic (`%APPDATA%\StockManager\logs\stockmanager.log`) / contacter le support |

---

# 21. Glossaire

| Terme | Définition simple |
|---|---|
| **Article** | Un produit géré dans le stock. |
| **Catégorie** | Un regroupement d'articles similaires. |
| **Fournisseur** | Une entreprise auprès de laquelle des articles sont achetés. |
| **Client** | Une personne ou entreprise à qui l'on vend des articles. |
| **Entrée** | Réception de marchandise qui augmente le stock. |
| **Sortie** | Retrait de stock qui n'est pas une vente (casse, perte, usage interne...). |
| **Vente** | Transaction commerciale avec un client, qui diminue le stock. |
| **Mouvement** | Toute variation enregistrée du stock d'un article (entrée, sortie, vente, ajustement, annulation). |
| **Inventaire** | Comptage physique du stock, comparé au stock théorique, avec ajustement à la clé. |
| **CMUP** | Coût Moyen Unitaire Pondéré : coût moyen d'un article, recalculé à chaque entrée de stock. |
| **Stock disponible / stock actuel** | Quantité actuellement en stock pour un article. |
| **Stock de sécurité / stock minimum** | Seuil en dessous duquel un article est signalé en « stock faible ». |
| **Stock faible** | Article dont le stock est au niveau ou en dessous de son stock minimum. |
| **Rupture** | Article dont le stock est à zéro. |
| **Brouillon** | État initial d'un document, avant validation — ne modifie pas le stock. |
| **Validation** | Action qui rend un document définitif et modifie réellement le stock. |
| **Annulation** | Action qui, lorsqu'elle est autorisée, restaure le stock d'un document déjà validé, sans supprimer ce document. |
| **Audit** | Journal de traçabilité de toutes les actions importantes réalisées dans l'application. |
| **Licence** | Fichier qui débloque les fonctionnalités de l'application selon l'édition achetée. |
| **Permission** | Une autorisation précise (ex. « créer un article »). |
| **Rôle** | Un ensemble de permissions attribué à un utilisateur (Administrateur, Gestionnaire de stock, Vendeur, Consultation). |
| **Sauvegarde** | Copie de sécurité de la base de données. |
| **Restauration** | Remplacement de la base de données actuelle par une sauvegarde. |

---

# 22. Annexe — Matrice complète des permissions

Cette annexe liste les **75 permissions réelles** définies dans l'application, regroupées par module, avec le détail exact pour chacun des quatre rôles (A = Administrateur, G = Gestionnaire de stock, V = Vendeur, C = Consultation).

### Dashboard
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter le tableau de bord | ✓ | ✓ | ✓ | ✓ |

### Articles
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les articles | ✓ | ✓ | ✓ | ✓ |
| Créer un article | ✓ | ✓ | — | — |
| Modifier un article | ✓ | ✓ | — | — |
| Activer un article | ✓ | ✓ | — | — |
| Désactiver un article | ✓ | ✓ | — | — |

### Catégories
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les catégories | ✓ | ✓ | — | ✓ |
| Créer une catégorie | ✓ | ✓ | — | — |
| Modifier une catégorie | ✓ | ✓ | — | — |
| Activer une catégorie | ✓ | ✓ | — | — |
| Désactiver une catégorie | ✓ | ✓ | — | — |

### Fournisseurs
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les fournisseurs | ✓ | ✓ | — | ✓ |
| Créer un fournisseur | ✓ | ✓ | — | — |
| Modifier un fournisseur | ✓ | ✓ | — | — |
| Activer un fournisseur | ✓ | ✓ | — | — |
| Désactiver un fournisseur | ✓ | ✓ | — | — |

### Motifs de sortie
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les motifs de sortie | ✓ | — | — | — |
| Créer un motif de sortie | ✓ | — | — | — |
| Modifier un motif de sortie | ✓ | — | — | — |
| Activer un motif de sortie | ✓ | — | — | — |
| Désactiver un motif de sortie | ✓ | — | — | — |

### Entrées
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les entrées | ✓ | ✓ | — | — |
| Créer une entrée | ✓ | ✓ | — | — |
| Modifier une entrée en brouillon | ✓ | ✓ | — | — |
| Valider une entrée | ✓ | ✓ | — | — |
| Annuler une entrée validée | ✓ | — | — | — |

### Sorties
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les sorties | ✓ | ✓ | — | — |
| Créer une sortie | ✓ | ✓ | — | — |
| Modifier une sortie en brouillon | ✓ | ✓ | — | — |
| Valider une sortie | ✓ | ✓ | — | — |
| Annuler une sortie validée | ✓ | — | — | — |

### Ventes
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les ventes | ✓ | — | ✓ | — |
| Créer une vente | ✓ | — | ✓ | — |
| Modifier une vente en brouillon | ✓ | — | ✓ | — |
| Valider une vente | ✓ | — | ✓ | — |
| Annuler une vente validée | ✓ | — | — | — |
| Enregistrer un paiement sur une vente | ✓ | — | ✓ | — |

### Clients
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les clients | ✓ | ✓ | ✓ | — |
| Créer un client | ✓ | ✓ | ✓ | — |
| Modifier un client | ✓ | ✓ | ✓ | — |
| Activer un client | ✓ | ✓ | — | — |
| Désactiver un client | ✓ | ✓ | — | — |

### Mouvements
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les mouvements de stock | ✓ | ✓ | — | ✓ |

### Inventaires
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les inventaires | ✓ | ✓ | — | — |
| Créer un inventaire | ✓ | ✓ | — | — |
| Modifier un inventaire en brouillon | ✓ | ✓ | — | — |
| Valider un inventaire | ✓ | ✓ | — | — |

### Rapports
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les rapports | ✓ | ✓ | — | ✓ |
| Exporter un rapport | ✓ | ✓ | — | — |

### Utilisateurs
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les utilisateurs | ✓ | — | — | — |
| Créer un utilisateur | ✓ | — | — | — |
| Modifier un utilisateur | ✓ | — | — | — |
| Activer/désactiver un compte utilisateur | ✓ | — | — | — |
| Réinitialiser le mot de passe d'un utilisateur | ✓ | — | — | — |
| Générer/régénérer son propre code de récupération administrateur | ✓ | — | — | — |

### Rôles
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les rôles et permissions | ✓ | — | — | — |
| Modifier les permissions d'un rôle | ✓ | — | — | — |

### Paramètres
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les paramètres | ✓ | — | — | — |
| Modifier les paramètres | ✓ | — | — | — |

### Sauvegardes
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter l'historique des sauvegardes | ✓ | — | — | — |
| Lancer une sauvegarde | ✓ | — | — | — |

### Restauration
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Restaurer une sauvegarde | ✓ | — | — | — |

### Audit
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter le journal d'audit | ✓ | — | — | — |

### Licences
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter la licence | ✓ | — | — | — |
| Activer une licence | ✓ | — | — | — |

### Système
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Réinitialiser les données métier | ✓ | — | — | — |

### Locations
| Permission | A | G | V | C |
|---|:-:|:-:|:-:|:-:|
| Consulter les locations | ✓ | ✓ | ✓ | ✓ |
| Créer une location | ✓ | ✓ | ✓ | — |
| Modifier une location en brouillon | ✓ | ✓ | ✓ | — |
| Confirmer une location | ✓ | ✓ | ✓ | — |
| Enregistrer le départ d'une location | ✓ | ✓ | ✓ | — |
| Enregistrer un retour (total ou partiel) sur une location | ✓ | ✓ | ✓ | — |
| Annuler une location (avant départ uniquement) | ✓ | — | — | — |
| Définir et restituer la caution d'une location | ✓ | ✓ | ✓ | — |
| Enregistrer un paiement sur une location | ✓ | ✓ | ✓ | — |

> Le fonctionnement du module Locations (statuts, quantités réservée/en location/immobilisée, calcul de la facturation au retour, gestion de la caution) est détaillé au chapitre 13.5.

---

# 23. Annexe — Liste des captures d'écran à réaliser

Aucune capture n'est intégrée à ce document. La liste ci-dessous doit être suivie lors de la prise de captures réelles (environnement Windows ou environnement graphique équivalent, avec des données de démonstration — jamais de données client réelles).

| N° | Fichier suggéré | Écran | Scénario | Données nécessaires |
|---|---|---|---|---|
| 01 | `01-connexion.png` | Écran de connexion | Écran vide | Aucune |
| 02 | `02-premier-mdp.png` | Changement de mot de passe obligatoire | Après le tout premier login admin | Compte admin initial |
| 03 | `03-guide-demarrage.png` | Guide de démarrage | Les 5 étapes visibles | Compte admin initial, 1er login |
| 04 | `04-dashboard.png` | Tableau de bord | Avec données (KPI + 3 graphiques) | Au moins 1 article, 1 vente, 1 mouvement |
| 05 | `05-parametres.png` | Paramètres | Formulaire rempli + logo | Logo de démonstration générique |
| 06 | `06-utilisateurs.png` | Utilisateurs | Liste avec 2-3 comptes | Comptes de démonstration |
| 07 | `07-roles.png` | Rôles + édition des permissions | Édition d'un rôle non-Administrateur | — |
| 08 | `08-categories.png` | Catégories | Liste avec quelques catégories | 2-3 catégories |
| 09 | `09-articles.png` | Articles (liste + formulaire) | Formulaire de création | 1 catégorie créée |
| 10 | `10-fournisseurs.png` | Fournisseurs | Liste | 1-2 fournisseurs |
| 11 | `11-entree.png` | Entrée de stock | Brouillon puis validée | 1 fournisseur, 1 article |
| 12 | `12-sortie.png` | Sortie de stock | Avec motif sélectionné | 1 motif, 1 article en stock |
| 13 | `13-vente.png` | Vente | Formulaire avec lignes + client | 1 client, 1 article |
| 14 | `14-client.png` | Clients | Formulaire | — |
| 15 | `15-inventaire.png` | Inventaire | Écart affiché | 1 article à stock connu |
| 16 | `16-mouvements.png` | Mouvements | Filtres + résultats | Historique de démonstration |
| 17 | `17-rapports.png` | Rapports | Un rapport avec filtres appliqués | Historique de démonstration |
| 18 | `18-sauvegardes.png` | Sauvegardes | Configuration + historique | 1 sauvegarde effectuée |
| 19 | `19-audit.png` | Journal d'audit | Détail d'un événement ouvert | Historique de démonstration |
| 20 | `20-licence.png` | Licence | Licence active affichée | Licence de démonstration signée |
| 21 | `21-a-propos.png` | À propos | Section licence visible | Compte Administrateur |
| 22 | `22-creances.png` | Créances clients | Liste filtrée par client, avec créance affichée | Au moins 1 vente à crédit partiellement payée |

**Marqueurs correspondants utilisés dans ce document** (pour repérage rapide) :

```
[CAPTURE 01 — CONNEXION]
[CAPTURE 02 — PREMIER MOT DE PASSE]
[CAPTURE 03 — GUIDE DE DÉMARRAGE]
[CAPTURE 04 — DASHBOARD]
[CAPTURE 05 — PARAMÈTRES]
[CAPTURE 06 — UTILISATEURS]
[CAPTURE 07 — RÔLES]
[CAPTURE 08 — CATÉGORIES]
[CAPTURE 09 — ARTICLES]
[CAPTURE 10 — FOURNISSEURS]
[CAPTURE 11 — ENTRÉE]
[CAPTURE 12 — SORTIE]
[CAPTURE 13 — VENTE]
[CAPTURE 14 — CLIENT]
[CAPTURE 15 — INVENTAIRE]
[CAPTURE 16 — MOUVEMENTS]
[CAPTURE 17 — RAPPORTS]
[CAPTURE 18 — SAUVEGARDES]
[CAPTURE 19 — AUDIT]
[CAPTURE 20 — LICENCE]
[CAPTURE 21 — À PROPOS]
[CAPTURE 22 — CRÉANCES]
```

---

*Fin du document de travail. Ce fichier est une source de rédaction Markdown — il ne constitue pas encore le livrable final DOCX/PDF.*
