# Manuel utilisateur — StockManager Desktop V1.0

**Éditeur :** TechNova
**Produit :** StockManager Desktop
**Version couverte par ce document :** 1.0.0
**Public :** utilisateur final non technique
**Nature du document :** manuel utilisateur, rédigé et vérifié directement à partir du comportement réel du code de l'application (aucune fonctionnalité supposée ou future n'y est décrite comme existante). Aucune capture d'écran n'est incluse.

> Convention utilisée dans tout ce manuel : lorsqu'une information n'a pas pu être vérifiée dans le code ou n'a pas encore été testée sur un poste Windows réel, elle est signalée par **[NON VÉRIFIÉ]**. Lorsqu'une fonctionnalité communément attendue n'existe pas dans cette version, elle est signalée par **[ABSENT EN V1]**.

---

## Table des matières

1. [Présentation de StockManager](#1-présentation-de-stockmanager)
2. [Installation et premier lancement](#2-installation-et-premier-lancement)
3. [Tableau de bord](#3-tableau-de-bord)
4. [Articles](#4-articles)
5. [Catégories](#5-catégories)
6. [Fournisseurs](#6-fournisseurs)
7. [Clients](#7-clients)
8. [Motifs de sortie](#8-motifs-de-sortie)
9. [Entrées de stock](#9-entrées-de-stock)
10. [Sorties de stock](#10-sorties-de-stock)
11. [Ventes](#11-ventes)
12. [Paiements](#12-paiements)
13. [Inventaires](#13-inventaires)
14. [Mouvements](#14-mouvements)
15. [Rapports](#15-rapports)
16. [Utilisateurs](#16-utilisateurs)
17. [Rôles et permissions](#17-rôles-et-permissions)
18. [Sauvegardes](#18-sauvegardes)
19. [Licences](#19-licences)
20. [Paramètres](#20-paramètres)
21. [Reçus et impressions](#21-reçus-et-impressions)
22. [Règles importantes à connaître](#22-règles-importantes-à-connaître)
23. [Sauvegarde et bonnes pratiques utilisateur](#23-sauvegarde-et-bonnes-pratiques-utilisateur)
24. [Dépannage / problèmes fréquents](#24-dépannage--problèmes-fréquents)
25. [Glossaire](#25-glossaire)

---

## 1. Présentation de StockManager

### Objectif

StockManager Desktop est un logiciel de gestion de stock destiné aux petites et moyennes entreprises. Il permet de gérer un catalogue d'articles, de suivre les mouvements de stock (entrées, sorties, ventes, inventaires), d'enregistrer des ventes avec ou sans client identifié, de suivre les paiements et les créances, de produire des rapports, de gérer les comptes utilisateurs et leurs droits d'accès, et de sauvegarder/restaurer les données.

### Public cible

Toute entreprise ayant besoin de suivre un stock physique de manière fiable, sur un poste de travail unique : commerces, dépôts, petites unités de production, points de vente.

### Fonctionnement Desktop / local

StockManager Desktop est une application installée directement sur un ordinateur (« application de bureau »), et non un service web. Toutes les données sont stockées dans une base de données locale (technologie SQLite) sur l'ordinateur où l'application est installée. **Cette version est conçue pour un usage sur un seul poste de travail** : elle ne synchronise pas les données entre plusieurs ordinateurs. Si plusieurs personnes doivent utiliser StockManager, elles se connectent avec leur propre compte utilisateur, mais **sur le même ordinateur**.

### Fonctionnement hors ligne

StockManager fonctionne **entièrement sans connexion Internet**, aussi bien pour l'utilisation quotidienne que pour l'activation de la licence. Aucune donnée n'est transmise à un serveur distant : le code de l'application ne contient aucun appel réseau (vérifié : aucune bibliothèque de communication réseau n'est utilisée par l'application). L'activation de licence se fait par simple import d'un fichier fourni par l'éditeur ou l'intégrateur (voir chapitre 19).

### Rôle de TechNova comme éditeur

**TechNova** est l'éditeur du logiciel StockManager Desktop. Ce nom est fixe et apparaît dans l'écran « À propos » de l'application ainsi que dans les informations de l'exécutable Windows (propriétés du fichier) ; il n'est pas modifiable par l'utilisateur.

### Rôle de StockManager comme produit

**StockManager Desktop** est le nom du produit lui-même (distinct du nom de l'entreprise cliente qui l'utilise, qui est configuré dans les Paramètres — voir chapitre 20). Version couverte par ce manuel : **1.0.0**.

---

## 2. Installation et premier lancement

### Installation Windows

**[NON VÉRIFIÉ sur poste Windows réel]** — L'installation est prévue via un programme d'installation Windows classique (`StockManager-Setup-<version>.exe`), qui ne nécessite **pas** de droits administrateur (installation dans le dossier propre à l'utilisateur courant). Ce mécanisme est en place dans le projet, mais sa construction/exécution sur un poste Windows réel n'a pas encore été validée au moment de la rédaction de ce document.

À la fin de l'installation, un raccourci est créé dans le menu Démarrer.

**Mise à jour** : installer la nouvelle version par-dessus l'ancienne. Les données ne sont jamais écrasées par une mise à jour (elles sont stockées dans un dossier séparé du dossier d'installation).

**Désinstallation** : depuis le Panneau de configuration Windows. Les données ne sont **jamais** supprimées automatiquement lors d'une désinstallation — à supprimer manuellement si elles ne sont plus nécessaires.

**Emplacement des données** (Windows) :

| Donnée | Emplacement |
|---|---|
| Base de données | `%APPDATA%\StockManager\stockmanager.db` |
| Sauvegardes | `%APPDATA%\StockManager\backups\` (modifiable dans Sauvegardes) |
| Journaux techniques | `%APPDATA%\StockManager\logs\stockmanager.log` |

### Premier démarrage

Au tout premier lancement, l'application :
1. Crée automatiquement sa base de données locale.
2. Crée automatiquement un compte **Administrateur** initial, identifiant `admin`, avec un mot de passe généré aléatoirement (affiché une seule fois au démarrage, dans les journaux techniques).
3. Ce compte doit obligatoirement changer son mot de passe dès la première connexion (l'application l'exige avant de laisser accéder à l'écran principal).

### Connexion

À chaque lancement, un écran de connexion demande l'identifiant et le mot de passe. Si le compte doit changer de mot de passe (première connexion, ou après une réinitialisation par un administrateur), une fenêtre de changement de mot de passe obligatoire s'affiche : elle ne peut pas être fermée sans effectuer le changement (l'annuler déconnecte l'utilisateur).

En cas d'identifiant ou de mot de passe incorrect, le message est volontairement générique (« Identifiant ou mot de passe incorrect. ») pour ne pas révéler si un identifiant existe. Si le compte a été désactivé par un administrateur, un message spécifique l'indique.

### Configuration initiale — entreprise

Dans **Paramètres**, renseignez le nom, l'adresse, le téléphone, l'email et la devise de votre entreprise, ainsi que son logo. Ces informations apparaissent sur les reçus imprimés (voir chapitre 20).

### Licence

Sans licence activée, l'application reste accessible mais la plupart des fonctionnalités restent verrouillées selon l'édition. Voir chapitre 19 pour l'activation.

---

## 3. Tableau de bord

Le tableau de bord (accès nécessite la permission de consultation du tableau de bord) affiche une synthèse de l'activité, sur une **période sélectionnable** (deux sélecteurs de date « du » / « au », par défaut le mois en cours, du 1er jour du mois à aujourd'hui). Un bouton « Actualiser » recalcule les indicateurs pour la période choisie.

### Indicateurs principaux
- **Articles actifs** — nombre d'articles au statut actif.
- **Valeur du stock** — valeur totale du stock (quantité × coût moyen pondéré), tous articles actifs.
- **Stock faible** — nombre d'articles dont le stock actuel est descendu au niveau ou en dessous de leur stock minimum.
- **Ruptures** — nombre d'articles à stock nul.
- **Chiffre d'affaires** — somme des ventes **validées** sur la période sélectionnée.

### Indicateurs secondaires
- **Quantité en stock** (somme de toutes les quantités).
- **Entrées** validées sur la période.
- **Sorties** validées sur la période.
- **Ventes** validées sur la période.
- **Inventaires** validés sur la période.

### Graphiques
- Évolution des ventes (montant, agrégé automatiquement par jour, semaine ou mois selon la durée de la période choisie — jusqu'à 31 jours : par jour ; jusqu'à 120 jours : par semaine ; au-delà : par mois).
- Répartition des mouvements de stock par type sur la période.
- Valeur du stock par catégorie.
- Table des articles en stock faible (10 premiers par défaut, triés par déficit).

### Alertes
Des libellés « N article(s) en stock faible » / « N article(s) en rupture » apparaissent avec des boutons de raccourci vers le rapport correspondant.

### Activité récente

Un tableau « Activité récente » affiche les derniers mouvements de stock (date/heure, type, article, utilisateur, quantité). **Cette liste est strictement limitée aux 15 derniers mouvements** — il ne s'agit pas d'une limite d'affichage modifiable par l'utilisateur, mais d'une limite fixée dans le code de l'application. Pour consulter l'historique complet, utilisez le module Mouvements (chapitre 14).

### Bouton « Voir les mouvements »

Ce bouton (comme les boutons équivalents « Voir les ventes », « Voir les entrées », « Voir les sorties ») navigue directement vers le module correspondant de l'application (respectivement Mouvements, Ventes, Entrées, Sorties) pour consulter le détail complet, au-delà des 15 lignes affichées sur le tableau de bord.

Un champ vide (« — ») est affiché à la place d'un indicateur si l'utilisateur connecté n'a pas la permission nécessaire pour la donnée sous-jacente — jamais un zéro trompeur.

---

## 4. Articles

Un article représente un produit géré en stock.

### Création

Bouton « Ajouter » (nécessite la permission de création d'article). Champs du formulaire :

| Champ | Obligatoire ? | Remarques |
|---|---|---|
| Référence | **Oui** | Doit être unique dans le catalogue, 50 caractères max. |
| Désignation | **Oui** | 255 caractères max. |
| Catégorie | **Oui** | Doit être une catégorie active. |
| Fournisseur principal | Non | Doit être un fournisseur actif si renseigné. |
| Unité | **Oui** | Champ à saisie libre avec suggestions (pièce, unité, carton, paquet, kg, litre, mètre). |
| Prix d'achat | **Oui** | Doit être ≥ 0. |
| Prix de vente | **Oui** | Doit être ≥ 0. |
| Stock minimum | **Oui** | Doit être ≥ 0. |
| Stock maximum | Non | Si renseigné, doit être ≥ 0 et ≥ au stock minimum. |
| Stock initial | **Oui** (création uniquement) | Doit être ≥ 0. Si supérieur à 0, un mouvement d'ajustement traçable est créé — ce n'est jamais une simple valeur écrite directement. |
| Emplacement | Non | 100 caractères max. |
| Code-barres | Non | 50 caractères max. Doit être unique **parmi les articles actifs uniquement** — deux articles inactifs, ou un actif et un inactif, peuvent partager le même code-barres, mais jamais deux articles actifs. |
| Description | Non | 1000 caractères max. |

**Exemple** : créer un article « Sac de riz 25 kg » avec référence `RIZ-25KG`, catégorie « Alimentation », unité « sac », prix d'achat 12 000, prix de vente 15 000, stock minimum 5, stock initial 20.

### Modification

Bouton « Modifier ». Tous les champs ci-dessus restent modifiables **sauf le stock initial** (qui n'existe qu'à la création). Le stock actuel et le coût moyen pondéré (CMUP) sont affichés en lecture seule sur la fiche de modification, avec la mention « piloté par le système » : ils ne peuvent **jamais** être saisis manuellement, uniquement modifiés par les opérations de stock (entrées, sorties, ventes, inventaires).

### Activation / désactivation

Il n'existe pas de suppression d'article. Un article devenu obsolète est **désactivé** (bouton « Activer / désactiver »). Un article désactivé :
- reste visible dans l'historique des mouvements, entrées, sorties, ventes passées ;
- n'est plus proposé dans les listes de sélection pour une nouvelle opération (entrée, sortie, vente, inventaire) ;
- peut être réactivé à tout moment.

### Stock faible et rupture

Un article est en « stock faible » lorsque son stock actuel est inférieur ou égal à son stock minimum ; en « rupture » lorsque son stock actuel est nul. Ces états déclenchent une mise en évidence colorée dans la liste des articles (ambre/rouge), une case à cocher de filtrage « Stock faible uniquement », et alimentent le tableau de bord et le rapport « Stock faible ».

### Code-barres

Un article peut porter un code-barres optionnel, utilisable par douchette USB (« lecteur clavier ») dans les écrans Ventes et Inventaires : scanner un code ajoute directement une ligne pour l'article correspondant (s'il est actif). La recherche par code-barres ne retourne jamais un article désactivé.

---

## 5. Catégories

Une catégorie regroupe des articles (champ obligatoire sur la fiche article). Formulaire réduit à un seul champ :

| Champ | Obligatoire ? | Remarques |
|---|---|---|
| Nom | **Oui** | 100 caractères max, doit être unique. |

Création, modification et activation/désactivation suivent le même principe que pour les articles : **aucune suppression physique**, seulement une désactivation. Une catégorie désactivée n'est plus proposée pour un nouvel article, mais reste affichée pour les articles qui l'utilisent déjà.

---

## 6. Fournisseurs

| Champ | Obligatoire ? | Remarques |
|---|---|---|
| Nom / raison sociale | **Oui** | 150 caractères max. **Aucune unicité exigée** — deux fournisseurs peuvent légitimement porter le même nom. |
| Contact | Non | 150 caractères max. |
| Téléphone | Non | 30 caractères max. |
| Email | Non | 150 caractères max, doit contenir « @ » si renseigné. |
| Adresse | Non | 255 caractères max. |
| Ville | Non | 100 caractères max. |
| Pays | Non | 100 caractères max. |
| Observations | Non | 500 caractères max. |

Création, modification, activation/désactivation — pas de suppression physique. Un fournisseur désactivé n'est plus proposé pour une nouvelle fiche article ou une nouvelle entrée, mais reste visible dans l'historique.

---

## 7. Clients

| Champ | Obligatoire ? | Remarques |
|---|---|---|
| Nom | **Oui** | 150 caractères max. Aucune unicité exigée. |
| Téléphone | Non | 30 caractères max. |
| Email | Non | 150 caractères max, doit contenir « @ » si renseigné. |
| Adresse | Non | 255 caractères max. |
| Observations | Non | 500 caractères max. |

Un client peut être créé « à la volée » directement depuis le formulaire de vente (bouton « Nouveau client… »), sans quitter la saisie de la vente en cours.

Création, modification, activation/désactivation — pas de suppression physique. Un client désactivé reste consultable, en particulier dans l'historique des ventes qui lui sont associées, mais n'est plus proposé pour une nouvelle vente.

---

## 8. Motifs de sortie

Les motifs de sortie qualifient une sortie de stock (perte, casse, usage interne, don, etc.).

| Champ | Obligatoire ? | Remarques |
|---|---|---|
| Libellé | **Oui** | 150 caractères max. Unicité vérifiée en ignorant la casse et les espaces superflus (« Perte », « perte » et « PERTE » sont considérés comme un seul et même motif). |
| Description | Non | 500 caractères max. |

**Particularité importante** : la gestion des motifs de sortie (création, modification, activation, et même leur simple consultation) est réservée à l'**Administrateur** uniquement — ni le Gestionnaire de stock ni aucun autre rôle n'y a accès par défaut.

Pas de suppression physique. Un motif désactivé reste visible dans l'historique mais n'est plus proposé pour une nouvelle sortie.

---

## 9. Entrées de stock

Une entrée de stock enregistre une réception de marchandise (généralement en provenance d'un fournisseur).

### Cycle de vie : Brouillon → Validée → (Annulée)

**Création (brouillon)** : fournisseur (obligatoire, doit être actif), date (obligatoire), référence document (optionnel, 100 caractères), commentaire (optionnel, 500 caractères), puis une ou plusieurs lignes : article, quantité (doit être strictement positive), prix unitaire d'achat (doit être ≥ 0). Un numéro d'entrée est généré automatiquement. **Une entrée en brouillon n'a aucun impact sur le stock.**

Une entrée en brouillon peut être librement modifiée (toutes les lignes sont remplacées à chaque modification).

### Règles de date

La date d'une entrée **ne peut jamais être postérieure à la date du jour** — cette règle est vérifiée aussi bien à la création qu'à la modification du brouillon, et refusée avec un message explicite si elle est violée.

### Validation

Bouton « Valider ». Nécessite au moins une ligne. À la validation :
- un **mouvement de stock de type Entrée** est créé pour chaque ligne, augmentant le stock de l'article ;
- le **CMUP (coût moyen unitaire pondéré)** de chaque article concerné est recalculé (c'est la seule opération de l'application qui recalcule le CMUP — voir chapitre 22 pour la formule) ;
- l'entrée passe au statut « Validée » et n'est plus modifiable.

### Impact sur le stock et CMUP

Chaque entrée validée augmente le stock de la quantité reçue et recalcule le CMUP de l'article selon la formule de moyenne pondérée (stock avant + valeur reçue, divisé par le nouveau stock total).

### Annulation

Une entrée **déjà validée** (et seulement dans ce cas — un brouillon ne s'« annule » pas, il se modifie ou reste tel quel) peut être annulée. L'annulation génère, pour chaque ligne, un mouvement inverse (« Annulation ») qui retire du stock la quantité précédemment reçue, sans jamais recalculer rétroactivement le CMUP. L'entrée originale n'est jamais supprimée : elle passe au statut « Annulée » et reste consultable dans l'historique.

---

## 10. Sorties de stock

Une sortie de stock enregistre une diminution de stock non liée à une vente (perte, casse, usage interne, don…).

### Cycle de vie : Brouillon → Validée → (Annulée)

**Création (brouillon)** : motif de sortie (obligatoire, doit être actif), date (obligatoire), bénéficiaire (optionnel, 150 caractères), référence (optionnel, 100 caractères), commentaire (optionnel, 500 caractères), puis des lignes : article, quantité (strictement positive). **Aucun coût unitaire n'est saisi manuellement** : le coût de valorisation d'une sortie est toujours le coût moyen pondéré (CMUP) courant de l'article, jamais une valeur libre — il est capturé à nouveau au moment de la validation (et non figé dès le brouillon), pour refléter le CMUP le plus à jour.

Même règle de date que pour les Entrées : aucune date future.

### Validation

À la validation, l'application revérifie que chaque article est toujours actif, recalcule le coût de valorisation sur le CMUP courant, puis crée un **mouvement de stock de type Sortie** (quantité négative) par ligne. Le stock disponible est vérifié automatiquement : **si la quantité demandée dépasse le stock disponible, la validation est refusée avec un message explicite** — aucune sortie ne peut faire passer un stock sous zéro. La sortie passe au statut « Validée » et n'est plus modifiable. Une sortie ne modifie jamais le CMUP de l'article (seule la quantité change).

### Annulation

Comme pour les Entrées : uniquement possible sur une sortie déjà validée. Génère un mouvement inverse restituant la quantité au stock, sans recalcul de CMUP. La sortie originale passe au statut « Annulée », jamais supprimée.

---

## 11. Ventes

### Création

Formulaire de vente : date (obligatoire, jamais future), client (voir ci-dessous), lignes de vente. Le bouton d'enregistrement est intitulé **« Enregistrer en brouillon »** — toute vente passe obligatoirement par un état brouillon avant validation, il n'existe pas de raccourci « créer et valider en une seule étape ».

Un champ de saisie de code-barres permet, avec une douchette USB, d'ajouter instantanément une ligne (quantité 1, au prix de vente courant) pour l'article scanné, s'il est actif.

### Vente comptant / client facultatif

**Le client est entièrement facultatif.** Une vente sans client rattaché (« vente comptant ») est un cas d'usage parfaitement normal et courant — dans ce cas, le champ client reste vide (« (Aucun client / Vente comptant) » dans le sélecteur). L'absence de client n'a aucun impact sur le stock, le CMUP, les mouvements, les prix ou les quantités : le client ne fait que transiter comme information associée à la vente.

Un client peut être créé à la volée via le bouton « Nouveau client… » sans quitter le formulaire de vente.

### Lignes de vente

Chaque ligne comporte : article (obligatoire), quantité (obligatoire, strictement positive), prix unitaire (obligatoire). **Le prix de vente unitaire est pré-rempli avec le prix de vente actuel de l'article au moment où il est sélectionné, mais reste librement modifiable** : c'est le prix réellement facturé qui est conservé sur la ligne, il n'est jamais recalculé automatiquement, même si le prix catalogue de l'article change ensuite.

### Validation

Nécessite au moins une ligne. Chaque article est revérifié comme actif. À la validation :
- un **mouvement de stock de type Vente** (quantité négative) est créé pour chaque ligne ;
- le stock disponible est vérifié : si le stock est insuffisant, la validation est refusée ;
- il est possible de saisir un **paiement initial** dès la validation (voir chapitre 12) ;
- la vente passe au statut « Validée » et n'est plus modifiable.

### Impact stock

Identique aux sorties : diminution du stock, aucun recalcul de CMUP (le mouvement enregistre le CMUP courant comme coût de valorisation, à titre indicatif seulement).

### Brouillon et suppression du brouillon

Une vente en brouillon peut être modifiée librement (toutes ses lignes et son client sont alors remplacés). **C'est le seul document de toute l'application qui peut être supprimé physiquement** — uniquement à l'état brouillon, car un brouillon jamais validé n'a produit aucun mouvement de stock ni aucune conséquence sur l'historique. Le message de confirmation affiché est : *« Voulez-vous vraiment supprimer cette vente en brouillon ? Cette action est irréversible. »*

### Annulation d'une vente validée

Une vente déjà validée peut être annulée (jamais un brouillon, qui n'a pas besoin d'être « annulé »). L'annulation génère, pour chaque ligne, un mouvement inverse restituant la quantité au stock. La vente originale passe au statut « Annulée », jamais supprimée.

**Important — effet sur les paiements déjà encaissés** : l'annulation d'une vente **ne modifie, ne supprime et ne rembourse jamais automatiquement les paiements déjà enregistrés**. Le montant payé et le statut de paiement restent figés à leur valeur au moment de l'annulation, comme trace historique de ce qui a réellement été perçu. Un éventuel remboursement reste une démarche à gérer manuellement en dehors de l'application (aucune écriture comptable de remboursement n'est générée).

---

## 12. Paiements

Une vente **validée** peut recevoir un ou plusieurs paiements (jamais un brouillon, qui ne peut avoir aucun paiement).

### Paiement initial

Lors de la validation d'une vente, un paiement initial optionnel peut être saisi (de 0 jusqu'au montant total de la vente). Si le montant saisi couvre exactement le total, la vente est immédiatement considérée « Payée ».

### Paiement partiel

Un paiement peut être inférieur au reste à payer : la vente passe alors au statut de paiement « Partiellement payée ». D'autres paiements peuvent être enregistrés ultérieurement (bouton dédié depuis la fiche de détail de la vente), tant que le solde n'est pas atteint. **Un paiement qui dépasserait le reste à payer est refusé** (l'application affiche le montant maximum acceptable).

### Paiement complet

Dès que la somme des paiements atteint le montant total de la vente, le statut de paiement passe à « Payée ».

### Champs d'un paiement

| Champ | Obligatoire ? | Remarques |
|---|---|---|
| Montant | **Oui** | Doit être strictement positif, ne doit pas dépasser le reste à payer. |
| Mode de paiement | Non | Texte libre (exemples suggérés : Espèces, Mobile Money, Virement…), 50 caractères max. |
| Référence | Non | 100 caractères max. |
| Commentaire | Non | 500 caractères max. |

### Historique

La fiche de détail d'une vente affiche l'historique complet des paiements enregistrés (du plus ancien au plus récent).

### Créances

L'écran **Créances** (menu Clients) liste toutes les ventes **validées** avec leur montant total, montant payé, reste à payer et statut de paiement, avec des filtres par client, statut de paiement (Non payée / Partiellement payée / Payée / Toutes) et période. Une vente comptant sans client y apparaît sous la mention « (Vente comptant sans client) ». En filtrant sur un client précis, un résumé agrégé (total des ventes, total payé, reste à payer global pour ce client) est affiché — uniquement calculé sur les ventes validées et non annulées.

### Modes de paiement

Le mode de paiement est un champ **texte libre**, il n'existe pas de liste fermée de modes de paiement imposée par l'application.

### Reçu du paiement

Depuis la fiche de détail d'une vente, il est possible d'exporter en PDF le reçu d'un paiement précis sélectionné dans l'historique (voir chapitre 21 pour la distinction avec le reçu de vente).

### Immuabilité des paiements

**Un paiement enregistré n'est jamais modifiable ni supprimable**, quel que soit le rôle de l'utilisateur — c'est une garantie de traçabilité financière : chaque paiement reste une ligne d'historique définitive. Une éventuelle erreur de saisie ne peut pas être corrigée après coup dans l'application.

---

## 13. Inventaires

Un inventaire permet de comparer le stock théorique (celui enregistré par le système) au stock réellement compté physiquement, et de corriger les écarts constatés.

### Création

Bouton « Nouvel inventaire ». Un inventaire n'a pas de mode « tous les articles automatiquement » : il se construit ligne par ligne, en ajoutant les articles à compter un par un (manuellement ou par scan de code-barres — le scan sert uniquement à sélectionner l'article, jamais à deviner la quantité comptée). Un numéro est généré automatiquement. Un inventaire est toujours créé en statut « Brouillon », sans aucun impact immédiat sur le stock.

### Stock théorique

Pour chaque ligne, le **stock théorique est figé au moment où la ligne est construite** (à la création ou lors d'une modification du brouillon) : il s'agit d'une photographie du stock système à cet instant précis, qui n'est **jamais recalculée automatiquement** ensuite, même si d'autres mouvements de stock surviennent en parallèle.

### Stock compté

Le stock physiquement compté est **toujours une saisie manuelle** de l'utilisateur, article par article — jamais devinée ou pré-remplie automatiquement, y compris lors d'un scan de code-barres (qui ne fait que sélectionner l'article concerné).

### Écart

L'écart (stock compté − stock théorique) est calculé et affiché en permanence pendant la saisie du brouillon, ligne par ligne, ainsi qu'un écart global cumulé. Avant toute validation, un message de confirmation récapitule explicitement chaque ligne avec son stock théorique, son stock compté et son écart.

### Validation

Bouton « Valider », nécessite au moins une ligne. Pour chaque ligne dont l'écart est différent de zéro, un **mouvement de stock de type Ajustement** est généré, appliquant la correction au stock réel de l'article (à l'instant de la validation, pas au stock théorique figé — si le stock a bougé entre-temps, c'est le stock réel courant qui est ajusté). Une ligne à écart nul ne génère aucun mouvement. **Le CMUP n'est jamais recalculé par un ajustement d'inventaire**, que l'écart soit positif ou négatif — seule la quantité change. Si un ajustement ferait passer un stock sous zéro, la validation est refusée. L'inventaire passe alors au statut « Validé ».

Message d'avertissement affiché avant validation : *« Cette action applique définitivement ces écarts au stock (mouvements d'ajustement) et n'est pas réversible — aucune annulation n'est possible. »*

### Règles concernant les inventaires validés — définitif en V1

**Un inventaire validé ne peut jamais être annulé, ni modifié, ni supprimé.** Il s'agit d'une décision métier explicite de cette version : il n'existe volontairement aucune fonctionnalité d'annulation pour les inventaires (contrairement aux Entrées, Sorties et Ventes). Toute correction ultérieure nécessaire doit passer par la création d'un **nouvel** inventaire.

Boutons disponibles selon le statut :
- **Brouillon** : « Modifier » et « Valider » disponibles, « Détails » disponible.
- **Validé** : seul « Détails » (lecture seule) reste disponible.

---

## 14. Mouvements

### Rôle du journal

Le module Mouvements est le **journal central de toute variation de stock**, quelle qu'en soit l'origine (entrée, sortie, vente, ajustement d'inventaire, annulation). C'est une page strictement de consultation : elle ne propose aucun bouton d'action.

### Types de mouvements

Cinq types existent : **Entrée**, **Sortie**, **Vente**, **Ajustement** (généré par une validation d'inventaire), **Annulation** (généré par l'annulation d'une entrée, d'une sortie ou d'une vente validée).

### Colonnes affichées

Date/heure, Article, Type, Quantité, Stock avant, Stock après, Référence de l'opération d'origine, Utilisateur, Commentaire.

### Filtres

Recherche libre (article / utilisateur / commentaire), période (date du / date au), type de mouvement. Un bouton « Réinitialiser les filtres » efface tous les critères. Le tableau nécessite un clic explicite sur « Actualiser » (pas de filtrage en direct pendant la saisie).

### Absence de suppression

**Aucun mouvement ne peut jamais être modifié ou supprimé**, quel que soit le rôle de l'utilisateur — c'est le journal d'audit de référence du stock, immuable par conception.

---

## 15. Rapports

### Rapports disponibles

Neuf rapports existent :

1. **État du stock** — liste complète des articles avec stock actuel/min/max, CMUP, valeur de stock, statut.
2. **Stock faible** — articles dont le stock actuel est ≤ au stock minimum.
3. **Ruptures** — articles à stock nul.
4. **Mouvements** — journal des mouvements de stock (période, article, type).
5. **Entrées** — liste des entrées de stock (période, statut).
6. **Sorties** — liste des sorties de stock (période, motif, statut).
7. **Ventes** — liste des ventes (période, statut), avec chiffre d'affaires agrégé sur les ventes validées.
8. **Inventaires** — liste des inventaires (période, statut), avec écarts positifs/négatifs et quantité totale ajustée.
9. **Valorisation** — valeur du stock (stock actuel × CMUP) par article et total général.

### Filtres

Selon le rapport : recherche texte, catégorie, période, statut, motif, type de mouvement, inclusion des éléments inactifs.

### Export

**Un seul format d'export existe : CSV** (délimiteur `;`, encodage compatible Excel). **[ABSENT EN V1]** Aucun export PDF ou Excel (`.xlsx`) n'existe dans cette version. La consultation des rapports et leur export sont deux permissions séparées : un rôle peut avoir le droit de consulter les rapports sans avoir le droit de les exporter (c'est le cas du rôle Consultation par défaut).

---

## 16. Utilisateurs

### Création

Formulaire : identifiant (obligatoire, unique, 50 caractères max), mot de passe (obligatoire, au moins 8 caractères), rôle (obligatoire), compte actif (case à cocher). Le nouveau compte doit obligatoirement changer son mot de passe à sa première connexion — cette contrainte est automatique, jamais un champ que l'administrateur peut désactiver.

### Activation / désactivation

Aucune suppression de compte utilisateur n'existe : seule l'activation/désactivation est disponible. Un compte désactivé ne peut plus se connecter, mais son historique (ventes, mouvements, actions journalisées) reste intact et consultable.

**Garde-fou « dernier administrateur »** : il est impossible de désactiver le dernier compte Administrateur actif restant, afin de ne jamais bloquer l'accès administratif à l'application.

### Réinitialisation de mot de passe

Un administrateur peut réinitialiser le mot de passe d'un utilisateur. Le nouveau mot de passe doit respecter la même règle (8 caractères minimum), et force à nouveau le changement de mot de passe à la prochaine connexion.

### Rôles

Chaque utilisateur est rattaché à exactement un rôle parmi les quatre rôles existants (voir chapitre 17). Un administrateur ne peut jamais retirer son **propre** rôle Administrateur (même s'il reste d'autres administrateurs) ; un autre administrateur peut le faire, à condition qu'il reste au moins un compte Administrateur actif après l'opération.

### Permissions

Les permissions ne se gèrent pas individuellement par utilisateur : elles sont attachées au **rôle**. Modifier les droits d'un utilisateur consiste donc à lui attribuer un autre rôle (voir chapitre 17).

---

## 17. Rôles et permissions

### Les quatre rôles

StockManager Desktop définit exactement **quatre rôles fixes**, sans possibilité d'en créer, d'en renommer ou d'en supprimer de nouveaux : **Administrateur**, **Gestionnaire de stock**, **Vendeur**, **Consultation**.

| Rôle | Description |
|---|---|
| Administrateur | Accès complet à l'application. |
| Gestionnaire de stock | Gestion du catalogue et des mouvements de stock. |
| Vendeur | Création et validation des ventes. |
| Consultation | Accès en lecture seule aux données autorisées. |

### Ce qui est configurable

Seul l'**ensemble des permissions attribuées à chaque rôle** peut être modifié (bouton « Modifier les permissions » sur la fiche du rôle). Les modifications prennent effet à la prochaine connexion de l'utilisateur concerné (pas en temps réel sur une session déjà ouverte).

Deux garde-fous protègent la configuration :
- Le rôle **Administrateur** ne peut jamais perdre quatre permissions essentielles : consulter/modifier les rôles, consulter/modifier les utilisateurs — cela évite de se retrouver dans une configuration où plus personne ne peut corriger un mauvais réglage RBAC.
- Un rôle qui compte au moins un utilisateur actif ne peut jamais se retrouver **sans aucune permission**.

### Permissions importantes (aperçu par domaine)

Chaque module métier (Articles, Catégories, Fournisseurs, Clients, Motifs de sortie, Entrées, Sorties, Ventes, Paiements, Inventaires, Mouvements, Rapports, Utilisateurs, Rôles, Paramètres, Sauvegardes, Audit, Licence) possède ses propres permissions distinctes (typiquement : Consulter / Créer / Modifier / Activer / Désactiver / Valider / Annuler selon le module). Voir le chapitre « Matrice des rôles » du cahier des charges de référence pour le détail complet.

Points notables par défaut :
- Seul l'Administrateur peut annuler une entrée ou une sortie déjà validée (`STOCK_ENTRY_CANCEL`/`STOCK_EXIT_CANCEL` ne sont pas attribuées au Gestionnaire de stock par défaut).
- Seul l'Administrateur peut annuler une vente validée.
- Les Motifs de sortie sont une exclusivité de l'Administrateur (même leur simple consultation).
- Le Vendeur peut créer/modifier un client à la volée, mais ne peut pas l'activer/désactiver.

### Relation entre permissions utilisateur et fonctionnalités de licence

Certaines permissions sont **doublement conditionnées** : par le rôle de l'utilisateur (RBAC) **et** par l'édition de licence activée. Par exemple, les permissions liées à la création/modification/activation/réinitialisation des comptes utilisateurs nécessitent que la licence active inclue la fonctionnalité « Multi-utilisateur » — même un Administrateur ne peut pas créer de second compte si la licence ne le permet pas. À l'inverse, la simple consultation de la liste des comptes reste toujours possible (pour voir au moins le compte existant), indépendamment de la licence. Les permissions liées à la consultation et à l'activation de la licence elle-même **ne sont jamais soumises à cette double vérification** (sinon il deviendrait impossible d'activer une licence).

---

## 18. Sauvegardes

### Sauvegarde manuelle

Bouton « Sauvegarder maintenant » (module Sauvegardes). Utilise le mécanisme de sauvegarde natif de SQLite (compatible avec une base en cours d'utilisation), puis **vérifie automatiquement l'intégrité** du fichier généré avant de considérer la sauvegarde comme réussie. Le nom du fichier suit le modèle `stockmanager_backup_AAAAMMJJ_HHMMSS.db`.

### Sauvegarde automatique

Une sauvegarde automatique peut être activée dans la configuration (désactivée par défaut), avec une fréquence quotidienne ou hebdomadaire et une heure cible. Deux mécanismes coexistent :
- pendant que l'application est ouverte, une vérification interne toutes les minutes déclenche la sauvegarde si elle est due ;
- un utilitaire externe séparé, destiné à être enregistré dans le Planificateur de tâches Windows par un administrateur système, permet de déclencher la sauvegarde même lorsque l'application est fermée. **[NON VÉRIFIÉ]** L'enregistrement de cette tâche planifiée dans Windows n'est pas automatique — c'est une étape manuelle à réaliser par un administrateur système, non testée sur un poste Windows réel dans le cadre de ce document.

Un nombre de sauvegardes à conserver (rétention) est configurable ; les plus anciennes sont supprimées automatiquement au-delà de cette limite.

### Restauration

Bouton « Restaurer la sauvegarde sélectionnée ». La restauration suit un ordre strict et sécurisé :
1. Vérification d'intégrité du fichier de sauvegarde choisi.
2. Vérification que sa version de schéma correspond à celle de la base actuelle.
3. **Création automatique d'une sauvegarde de sécurité de la base actuelle avant toute écriture** (préfixe dédié, jamais supprimée par la rotation automatique).
4. Remplacement effectif de la base de données.
5. En cas d'échec à cette étape, tentative automatique de restauration de la sauvegarde de sécurité créée à l'étape 3.

Un redémarrage de l'application est nécessaire après une restauration réussie.

### Précautions

- Ne jamais interrompre l'application pendant une opération de sauvegarde ou de restauration.
- La sauvegarde de sécurité automatique créée avant une restauration ne doit jamais être supprimée manuellement tant que la restauration n'est pas confirmée réussie.

### Emplacement

Le dossier de destination des sauvegardes est visible et modifiable directement dans l'écran Sauvegardes (champ « Dossier de destination » avec bouton « Parcourir… »), par défaut un sous-dossier `backups` du dossier de données de l'application.

### Zone dangereuse — réinitialisation des données métier

Réservée à l'Administrateur : permet d'effacer en une seule fois toutes les données métier (articles, catégories, fournisseurs, clients, motifs, entrées, sorties, ventes, paiements, inventaires, mouvements), tout en **préservant** les comptes utilisateurs, rôles, permissions, paramètres, licence et journal d'audit. Une sauvegarde complète est créée et vérifiée automatiquement **avant** toute suppression ; si cette sauvegarde échoue, la réinitialisation est intégralement annulée et rien n'est supprimé.

---

## 19. Licences

### Éditions existantes

Quatre éditions de licence existent : **DEMO**, **STANDARD**, **PROFESSIONAL**, **ENTREPRISE**. Chaque édition déverrouille un ensemble de fonctionnalités croissant (articles, catégories, fournisseurs, entrées/sorties/mouvements de stock dès la DEMO ; ventes, inventaire, rapports à partir de STANDARD ; export de rapports, sauvegardes, audit à partir de PROFESSIONAL ; gestion multi-utilisateur à partir d'ENTREPRISE).

### Expiration

Une licence peut être **permanente** (sans date d'expiration) ou avoir une **date d'expiration**. Une licence expirée bloque à nouveau les fonctionnalités qu'elle déverrouillait.

### Fonctionnalités selon licence

L'accès à chaque fonctionnalité est déterminé par le contenu réel du fichier de licence activé (jamais par un simple nom d'édition codé en dur dans l'interface) : c'est le fichier signé qui porte la liste exacte des fonctionnalités accordées.

### Activation hors ligne

L'activation se fait en important un fichier de licence (`.lic`) fourni par l'éditeur ou l'intégrateur — **aucune connexion Internet n'est nécessaire**, ni pour l'activation, ni pour les vérifications ultérieures (la validité est recalculée par vérification cryptographique à chaque démarrage). Le fichier de licence est protégé par une signature électronique qui garantit son authenticité — un fichier modifié ou falsifié est automatiquement rejeté.

L'écran Licence (menu dédié) affiche l'édition active, sa date d'expiration (ou « Sans expiration »), le nombre maximum d'utilisateurs et de postes autorisés, et propose un bouton « Importer / activer une licence… ».

---

## 20. Paramètres

L'écran Paramètres comporte exactement deux sections :

### Entreprise

- **Nom de l'entreprise** (obligatoire, 150 caractères max)
- **Adresse** (optionnel, 255 caractères max)
- **Téléphone** (optionnel, 30 caractères max)
- **Email** (optionnel, 150 caractères max, doit contenir « @ »)
- **Devise** (obligatoire, choix parmi XOF, XAF, EUR, USD — XOF par défaut)

### Logo

Logo de l'entreprise cliente (distinct du logo/de la marque StockManager elle-même), avec aperçu, bouton de sélection et bouton de suppression. Formats acceptés : PNG, JPG/JPEG, taille maximale 5 Mo, dimensions maximales 4000 × 4000 pixels.

### Autres paramètres

**[ABSENT EN V1]** Aucun autre paramètre applicatif n'est exposé dans cette version (pas de gestion de taxes, de multi-devises simultané, de numérotation personnalisée des documents, etc. — ces sujets ne figurent pas dans le code actuel). La configuration des sauvegardes automatiques (fréquence, rétention, dossier de destination) se trouve dans l'écran Sauvegardes, pas dans Paramètres (voir chapitre 18).

---

## 21. Reçus et impressions

Deux types de documents imprimables existent, bien distincts :

### Reçu de vente

Disponible uniquement pour une vente **validée** (jamais un brouillon, jamais une vente annulée en V1). Reprend l'en-tête entreprise, le numéro/date/vendeur de la vente, le client (le cas échéant), toutes les lignes de vente (article, quantité, prix unitaire, sous-total), le total, et le bloc de paiement (montant payé, reste à payer, statut). Disponible en deux formats : **A4** et **Ticket 80 mm** (format adapté à une imprimante thermique de caisse, hauteur calculée automatiquement selon le contenu). Peut être imprimé directement ou exporté en PDF dans chacun des deux formats.

### Reçu de paiement

Document distinct concernant **un seul paiement précis**, sélectionné dans l'historique des paiements d'une vente. Ne reprend jamais le détail des articles vendus — uniquement la trace du règlement : référence de la vente, montant payé, total payé cumulé après ce paiement, reste à payer, date, utilisateur. Disponible uniquement en export PDF au format **A4** (pas de variante ticket thermique, pas de bouton d'impression directe dédié).

### Distinction essentielle

Le reçu de vente documente **la transaction commerciale complète** (ce qui a été vendu). Le reçu de paiement documente **un encaissement précis** (ce qui a été payé, à un instant donné) — utile notamment en cas de paiements partiels échelonnés dans le temps, pour donner une preuve de règlement sans réimprimer l'intégralité de la facture.

---

## 22. Règles importantes à connaître

- **Pas de stock négatif** : toute opération (sortie, vente, ajustement d'inventaire, annulation) qui ferait passer le stock d'un article sous zéro est automatiquement refusée, quel que soit le rôle de l'utilisateur — sans exception ni contournement possible.
- **Dates futures interdites** : la date d'une entrée, d'une sortie, d'une vente ou d'un inventaire ne peut jamais être postérieure à la date du jour.
- **Opérations validées non supprimables** : une entrée, une sortie ou une vente validée ne peut plus être supprimée — seule son annulation (avec mouvement inverse) est possible. Seule une vente en **brouillon** peut être supprimée physiquement.
- **Mouvements non supprimables** : le journal des mouvements de stock est immuable, aucune ligne n'y est jamais modifiée ni supprimée après création.
- **Paiements immuables** : un paiement enregistré n'est jamais corrigé ni supprimé.
- **Activation/désactivation des référentiels** : Articles, Catégories, Fournisseurs, Clients et Motifs de sortie ne se suppriment jamais physiquement — seule leur désactivation est possible, afin de préserver l'intégrité de tout l'historique qui s'appuie sur eux.
- **Inventaires définitifs** : un inventaire validé ne peut jamais être annulé — c'est le seul document de l'application sans aucune fonctionnalité d'annulation.
- **CMUP recalculé uniquement à l'entrée** : le coût moyen unitaire pondéré n'est recalculé que lors de la validation d'une entrée de stock ; il n'est jamais modifié par une sortie, une vente ou un ajustement d'inventaire.
- **Fonctionnement hors ligne** : StockManager fonctionne intégralement sans connexion Internet, licence comprise.

---

## 23. Sauvegarde et bonnes pratiques utilisateur

- Effectuez une sauvegarde manuelle avant toute opération à fort impact (réinitialisation des données métier, restauration d'une ancienne sauvegarde, montée de version majeure de l'application).
- Activez la sauvegarde automatique et vérifiez régulièrement, dans l'écran Sauvegardes, que la dernière exécution automatique s'est bien déroulée.
- Ne partagez jamais un compte utilisateur entre plusieurs personnes : créez un compte par personne, avec le rôle approprié — cela garantit une traçabilité correcte de qui a fait quoi (journal d'audit, utilisateur associé à chaque mouvement).
- Désactivez immédiatement le compte d'une personne qui quitte l'entreprise, plutôt que de le laisser actif.
- Vérifiez régulièrement l'onglet Stock faible / Ruptures du tableau de bord pour anticiper les réapprovisionnements.
- En cas d'erreur de saisie sur une opération déjà validée, utilisez l'annulation (lorsqu'elle est disponible) plutôt que de tenter de « forcer » une correction ailleurs — cela préserve un historique cohérent et compréhensible.

---

## 24. Dépannage / problèmes fréquents

**« Identifiant ou mot de passe incorrect »** — Message volontairement générique, qu'il s'agisse d'un identifiant inconnu ou d'un mot de passe erroné. Vérifiez la saisie ; contactez un administrateur pour une réinitialisation de mot de passe si nécessaire.

**« Ce compte est désactivé »** — Le compte a été désactivé par un administrateur ; seul un administrateur peut le réactiver.

**Impossible de valider une sortie ou une vente : « le stock deviendrait négatif »** — Le stock disponible est insuffisant pour la quantité demandée. Vérifiez le stock actuel de l'article, ou corrigez la quantité de la ligne concernée.

**Impossible d'enregistrer une opération : « date future »** — La date choisie est postérieure à aujourd'hui ; elle n'est pas autorisée pour une entrée, une sortie, une vente ou un inventaire.

**Le bouton d'une action reste grisé** — Le rôle de l'utilisateur connecté ne dispose probablement pas de la permission nécessaire, ou (selon la fonctionnalité) la licence active ne l'inclut pas. Contactez votre administrateur.

**Impossible d'imprimer un reçu** — Vérifiez qu'une imprimante est bien installée et détectée par Windows ; à défaut, utilisez l'export PDF (A4 ou Ticket 80 mm).

**Un article n'apparaît pas dans la liste de sélection d'une opération** — L'article (ou la catégorie/le fournisseur/le client/le motif associé) est probablement désactivé. Réactivez-le si nécessaire depuis son module de gestion.

**Après une restauration de sauvegarde, l'application se comporte anormalement** — Un redémarrage complet de l'application est nécessaire après toute restauration ; s'il n'a pas été effectué, fermez et relancez StockManager.

**Mot de passe oublié** — Un administrateur doit réinitialiser le mot de passe depuis le module Utilisateurs. **[ABSENT EN V1]** Il n'existe aucune fonctionnalité de réinitialisation en libre-service (pas d'email de récupération) : l'intervention d'un administrateur est obligatoire.

---

## 25. Glossaire

- **CMUP (Coût Moyen Unitaire Pondéré)** : coût de revient moyen d'une unité de stock, recalculé à chaque entrée de stock en pondérant le stock existant et la quantité reçue. Ne change jamais lors d'une sortie, d'une vente ou d'un ajustement d'inventaire.
- **Stock théorique** : quantité de stock enregistrée dans le système au moment de la préparation d'un inventaire (photographie figée, jamais recalculée automatiquement après coup).
- **Stock compté** : quantité réellement dénombrée physiquement lors d'un inventaire, saisie manuellement.
- **Écart** : différence entre le stock compté et le stock théorique (positif = surplus constaté, négatif = manquant constaté).
- **Mouvement (de stock)** : toute variation enregistrée du stock d'un article (entrée, sortie, vente, ajustement, annulation), avec la quantité, le stock avant et après, et l'opération d'origine.
- **Créance** : montant restant dû par un client sur une vente validée dont le paiement n'est pas (ou pas totalement) encaissé.
- **Brouillon** : état initial d'un document (entrée, sortie, vente, inventaire) avant sa validation — modifiable librement, sans aucun impact sur le stock.
- **Validation** : action qui rend un document définitif et déclenche son impact réel sur le stock (création de mouvements).
- **Annulation** : action inverse d'une validation, applicable uniquement à un document déjà validé (sauf inventaire, qui ne s'annule jamais), générant un mouvement inverse sans supprimer le document original.
- **Vente comptant** : vente sans client identifié.
- **RBAC** : contrôle d'accès basé sur les rôles — chaque utilisateur a un rôle, chaque rôle a un ensemble de permissions.
- **Licence** : fichier signé électroniquement qui autorise l'usage de certaines fonctionnalités de l'application, pour une édition et une durée données.
