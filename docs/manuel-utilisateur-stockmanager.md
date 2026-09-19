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
14. Rapports
15. Sauvegardes et restauration
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

## Points d'attention
- Ne partagez jamais votre mot de passe avec un autre utilisateur (voir chapitre 19 — Bonnes pratiques).
- Il n'existe pas, dans cette version, de fonctionnalité « mot de passe oublié » en libre-service : seul un administrateur peut réinitialiser le mot de passe d'un compte (chapitre 9).

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
| Clients | ✓ | ✓ | Création/modification (pas activer/désactiver) | — |
| Mouvements (consultation) | ✓ | ✓ | — | ✓ |
| Rapports (consulter) | ✓ | ✓ | — | ✓ |
| Rapports (exporter) | ✓ | ✓ | — | — |
| Utilisateurs / Rôles | ✓ | — | — | — |
| Paramètres | ✓ | — | — | — |
| Sauvegardes | ✓ | — | — | — |
| Journal d'audit | ✓ | — | — | — |
| Licence | ✓ | — | — | — |

> Cette matrice est une **présentation simplifiée**. Le détail complet des permissions (63 permissions réelles) figure en annexe (chapitre 22) — c'est ce détail qui fait foi en cas de doute.

> **Important** — Les droits d'accès sont vérifiés à deux niveaux : au niveau de l'écran (un bouton non autorisé n'est pas affiché ou est désactivé) **et** au niveau du programme lui-même. Un utilisateur ne peut donc jamais contourner ses droits, même en essayant d'accéder à une fonctionnalité par un autre moyen.

## Procédure — Créer un utilisateur

1. Ouvrir le menu Utilisateurs.
2. Cliquer sur « Ajouter un utilisateur ».
3. Renseigner : nom d'utilisateur, mot de passe, rôle, et cocher « Compte actif » si le compte doit être immédiatement utilisable.
4. Valider.

**Résultat attendu** : le compte est créé. Son titulaire devra changer ce mot de passe dès sa première connexion.

## Procédure — Modifier le rôle d'un utilisateur

1. Sélectionner l'utilisateur dans la liste.
2. Cliquer sur « Modifier ».
3. Choisir le nouveau rôle.
4. Valider.

> Seul le rôle peut être modifié ici — pas le nom d'utilisateur ni le mot de passe.

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
| Code-barres | Non | Doit être unique s'il est renseigné |
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
Bouton « Annuler » (Administrateur uniquement), disponible uniquement pour une entrée déjà validée. Le stock est restauré à son niveau précédent via un mouvement inverse.

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
Identique aux entrées (Administrateur uniquement, uniquement après validation).

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
4. Ajouter les lignes de vente (article, quantité, prix unitaire — pré-rempli avec le prix catalogue, modifiable).
5. Enregistrer en brouillon.

### Calcul du total
Le total de la vente est la somme des lignes (quantité × prix unitaire saisi). Le prix effectivement facturé (historisé sur la ligne) sert toujours de référence, même si le prix catalogue de l'article change ensuite.

## 12.3 Validation d'une vente

Bouton « Valider » (visible uniquement pour une vente en brouillon). La validation :
- diminue le stock des articles vendus ;
- génère un mouvement de type VENTE (dont le coût de valorisation interne est le CMUP courant — distinct du prix facturé au client) ;
- rend la vente définitive (elle ne peut plus être modifiée, seulement annulée).

## 12.4 Annulation

Bouton « Annuler » (Administrateur uniquement), uniquement pour une vente déjà validée. Le stock vendu est restauré.

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
Informations de l'entreprise (nom, coordonnées, logo — tels que renseignés dans les Paramètres), informations du client si renseignées, lignes de la vente, total, date/heure.

> Il n'existe pas, dans la version actuelle, d'archivage automatique des reçus PDF générés : chaque export doit être enregistré manuellement à l'endroit choisi par l'utilisateur.

**Capture à insérer** : `[CAPTURE 13 — VENTE]`, `[CAPTURE 14 — CLIENT]`

---

# 13. Inventaires

## Objectif
Comparer le stock réellement compté physiquement au stock théorique enregistré par l'application, et ajuster le stock en conséquence.

## Qui peut l'utiliser
Administrateur, Gestionnaire de stock.

## Procédure

1. Menu Inventaires → nouvel inventaire.
2. Choisir la date.
3. Ajouter une ligne par article à compter : sélectionner l'article (parmi les articles actifs), saisir le **stock compté**.
4. Le **stock théorique** de chaque ligne est capturé automatiquement au moment de l'ajout ; l'**écart** (compté − théorique) est calculé et affiché.
5. Une fois toutes les lignes saisies, cliquer sur « Valider ». Une confirmation détaille, ligne par ligne, le théorique/compté/écart, et précise que l'opération est définitive.

## Résultat attendu
Pour chaque écart non nul, un mouvement d'ajustement est généré automatiquement, portant le stock réel de chaque article à la valeur comptée.

> **Point important** — **Une fois un inventaire validé, il ne peut pas être annulé** dans cette version de StockManager. Vérifiez soigneusement les quantités comptées avant de valider. Une correction ultérieure nécessitera un nouvel inventaire ou une autre opération de stock.

**Capture à insérer** : `[CAPTURE 15 — INVENTAIRE]`

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
| État du stock | Vue complète du catalogue avec stock, CMUP et valeur | Recherche, Catégorie, Inclure inactifs | Non | CSV |
| Stock faible | Articles au niveau ou en dessous du seuil minimum | Recherche, Catégorie | Non | CSV |
| Ruptures | Articles à stock zéro | Recherche, Catégorie | Non | CSV |
| Mouvements | Historique des mouvements de stock | Article, Type de mouvement | Oui | CSV |
| Entrées | Historique des entrées | Statut | Oui | CSV |
| Sorties | Historique des sorties | Motif, Statut | Oui | CSV |
| Ventes | Historique des ventes | Statut | Oui | CSV |
| Inventaires | Résumé par inventaire (écarts, quantité ajustée) | Statut | Oui | CSV |
| Valorisation | Valeur du stock (stock × CMUP) et valeur totale | Recherche, Catégorie, Inclure inactifs | Non | CSV |

> Le rapport Inventaires présente un **résumé par inventaire** (nombre de lignes, écarts positifs/négatifs, quantité totale ajustée) — pas le détail ligne à ligne, qui reste consultable dans le détail de chaque inventaire.

## Export

- **Seul le format CSV est disponible** dans la version actuelle. Il n'existe pas d'export Excel ni PDF pour les rapports.
- Bouton « Exporter CSV ».
- Format technique du fichier : séparateur `;`, encodage compatible Excel (BOM UTF-8) — pensé pour une ouverture directe correcte dans Excel en français.
- Si le rapport ne contient aucune donnée, l'export est bloqué avec le message : « Aucune donnée à exporter. »

**Capture à insérer** : `[CAPTURE 17 — RAPPORTS]`

---

# 15. Sauvegardes et restauration

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
- **PROFESSIONAL** : STANDARD + export des rapports, sauvegardes, journal d'audit.
- **ENTREPRISE** : toutes les fonctionnalités, y compris la gestion de plusieurs comptes utilisateurs.

**Capture à insérer** : `[CAPTURE 20 — LICENCE]`

---

# 18. À propos et support

## Objectif
Retrouver rapidement les informations de version du logiciel et savoir où trouver de l'aide.

## Accès
Bouton **« À propos »**, dans la barre supérieure de l'application (accessible à tous les comptes connectés).

## Contenu affiché

- Nom du produit : **StockManager Desktop**
- Version installée
- Éditeur : **StockManager**
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

Cette annexe liste les **63 permissions réelles** définies dans l'application, regroupées par module, avec le détail exact pour chacun des quatre rôles (A = Administrateur, G = Gestionnaire de stock, V = Vendeur, C = Consultation).

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
```

---

*Fin du document de travail. Ce fichier est une source de rédaction Markdown — il ne constitue pas encore le livrable final DOCX/PDF.*
