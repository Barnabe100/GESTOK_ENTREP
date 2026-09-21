# Cahier des charges de référence — StockManager Desktop V1.0 et base de conception StockManager Web

**Éditeur :** TechNova
**Produit :** StockManager Desktop, version 1.0.0
**Nature du document :** document technique et fonctionnel de référence, rédigé exclusivement à partir de l'audit du code source actuel. Il sépare strictement **(A) ce qui existe réellement dans StockManager Desktop V1** et **(B) ce qui pourra être adapté ou construit dans une future version Web** — aucune fonctionnalité future n'est présentée comme déjà existante. Aucune capture d'écran n'est incluse.

> **Convention** : chaque section commence, lorsque pertinent, par un bloc **A. CE QUI EXISTE** (Desktop V1, vérifié dans le code, citations `fichier:ligne`) puis un bloc **B. ÉVOLUTION POSSIBLE (WEB)** (propositions, clairement non implémentées). Les informations non vérifiables sont marquées **[NON VÉRIFIÉ]** ; les fonctionnalités absentes sont marquées **[ABSENT EN V1]**.

---

## Table des matières

1. [Présentation générale](#1-présentation-générale)
2. [Contexte et objectifs](#2-contexte-et-objectifs)
3. [Vision produit](#3-vision-produit)
4. [Périmètre fonctionnel Desktop V1](#4-périmètre-fonctionnel-desktop-v1)
5. [Périmètre hors scope](#5-périmètre-hors-scope)
6. [Profils utilisateurs](#6-profils-utilisateurs)
7. [Gestion des rôles et permissions](#7-gestion-des-rôles-et-permissions)
8. [Gestion des licences et éditions](#8-gestion-des-licences-et-éditions)
9. [Gestion des articles](#9-gestion-des-articles)
10. [Catégories](#10-catégories)
11. [Fournisseurs](#11-fournisseurs)
12. [Clients](#12-clients)
13. [Entrées](#13-entrées)
14. [Sorties](#14-sorties)
15. [Ventes](#15-ventes)
16. [Paiements](#16-paiements)
17. [Créances](#17-créances)
18. [Inventaires](#18-inventaires)
19. [Mouvements](#19-mouvements)
20. [Dashboard](#20-dashboard)
21. [Rapports](#21-rapports)
22. [Sauvegardes/restauration](#22-sauvegardesrestauration)
23. [Audit](#23-audit)
24. [Paramètres](#24-paramètres)
25. [Reçus et documents](#25-reçus-et-documents)
26. [Règles métier détaillées](#26-règles-métier-détaillées)
27. [Workflows métier](#27-workflows-métier)
28. [Règles de validation](#28-règles-de-validation)
29. [Gestion des erreurs](#29-gestion-des-erreurs)
30. [Sécurité](#30-sécurité)
31. [Traçabilité](#31-traçabilité)
32. [Architecture actuelle Desktop](#32-architecture-actuelle-desktop)
33. [Modèle de données actuel](#33-modèle-de-données-actuel)
34. [Contraintes SQLite](#34-contraintes-sqlite)
35. [Packaging et déploiement Windows](#35-packaging-et-déploiement-windows)
36. [Fonctionnement hors ligne](#36-fonctionnement-hors-ligne)
37. [Évolution vers StockManager Web](#37-évolution-vers-stockmanager-web)
38. [Modèle de données — détail par entité et correspondance Web](#38-modèle-de-données--détail-par-entité-et-correspondance-web)
39. [Matrice des fonctionnalités](#39-matrice-des-fonctionnalités)
40. [Matrice des rôles](#40-matrice-des-rôles)
41. [Règles métier — récapitulatif vérifié](#41-règles-métier--récapitulatif-vérifié)

---

## 1. Présentation générale

StockManager Desktop est une application de gestion de stock développée par **TechNova**, distribuée sous forme d'exécutable Windows autonome, fonctionnant intégralement en local sur un poste de travail unique, sans dépendance réseau. Pile technique : **Python ≥ 3.11, PySide6 6.7.2 (interface graphique Qt), SQLAlchemy 2.0.35 (ORM), SQLite (base de données), Alembic 1.13.2 (migrations de schéma), argon2-cffi (hachage de mots de passe), cryptography/Ed25519 (signature des licences), PyInstaller (empaquetage), Inno Setup (installateur Windows)**. (`requirements.txt`, `stockmanager.spec`, `packaging/inno_setup.iss`)

## 2. Contexte et objectifs

### A. CE QUI EXISTE
Objectifs vérifiés dans le comportement du code : centraliser les données de stock d'une PME sur un poste unique ; connaître en temps réel le stock disponible (`Article.stock_actuel`, dénormalisé et maintenu exclusivement par `StockService`) ; tracer entrées/sorties/ventes/inventaires via un journal de mouvements immuable ; empêcher tout stock négatif ; contrôler les accès par rôle (RBAC à 4 rôles fixes) ; produire des rapports et un export CSV ; sauvegarder/restaurer les données ; gérer des licences commerciales par édition ; fonctionner sans connexion Internet.

### B. ÉVOLUTION POSSIBLE (WEB)
Objectifs additionnels envisageables pour une version Web (à valider avec le métier) : usage simultané par plusieurs postes/utilisateurs réels, centralisation multi-boutiques, accès distant, notifications, tableau de bord temps réel partagé. Voir §37.

## 3. Vision produit

**Desktop V1** : un outil de gestion de stock fiable, simple, autonome, pour une entreprise mono-site utilisant un seul ordinateur.
**Web (vision, non implémentée)** : une évolution qui conserverait l'intégrité des règles métier déjà validées et éprouvées en Desktop (aucun stock négatif, immuabilité des documents validés, traçabilité complète), tout en ouvrant l'accès à plusieurs postes, éventuellement plusieurs boutiques, avec une architecture technique différente (voir §37 — **la version Web ne doit pas être une simple copie technique de PySide6 + SQLite**).

## 4. Périmètre fonctionnel Desktop V1

### A. CE QUI EXISTE
Modules implémentés et fonctionnels : Authentification, Tableau de bord, Articles, Catégories, Fournisseurs, Clients, Motifs de sortie, Entrées de stock, Sorties de stock, Ventes, Paiements, Créances, Inventaires, Mouvements de stock, Rapports (9 rapports + export CSV), Utilisateurs, Rôles & permissions, Sauvegardes/restauration, Réinitialisation des données métier, Journal d'audit, Paramètres entreprise, Licences, Reçus (impression/export PDF A4 et ticket 80 mm).

## 5. Périmètre hors scope

### A. CE QUI EXISTE (absences confirmées, volontaires ou non, dans Desktop V1)
- **[ABSENT EN V1]** Aucune API réseau, aucun serveur, aucune synchronisation entre postes.
- **[ABSENT EN V1]** Aucun export PDF/Excel pour les rapports (CSV uniquement).
- **[ABSENT EN V1]** Aucune notification (email, SMS, push).
- **[ABSENT EN V1]** Aucune gestion multi-boutiques / multi-entrepôts.
- **[ABSENT EN V1]** Aucun verrouillage de compte après échecs de connexion répétés, aucune règle de complexité de mot de passe au-delà d'une longueur minimale de 8 caractères.
- **[ABSENT EN V1]** Aucune annulation d'inventaire validé, aucune modification/suppression d'un paiement ou d'un mouvement de stock.
- **[ABSENT EN V1]** Aucun mécanisme de récupération de mot de passe en libre-service (seule la réinitialisation par un administrateur existe).
- Le §25 du document de spécification antérieur (`Cahier_des_charges_final_StockManager.md`) évoquait déjà, comme perspectives volontairement hors périmètre : clients avancés, multi-entrepôt, transferts, API, synchronisation, version web/mobile — cohérent avec l'absence totale de code réseau constatée.

## 6. Profils utilisateurs

### A. CE QUI EXISTE
Quatre profils fixes correspondant aux quatre rôles système : Administrateur, Gestionnaire de stock, Vendeur, Consultation. **Un utilisateur = un compte = un seul mot de passe, mais un ou plusieurs rôles** (relation many-to-many `User <-> Role` via la table `user_roles`, migration `0011_user_roles_many_to_many`). Un utilisateur peut posséder plusieurs rôles. Les permissions effectives correspondent à l'union des permissions de tous ses rôles. Exemple : Jean cumule Vendeur + Gestionnaire de stock — une seule connexion, un seul mot de passe, les permissions des deux rôles cumulées. Voir §7 et §40 pour le détail complet des permissions.

## 7. Gestion des rôles et permissions

### A. CE QUI EXISTE
- 4 rôles fixes, **sans création/suppression/renommage possible** — docstring `app/services/roles/role_service.py:1-16` : *« Ne crée, ne renomme, ne supprime et ne désactive aucun rôle — ces opérations sont explicitement hors périmètre. »*
- Seul l'ensemble des permissions d'un rôle est modifiable, via `RoleService.update_role_permissions()` (`app/services/roles/role_service.py:80-141`), avec deux garde-fous :
  1. Le rôle **Administrateur** ne peut jamais perdre `ROLE_VIEW`, `ROLE_UPDATE`, `USER_VIEW`, `USER_UPDATE` (`_PROTECTED_ADMIN_PERMISSIONS`, `role_service.py:36-39,107-113`).
  2. Un rôle avec au moins un utilisateur actif ne peut jamais se retrouver sans aucune permission (`role_service.py:115-120`).
- 65 permissions déclarées au total (`app/db/seed.py:25-95`, vérifié par comptage exhaustif de la liste), organisées par module. Les modifications de permissions prennent effet à la prochaine connexion de l'utilisateur (`app/views/pages/roles_page.py:49`), pas en temps réel.
- Vérification RBAC centralisée : `PermissionService.require_permission()`/`has_permission()` (`app/services/auth/permission_service.py`) — point d'application unique, jamais contourné côté UI (masquage de bouton = confort visuel uniquement, jamais la garantie de sécurité réelle).
- **Multi-rôles** (relation many-to-many `User <-> Role` via `user_roles`, migration `0011_user_roles_many_to_many`) : un utilisateur peut posséder plusieurs rôles. Les permissions effectives correspondent à l'union des permissions de tous ses rôles, calculée côté service à la connexion (`AuthService.login`, `app/services/auth/auth_service.py`) et stockée dans `CurrentUser.permissions` — jamais recalculée uniquement côté interface. Exemple : Jean cumule les rôles Vendeur et Gestionnaire de stock — une seule connexion, un seul mot de passe, les permissions des deux rôles cumulées et dédupliquées.
  - Contraintes : au moins un rôle obligatoire (impossible d'enregistrer un utilisateur sans rôle), un même rôle ne peut pas être attribué deux fois au même utilisateur (`UserService._validate_role_ids`).
  - Le rôle Administrateur ne bénéficie d'aucun traitement spécial du seul fait qu'un compte cumule plusieurs rôles : les garde-fous « dernier administrateur actif » (`UserService.set_active`/`update_user`) portent sur l'ensemble réel des rôles détenus (`User.roles`), jamais sur un rôle « principal ».
  - Colonne historique `users.role_id` **conservée** (jamais supprimée) comme pointeur de compatibilité non-autoritaire, renseigné avec le premier rôle attribué — jamais utilisé pour le calcul des permissions ou de l'appartenance réelle aux rôles, qui repose exclusivement sur `user_roles`/`User.roles`.
  - `max_users` de la licence active compte les **comptes actifs**, jamais les rôles détenus : un utilisateur ayant plusieurs rôles ne consomme qu'une seule place (ex. Jean = Vendeur + Gestionnaire de stock, Paul = Vendeur, Marie = Consultation → 3 comptes actifs, jamais 4).
  - La gestion multi-utilisateurs/multi-rôles (création, modification, activation, réinitialisation de mot de passe) reste soumise, comme avant ce lot, au double contrôle RBAC + licence : elle nécessite que la licence active inclue `MULTI_USER` (non incluse par défaut dans DEMO/STANDARD, incluse par défaut dans ENTREPRISE — voir §8), via le `FeatureGate` existant, inchangé par ce lot.

### B. ÉVOLUTION POSSIBLE (WEB)
Le modèle RBAC à 4 rôles fixes est robuste et pourrait être conservé tel quel en Web. Une évolution possible : permissions personnalisées par rôle **créé par le client** (au-delà des 4 rôles système), ou rôles par boutique/site dans un contexte multi-boutiques — à valider avec le métier, ceci élargirait significativement le périmètre RBAC actuel.

## 8. Gestion des licences et éditions

### A. CE QUI EXISTE
- 4 éditions codées : `DEMO`, `STANDARD`, `PROFESSIONAL`, `ENTREPRISE` (`app/models/enums.py:50-54`).
- Fonctionnalités par édition par défaut (`app/services/licensing/license_payload.py:53-70`) : DEMO = catalogue + mouvements de base ; STANDARD = + ventes, inventaire, rapports ; PROFESSIONAL = + export de rapports, sauvegardes, audit ; ENTREPRISE = + multi-utilisateur.
- Activation par fichier `.lic` (JSON signé Ed25519), **entièrement hors ligne**, vérifié par clé publique embarquée côté client (`app/services/licensing/license_crypto.py`, `public_key.py`). La clé privée ne quitte jamais l'outil de génération (`license_generator/`, jamais embarqué dans le client livré).
- État de licence toujours **recalculé** par re-vérification cryptographique complète à chaque évaluation (`VALID, EXPIRED, MISSING, INVALID, CORRUPTED` — `app/services/licensing/license_service.py:47-59`), jamais simplement lu depuis un champ stocké en base.
- Expiration optionnelle (licence permanente possible).
- Double vérification RBAC + licence sur certaines permissions via `PERMISSION_TO_FEATURE` (`app/services/licensing/permission_map.py:41-98`) — ex. `USER_CREATE` nécessite la fonctionnalité `MULTI_USER`, indépendamment du rôle de l'acteur.
- Limite `max_users`/`max_devices` portée par la licence ; `max_users` est réellement appliquée (`LicenseService.check_can_activate_user`) ; `max_devices` est **informationnelle uniquement** en V1 (pas de serveur central pour la faire respecter à travers plusieurs postes).

### B. ÉVOLUTION POSSIBLE (WEB)
Une architecture SaaS nécessiterait une **gestion centralisée des licences** côté serveur (activation, renouvellement, révocation à distance, application réelle de `max_devices`/`max_postes` à travers une flotte de postes) — voir §37.10.

## 9. Gestion des articles

### A. CE QUI EXISTE
Champs : référence (unique, 50c), désignation (255c), catégorie (obligatoire, FK active), fournisseur principal (optionnel, FK active), unité (20c), prix d'achat (≥0), prix de vente (≥0), CMUP (piloté par le système, jamais saisi), stock actuel (piloté par le système), stock minimum (≥0), stock maximum (optionnel, ≥ stock min), stock initial (création uniquement, traité comme un mouvement d'ajustement traçable, jamais une écriture brute), emplacement (100c), code-barres (50c, unique parmi les articles **actifs** uniquement), description (1000c). Aucune suppression physique — activation/désactivation uniquement (`app/services/articles/article_service.py`).

## 10. Catégories

### A. CE QUI EXISTE
Champ unique : nom (100c, unique). Activation/désactivation, aucune suppression physique (`app/services/categories/category_service.py`).

## 11. Fournisseurs

### A. CE QUI EXISTE
Nom (150c, **sans contrainte d'unicité** — décision explicite), contact, téléphone, email (validé « @ » si renseigné), adresse, ville, pays, observations. Activation/désactivation, aucune suppression physique (`app/services/suppliers/supplier_service.py`).

## 12. Clients

### A. CE QUI EXISTE
Nom (150c, sans unicité), téléphone, email (validé), adresse, observations. Créable à la volée depuis le formulaire de vente. Activation/désactivation, aucune suppression physique (`app/services/clients/client_service.py`).

## 13. Entrées

### A. CE QUI EXISTE
Cycle `BROUILLON → VALIDEE → (ANNULEE)`. Fournisseur obligatoire actif, date (jamais future), référence document, commentaire, lignes (article, quantité >0, prix unitaire ≥0). Validation : génère un mouvement `ENTREE` par ligne et **recalcule le CMUP** (seule opération à le faire). Annulation (validée uniquement) : mouvement `ANNULATION` inverse, sans recalcul rétroactif du CMUP (`app/services/entries/entry_service.py`). **Motif d'annulation obligatoire** depuis ce lot : `cancel_entry(entree_id, motif)` refuse l'annulation si `motif` est `None`, vide, uniquement des espaces, ou < 5 caractères après trim ; conservé sur `Entree.annulation_motif`, jamais modifié ensuite.

## 14. Sorties

### A. CE QUI EXISTE
Cycle identique aux Entrées. Motif de sortie obligatoire actif, bénéficiaire, référence, commentaire, lignes (article, quantité >0 ; **aucun coût saisi manuellement** — toujours le CMUP courant, recapturé à la validation). Validation : mouvement `SORTIE` (quantité négative), refus automatique si stock insuffisant, CMUP jamais modifié. Annulation : mouvement `ANNULATION` inverse (`app/services/exits/exit_service.py`). **Motif d'annulation obligatoire** depuis ce lot, même règle que pour les Entrées : `cancel_exit(sortie_id, motif)`, conservé sur `Sortie.annulation_motif`. (À ne pas confondre avec le motif de *sortie* lui-même — `Sortie.motif_id`/`ExitReason` — qui qualifie la nature de la sortie, pas son annulation.)

> **Point à signaler — décision future, non résolue ici** : contrairement aux Ventes (§15), ni les Entrées ni les Sorties ne proposent de suppression physique de leur brouillon (aucune méthode `delete_` dans `entry_service.py`/`exit_service.py`, aucun bouton « Supprimer » sur `entries_page.py`/`exits_page.py` — seul « Annuler », réservé aux documents déjà validés). Un brouillon d'Entrée ou de Sortie ne peut donc être qu'édité ou laissé tel quel, jamais retiré. Cette asymétrie avec les Ventes est vérifiée dans le code mais **son caractère volontaire ou non n'est pas tranché par ce document** — à valider avec le métier avant la conception Web (éventuellement en alignant Entrées/Sorties sur le comportement des Ventes, ou en le justifiant explicitement comme une différence assumée).

## 15. Ventes

### A. CE QUI EXISTE
Cycle `BROUILLON → VALIDEE → (ANNULEE)`. Client **optionnel** (`client_id` nullable — vente comptant). Lignes : article, quantité >0, prix unitaire ≥0 (pré-rempli au prix de vente courant, librement modifiable, jamais recalculé). Validation : mouvement `VENTE` par ligne, refus si stock insuffisant, paiement initial optionnel possible. Seul document supprimable physiquement (brouillon uniquement). Annulation (validée uniquement) : mouvement `ANNULATION` inverse ; les paiements déjà enregistrés ne sont jamais modifiés/remboursés automatiquement (`app/services/sales/sale_service.py`). **Motif d'annulation obligatoire** depuis ce lot, même règle que pour les Entrées/Sorties : `cancel_sale(sale_id, motif)`, conservé sur `Vente.annulation_motif`.

## 16. Paiements

### A. CE QUI EXISTE
Rattachés à une vente **validée** uniquement. Montant (>0, ≤ reste à payer — surpaiement bloqué), mode de paiement (texte libre, 50c), référence (100c), commentaire (500c). Statut de paiement dérivé automatiquement : `NON_PAYEE` / `PARTIELLEMENT_PAYEE` / `PAYEE`. **Immuables** : aucune méthode de modification ou de suppression n'existe (`app/models/payment.py`, `app/services/sales/sale_service.py:record_payment`).

## 17. Créances

### A. CE QUI EXISTE
Aucun service dédié : l'écran Créances réutilise intégralement `SaleService.list_sales` filtré sur les ventes validées, avec filtres client/statut de paiement/période. Reste à payer = `max(total − montant_payé, 0)`. Résumé agrégé par client disponible (`app/views/pages/receivables_page.py`, `app/services/sales/sale_service.py:get_client_receivable_summary`).

## 18. Inventaires

### A. CE QUI EXISTE
Cycle **réduit** à `BROUILLON → VALIDE` (pas d'état Annulée). Construction ligne par ligne (pas de mode « tous les articles »). Stock théorique figé à la construction de la ligne (jamais recalculé). Stock compté toujours saisi manuellement. Écart affiché en continu. Validation : génère un mouvement `AJUSTEMENT` par ligne à écart non nul, sur le stock réel courant (pas le stock théorique figé), sans jamais recalculer le CMUP. **Aucune annulation possible après validation** — décision métier explicite, documentée dans le code (`app/services/inventory/inventory_service.py:36-39`).

## 19. Mouvements

### A. CE QUI EXISTE
Journal central, immuable, append-only. 5 types : `ENTREE, SORTIE, VENTE, AJUSTEMENT, ANNULATION` (`app/models/enums.py:37-42`). Page de consultation uniquement (aucune action), avec filtres recherche/période/type (`app/views/pages/mouvements_page.py`, `app/repositories/mouvement_repository.py`).

## 20. Dashboard

### A. CE QUI EXISTE
Strictement lecture seule. Période sélectionnable (par défaut le mois courant). KPI (articles actifs, valeur du stock, stock faible, ruptures, CA période, quantité en stock, entrées/sorties/ventes/inventaires validés sur la période). Graphiques (évolution des ventes avec granularité automatique jour/semaine/mois, répartition des mouvements par type, valeur du stock par catégorie). Activité récente **limitée à 15 lignes** (`DEFAULT_RECENT_ACTIVITY_LIMIT = 15`, `app/services/dashboard/dashboard_service.py:45`). Boutons de navigation directe vers les modules détaillés (`app/services/dashboard/dashboard_service.py`, `app/views/pages/dashboard_page.py`).

## 21. Rapports

### A. CE QUI EXISTE
9 rapports (État du stock, Stock faible, Ruptures, Mouvements, Entrées, Sorties, Ventes, Inventaires, Valorisation), tous strictement lecture seule, jamais via les services métier (accès direct aux repositories pour ne dépendre que de `REPORT_VIEW`). Export **CSV uniquement**, permission distincte `REPORT_EXPORT` (`app/services/reports/report_service.py`, `app/utils/csv_export.py`). **[ABSENT EN V1]** aucun export PDF/Excel.

## 22. Sauvegardes/restauration

### A. CE QUI EXISTE
Sauvegarde manuelle et automatique (planifiée quotidienne/hebdomadaire, désactivée par défaut), via l'API de sauvegarde native SQLite (jamais une simple copie de fichier), avec vérification d'intégrité systématique. Rétention configurable (rotation automatique). Deux déclencheurs pour l'automatique : minuteur interne (app ouverte) et utilitaire CLI externe (`app/backup_cli.py`) destiné au Planificateur de tâches Windows, **enregistrement manuel non automatisé**. Restauration : vérification intégrité + version de schéma → sauvegarde de sécurité automatique de l'état courant → remplacement → tentative de récupération automatique en cas d'échec. Réinitialisation des données métier : sauvegarde préalable obligatoire et vérifiée, sinon annulation totale ; préserve utilisateurs/rôles/permissions/paramètres/licence/audit (`app/services/backups/`, `app/services/system/data_reset_service.py`).

## 23. Audit

### A. CE QUI EXISTE
Table `audit_logs`, rétention **illimitée** (aucune purge automatique — `app/models/audit.py:14`). Enregistre notamment : connexions/déconnexions, changements de mot de passe, activation de licence, opérations de sauvegarde/restauration, réinitialisation des données métier, modifications de paramètres, suppression de vente brouillon, etc. Page de consultation dédiée avec filtres (recherche, période, entité), permission `AUDIT_VIEW` (`app/services/audit/`, `app/views/pages/audit_page.py`).

## 24. Paramètres

### A. CE QUI EXISTE
Deux groupes uniquement : Entreprise (nom obligatoire, adresse, téléphone, email, devise parmi XOF/XAF/EUR/USD) et Logo entreprise (PNG/JPG, ≤5 Mo, ≤4000×4000px). **[ABSENT EN V1]** aucun autre paramètre applicatif (`app/services/settings/company_settings_service.py`).

## 25. Reçus et documents

### A. CE QUI EXISTE
Deux documents distincts : reçu de vente (vente validée uniquement, formats A4 et Ticket 80mm, impression directe ou export PDF) et reçu de paiement (un paiement précis, sans lignes d'articles, A4 PDF uniquement, pas d'impression directe dédiée) (`app/services/documents/`).

## 26. Règles métier détaillées

Voir la synthèse exhaustive et vérifiée au §41.

## 27. Workflows métier

### A. CE QUI EXISTE
Tous les documents opérationnels (Entrée, Sortie, Vente) suivent le même cycle `BROUILLON → VALIDEE → (ANNULEE)`. L'Inventaire suit un cycle réduit `BROUILLON → VALIDE` (sans annulation). Un brouillon n'a jamais d'impact sur le stock ; seule la validation déclenche la création de mouvements via `StockService.apply_movement`, point de passage unique et obligatoire pour toute variation de stock (`app/services/stock/stock_service.py`). L'annulation d'un document validé (Entrée/Sortie/Vente) génère systématiquement un mouvement `ANNULATION` inverse référençant le mouvement d'origine (`mouvement_origine_id`), sans jamais supprimer ni modifier le document original.

## 28. Règles de validation

### A. CE QUI EXISTE
- Quantités : toujours strictement positives sur les lignes de document (`Numeric(14,3)`, contraintes `CHECK > 0` au niveau base de données sur Entrée/Sortie/Vente).
- Montants/prix : toujours ≥ 0 (`Numeric(14,2)`, contraintes `CHECK >= 0`).
- Dates d'opération : jamais dans le futur (`app/utils/dates.py::validate_not_future_date`, appliqué dans Entrées, Sorties, Ventes, Inventaires).
- Textes : validation de longueur maximale systématique, alignée sur les colonnes SQL, avec message métier explicite plutôt qu'une erreur SQL brute en cas de dépassement.
- Emails (Fournisseurs, Clients, Paramètres entreprise) : présence du caractère « @ » uniquement — pas de validation par expression régulière complète.

## 29. Gestion des erreurs

### A. CE QUI EXISTE
Hiérarchie d'exceptions métier dédiée (`app/utils/exceptions.py`, non lue intégralement dans cet audit mais dont l'usage est confirmé par toutes les recherches ci-dessus) : `ValidationError` (règle métier violée — ex. stock négatif, date future, dépassement de longueur), `ConflictError` (état incompatible avec l'action demandée — ex. tenter de valider un document déjà validé), `NotFoundError` (référence inexistante), `PermissionDeniedError`/`LicenseError` (accès refusé). Chaque erreur porte un message français explicite destiné à être affiché directement à l'utilisateur. Toute opération multi-étapes (validation d'un document avec plusieurs lignes, restauration de sauvegarde, réinitialisation des données) s'exécute dans une transaction unique (`session_scope()`) : en cas d'erreur sur une seule ligne/étape, l'ensemble de l'opération est annulé (tout ou rien).

## 30. Sécurité

### A. CE QUI EXISTE
- Mots de passe hachés en **Argon2** (`app/security/password_hashing.py`), jamais stockés en clair.
- Politique de mot de passe : longueur minimale de **8 caractères**. **[ABSENT EN V1]** aucune règle de complexité (majuscule/chiffre/caractère spécial), **[ABSENT EN V1]** aucun verrouillage de compte après échecs répétés.
- Message de connexion volontairement générique en cas d'échec (ne révèle jamais si l'identifiant existe).
- Changement de mot de passe obligatoire (`must_change_password`) forcé à la création d'un compte et après une réinitialisation par un administrateur ; l'ancien mot de passe est toujours exigé pour le changer, y compris lors du changement forcé.
- RBAC appliqué exclusivement côté service (jamais uniquement côté interface).
- Licences signées Ed25519, clé privée jamais embarquée côté client.
- Aucune donnée transmise sur le réseau (application 100% locale).

## 31. Traçabilité

### A. CE QUI EXISTE
Trois niveaux de traçabilité complémentaires et tous immuables : (1) le journal des mouvements de stock (`MouvementStock`, toute variation de quantité) ; (2) le journal des paiements (`Paiement`, tout encaissement) ; (3) le journal d'audit (`AuditLog`, actions sensibles : connexion, sécurité, sauvegarde, paramétrage, licence). Chacun de ces trois journaux est en écriture seule (append-only) — confirmé par l'absence de toute méthode `update`/`delete` sur leurs repositories respectifs.

## 32. Architecture actuelle Desktop

### A. CE QUI EXISTE
Architecture en couches strictes : **Vues** (PySide6, `app/views/`) → **Services** (logique métier, permissions, audit, `app/services/`) → **Repositories** (accès aux données via SQLAlchemy, `app/repositories/`) → **Modèles** (ORM, `app/models/`), avec une base de données SQLite locale. `ServiceRegistry` (`app/services/registry.py`) centralise la construction de tous les services, partagés par session applicative. `session_scope()` (`app/db/session.py`) est le point d'entrée transactionnel unique — commit/rollback/fermeture garantis pour toute opération métier. Le schéma de base de données est exclusivement géré par Alembic (`command.upgrade(config, "head")`), jamais par une création directe des tables, afin de permettre l'évolution du schéma sans perte de données chez les clients déjà installés.

## 33. Modèle de données actuel

Voir le détail complet entité par entité au §38.

## 34. Contraintes SQLite

### A. CE QUI EXISTE
- Clés étrangères **activées explicitement** à chaque connexion (`PRAGMA foreign_keys=ON`) — SQLite ne les active pas par défaut.
- Tous les enums métier sont stockés comme **texte** (`native_enum=False`), jamais comme un type enum natif de la base — SQLite n'en propose pas nativement, et cela facilite l'évolution du schéma.
- Aucun validateur Python au niveau des modèles (`@validates`) — toute l'intégrité est portée par des `CheckConstraint`, contraintes d'unicité/index et clés étrangères SQL, plus la couche service.
- Un index unique **partiel** existe (`articles.code_barres`, restreint aux lignes `statut = 'ACTIF'`) — une fonctionnalité SQLite spécifique (`sqlite_where`), à reproduire différemment sur un moteur qui ne la supporterait pas nativement de la même façon (PostgreSQL le supporte aussi via `WHERE` sur un index, donc ce point est directement portable).
- Les montants sont stockés en `Numeric(14,2)` et les quantités en `Numeric(14,3)` (jamais en flottant), avec arrondi `ROUND_HALF_UP` centralisé (`app/utils/money.py::round_money`) — SQLite ne dispose pas nativement d'un type `DECIMAL`, mais SQLAlchemy émule ce comportement via Python `Decimal` de bout en bout.
- Sauvegarde/restauration s'appuient sur l'**API de sauvegarde native SQLite** (`sqlite3.Connection.backup()`), spécifique à ce moteur.

### B. ÉVOLUTION POSSIBLE (WEB)
Un passage à PostgreSQL (§37.9) est directement compatible avec le modèle de données actuel (types numériques précis, contraintes CHECK, unicité partielle, clés étrangères) — aucune de ces contraintes n'est une impasse pour PostgreSQL. Le mécanisme de sauvegarde SQLite devra être remplacé par l'outillage natif du SGBD cible (ex. `pg_dump`/`pg_basebackup`, ou une solution managée du fournisseur cloud).

## 35. Packaging et déploiement Windows

### A. CE QUI EXISTE
Empaquetage **PyInstaller en mode onedir** (jamais onefile — démarrage plus rapide, diagnostic plus simple, moins de faux positifs antivirus), embarquant `alembic.ini`, les migrations et les ressources graphiques. Installateur **Inno Setup**, sans droits administrateur requis (installation par utilisateur), ne supprimant jamais les données lors d'une désinstallation. Version unique centralisée dans `app/version.py` (`APP_NAME = "StockManager Desktop"`, `PUBLISHER_NAME = "TechNova"`, `__version__ = "1.0.0"`). **[NON VÉRIFIÉ]** ni le build PyInstaller Windows, ni l'installateur Inno Setup n'ont été réellement compilés/testés sur un poste Windows au moment de cet audit (l'environnement de développement est Linux) — les fichiers de configuration sont présents et revus, mais non exécutés en conditions réelles.

## 36. Fonctionnement hors ligne

### A. CE QUI EXISTE
Confirmé par l'absence totale, dans tout le code de `app/`, de bibliothèque ou d'appel réseau (aucune trace de `requests`, `urllib`, `httpx`, `socket`, etc.). Aucune fonctionnalité — y compris l'activation de licence — ne nécessite de connexion Internet.

---

# 37. Évolution vers StockManager Web

> **Rappel du principe directeur** : la version Web ne doit pas être une simple transposition technique de PySide6 + SQLite. Les **règles métier** documentées dans ce cahier des charges (aucun stock négatif, CMUP recalculé uniquement à l'entrée, immuabilité des mouvements/paiements, workflow Brouillon→Validé→Annulé, inventaire définitif, dates non-futures, etc.) doivent être **conservées à l'identique** ; l'**architecture technique**, elle, peut et doit être repensée pour un contexte multi-utilisateur et multi-poste réel.

## 37.1 Fonctionnalités à conserver telles quelles

- L'intégralité des règles métier du §41 (aucune exception connue à faire évoluer sans décision explicite).
- Le modèle RBAC à rôles avec permissions granulaires par module et par action (VIEW/CREATE/UPDATE/ACTIVATE/VALIDATE/CANCEL) — le principe reste valable en multi-utilisateur, seul son mécanisme d'application change (voir 37.3).
- Le principe de journal immuable pour les mouvements de stock, les paiements et l'audit.
- Le cycle de vie Brouillon → Validé → (Annulé), et son absence volontaire pour les inventaires.
- La distinction reçu de vente / reçu de paiement.
- La séparation entre édition de licence et permission RBAC (double contrôle).
- L'utilisation de types numériques exacts (`Decimal`) pour montants et quantités, avec arrondi `ROUND_HALF_UP` centralisé.

## 37.2 Fonctionnalités à adapter

| Sujet | Desktop V1 (actuel) | Adaptation envisagée pour le Web |
|---|---|---|
| Authentification | Session locale en mémoire de process, un seul utilisateur connecté à la fois par poste | Authentification Web par jeton (session serveur ou JWT), plusieurs sessions simultanées par utilisateur et par poste |
| Licence | Fichier `.lic` signé importé manuellement, vérifié localement | Gestion centralisée côté serveur (voir 37.10), toujours avec le même principe de fonctionnalités accordées par édition |
| Sauvegardes | Fichier SQLite copié via l'API native, planification locale | Sauvegardes serveur automatisées (voir 37.11), avec granularité par organisation/tenant |
| Rapports/export | CSV uniquement, génération synchrone en mémoire | Export CSV conservé, ajout envisageable de PDF/Excel en tâche asynchrone (volumes potentiellement plus grands en multi-boutiques) |
| Reçus PDF | Génération locale via Qt (`QTextDocument`) | Génération serveur (bibliothèque de rendu PDF côté backend), même contenu/structure |
| Stockage des logos | Fichier local dans le dossier de données de l'application | Stockage objet (voir 37.14) |

## 37.3 Fonctionnalités nouvelles nécessaires au Web

- **Authentification Web** : mécanisme de connexion adapté à un navigateur (formulaire + jeton de session ou JWT, expiration/renouvellement de session), tout en conservant la politique de mot de passe actuelle comme base (à renforcer — voir 37.4) et le hachage Argon2 déjà en place (directement réutilisable côté serveur).
- **Gestion des sessions** : sessions serveur multi-utilisateur simultanées (le modèle Desktop actuel — un seul `_current_user` en mémoire de process — n'est pas transposable tel quel ; il faudra un état de session par utilisateur connecté, avec expiration/déconnexion à distance).
- **API REST (ou équivalent)** : une couche API n'existe pas du tout aujourd'hui (l'UI PySide6 appelle directement les services Python en mémoire) ; elle est indispensable pour tout frontend Web/mobile.
- **Frontend Web** : à concevoir entièrement (aucun code HTML/JS/CSS n'existe dans le projet actuel) — pourrait réutiliser la structure fonctionnelle des pages PySide6 existantes comme cahier des charges d'écrans, sans réutiliser aucun code.
- **Backend** : service HTTP exposant la logique métier actuelle (qui reste largement réutilisable en l'état, car déjà découplée de l'UI dans la couche `app/services/`) — un travail de portage de cette couche vers un framework Web (ex. FastAPI/Django) est envisageable en conservant la logique métier, pas l'ORM SQLite-only ni l'appel direct en mémoire.
- **PostgreSQL** : remplacement du moteur SQLite pour supporter l'accès concurrent multi-utilisateur réel (SQLite au niveau de robustesse actuel n'est pas conçu pour des écritures concurrentes intensives multi-postes).
- **Multi-utilisateur réel** : accès simultané de plusieurs utilisateurs à la même base de données, avec gestion de la concurrence (verrous optimistes/transactions) — absent aujourd'hui puisque tout tourne sur un seul poste avec une seule session active.
- **Multi-postes** : accès à la même instance StockManager depuis plusieurs machines — impossible en V1 (base de données locale au poste).
- **Multi-boutiques** : notion de site/entrepôt/point de vente absente du modèle de données actuel (pas de champ « boutique » sur `Article`, `Vente`, etc.) — à concevoir entièrement si retenue.
- **Synchronisation** : sans objet en V1 (rien à synchroniser, une seule base). Devient pertinente si un mode déconnecté/local est conservé en parallèle du Web.
- **Gestion centralisée des licences** : aujourd'hui, chaque poste importe son propre fichier `.lic` ; un modèle SaaS impliquerait un service d'émission/révocation/renouvellement centralisé.
- **Sauvegardes serveur** : automatisation gérée par l'infrastructure (au lieu du minuteur applicatif + tâche planifiée Windows actuels).
- **Audit centralisé** : le journal d'audit actuel est déjà structuré de façon à être portable (table dédiée, append-only) ; en Web, il faudrait l'étendre pour couvrir les événements propres à l'infrastructure serveur (connexions API, exports, etc.).
- **Notifications** : totalement absentes en V1 — à construire (ex. alerte stock faible par email, notification de créance en retard).
- **Sécurité renforcée** : verrouillage de compte après échecs répétés, complexité de mot de passe, éventuellement authentification à deux facteurs — aucun de ces éléments n'existe en Desktop V1.
- **Gestion des fichiers / stockage des logos et documents** : un véritable service de stockage de fichiers (objet, ex. S3-compatible) devient nécessaire dès qu'il y a plusieurs serveurs applicatifs ou plusieurs organisations clientes.
- **Architecture SaaS éventuelle** : isolation multi-tenant (une base ou un schéma par client, ou un discriminant d'organisation dans chaque table) — concept totalement absent du modèle actuel, mono-entreprise par construction.

## 37.4 Limitations de Desktop à résoudre

- Absence de verrouillage de compte après échecs de connexion répétés.
- Absence de règles de complexité de mot de passe (seule la longueur minimale de 8 caractères est vérifiée).
- Absence de récupération de mot de passe en libre-service (dépendance totale à un administrateur).
- Modèle mono-poste/mono-session : ne supporte pas plusieurs utilisateurs connectés simultanément sur des postes différents.
- Absence de notion de site/boutique/entrepôt dans le modèle de données — bloquant pour tout scénario multi-boutiques.
- `max_devices` de la licence purement informationnel, non appliqué techniquement (pas de serveur pour le faire respecter).
- Export de rapports limité au CSV.
- Aucune API : toute intégration externe (comptabilité, e-commerce, etc.) est aujourd'hui impossible sans développement spécifique direct sur la base SQLite (non recommandé et non prévu).

## 37.5 Authentification Web — analyse détaillée

Le mécanisme actuel (`AuthService`, `app/services/auth/auth_service.py`) est un bon point de départ fonctionnel : vérification `username`/`password` (Argon2), message d'erreur volontairement générique, distinction compte désactivé, `must_change_password`. Pour le Web, il faudrait ajouter : gestion de jetons de session (cookies sécurisés ou JWT), expiration de session, éventuellement authentification multi-facteurs, et une politique de mot de passe renforcée (cf. 37.4).

## 37.6 Gestion des sessions — analyse détaillée

`AuthService` actuel maintient un unique `_current_user` par processus applicatif (`app/services/auth/auth_service.py:42-59`) — modèle intrinsèquement mono-utilisateur par instance. En Web, chaque requête doit être associée à un utilisateur authentifié indépendamment (session serveur partagée ou jeton signé), avec possibilité de sessions concurrentes multiples (plusieurs onglets, plusieurs appareils).

## 37.7 API REST — analyse détaillée

Aujourd'hui, `app/views/pages/*.py` appelle directement les méthodes des services (`app/services/*/*.py`) en mémoire, dans le même processus Python. Il n'existe aucune sérialisation JSON, aucune route HTTP. La couche service actuelle, déjà bien isolée de l'UI et du modèle (chaque service prend ses propres DTOs d'entrée/sortie — ex. `ArticleSummary`, `VenteSummary`), constitue une bonne base de conception pour définir les contrats d'API REST (ou GraphQL) à exposer.

## 37.8 Frontend Web — analyse détaillée

Aucun frontend Web n'existe. La structure fonctionnelle des pages PySide6 (formulaires, tableaux, filtres, dialogues de confirmation) peut servir de spécification d'écrans pour un frontend Web (React/Vue/etc. à choisir), sans réutilisation de code (Qt et Web ne partagent aucune techno de rendu).

## 37.9 Backend / PostgreSQL — analyse détaillée

La couche `app/services/` est déjà séparée de la couche de présentation, ce qui facilite un portage vers un backend Web. La couche `app/repositories/` utilise SQLAlchemy, compatible nativement avec PostgreSQL (changement de chaîne de connexion et de dialecte, sans réécriture du modèle). Points d'attention identifiés lors de l'audit : le `PRAGMA foreign_keys=ON` est spécifique à SQLite (PostgreSQL applique les clés étrangères nativement, sans configuration) ; l'API de sauvegarde native (`sqlite3.Connection.backup()`) devra être remplacée par l'outillage PostgreSQL ; l'index unique partiel sur `code_barres` est directement reproductible sous PostgreSQL.

## 37.10 Gestion centralisée des licences — analyse détaillée

Le modèle actuel de signature Ed25519 hors ligne reste pertinent comme **mécanisme de confiance**, mais la distribution/révocation devrait devenir un service centralisé (base de licences côté serveur, tableau de bord d'administration pour l'éditeur TechNova, application réelle de `max_devices`/`max_postes` par un contrôle serveur plutôt qu'une simple valeur informative locale).

## 37.11 Sauvegardes serveur — analyse détaillée

Le principe actuel (vérification d'intégrité systématique avant/après, sauvegarde de sécurité automatique avant toute opération destructive) est une bonne pratique à conserver dans son esprit, en la déléguant à l'outillage natif du SGBD serveur et/ou à l'infrastructure d'hébergement (snapshots automatiques, réplication), plutôt qu'à un minuteur applicatif.

## 37.12 Audit centralisé — analyse détaillée

Le modèle `AuditLog` actuel (rétention illimitée, append-only, action/entité/résultat) est directement réutilisable comme structure de base ; à étendre pour couvrir les événements spécifiques à une architecture Web/API (ex. requêtes API sensibles, exports de données, changements d'organisation en contexte multi-tenant).

## 37.13 Notifications — analyse détaillée

Fonctionnalité entièrement absente aujourd'hui. Cas d'usage envisageables à partir des données déjà modélisées : alerte de stock faible/rupture (déjà calculée pour le tableau de bord et les rapports), alerte de créance échue (déjà calculable depuis `Vente.statut_paiement`/`reste_a_payer`), rappel de sauvegarde en échec.

## 37.14 Gestion des fichiers / stockage des logos et documents — analyse détaillée

Aujourd'hui, le logo de l'entreprise cliente est stocké comme un simple fichier local (`<dossier de données>/branding/logo_entreprise.<ext>`). En Web, un stockage de type objet (compatible S3 ou équivalent) est recommandé, en particulier en contexte multi-tenant/multi-serveur.

## 37.15 Rapports et exports — analyse détaillée

Le CSV actuel reste un format d'export pertinent à conserver. Des formats supplémentaires (PDF, Excel) pourraient être ajoutés en Web, potentiellement en tâche asynchrone pour les gros volumes (multi-boutiques).

## 37.16 Architecture SaaS éventuelle — analyse détaillée

Question ouverte, à trancher avec le métier avant toute conception technique : isolation multi-tenant par base/schéma séparé (plus simple à raisonner, plus coûteux à opérer à grande échelle) versus discriminant d'organisation dans chaque table (plus complexe à sécuriser, plus économique à grande échelle). Le modèle de données actuel n'a aucune notion d'organisation/tenant — ce choix structurera fortement le modèle de données Web (voir §38, section correspondance).

---

# 38. Modèle de données — détail par entité et correspondance Web

> Toutes les entités et tous les champs ci-dessous existent réellement dans le modèle SQLAlchemy actuel (`app/models/`), vérifiés fichier par fichier. Les colonnes futures proposées dans les blocs « Correspondance possible pour la future base Web » sont explicitement marquées **[PROPOSITION]** et n'existent pas dans Desktop V1.

## Infrastructure commune du modèle

- **`TimestampMixin`** (`app/models/mixins.py`) : `date_creation` (UTC, non nul), `date_modification` (UTC, non nul, mis à jour automatiquement) — appliqué à la quasi-totalité des entités.
- **Types dédiés** (`app/models/types.py`) : `MONEY = Numeric(14,2)` pour tout montant ; `QUANTITY = Numeric(14,3)` pour toute quantité (unités fractionnaires possibles, ex. kg/L) — jamais de type flottant.
- Tous les enums métier sont stockés comme **texte** (`native_enum=False`).
- Aucun validateur Python (`@validates`) : toute l'intégrité passe par des `CheckConstraint`, contraintes d'unicité/index et clés étrangères SQL (appliquées grâce à `PRAGMA foreign_keys=ON`).

## User (`users`)

**Rôle** : compte utilisateur de l'application.
**Attributs** : `id`, `username` (50c, unique), `password_hash` (255c, Argon2), `role_id` (FK Role, obligatoire — colonne historique de compatibilité, voir ci-dessous), `actif` (bool, défaut vrai), `must_change_password` (bool, défaut faux), `dernier_login` (nullable), horodatages.
**Relations** : plusieurs rôles (many-to-many via `user_roles`, migration `0011_user_roles_many_to_many`) — un utilisateur peut posséder plusieurs rôles ; ses permissions effectives sont l'union des permissions de tous ses rôles.
**Contraintes** : `username` unique ; au moins un rôle obligatoire (`user_roles`), jamais le même rôle deux fois pour un même utilisateur.
**Règles métier** : aucune suppression physique (activation/désactivation uniquement) ; garde-fous « dernier administrateur actif » (voir §7/§41), appliqués sur l'ensemble réel des rôles détenus, pas sur un rôle « principal » ; `role_id` reste renseigné (premier rôle attribué) à titre de compatibilité, mais n'est jamais la source de vérité pour les permissions — celle-ci est exclusivement `user_roles`.

**Correspondance possible pour la future base Web** : conserver telle quelle. **[PROPOSITION]** ajout d'un `organization_id`/`tenant_id` si architecture multi-tenant retenue ; **[PROPOSITION]** champs de sécurité renforcée (`failed_login_count`, `locked_until`, `mfa_secret`) — absents aujourd'hui (voir §37.4).

## Role (`roles`) / Permission (`permissions`) / `role_permissions` / `user_roles`

**Rôle** : RBAC — un rôle regroupe un ensemble de permissions ; association many-to-many via `role_permissions`. Un utilisateur peut à son tour posséder plusieurs rôles, via l'association many-to-many `user_roles` (`user_id`, `role_id`, clé primaire composite, FK `ondelete=CASCADE` des deux côtés).
**Attributs Role** : `id`, `nom` (50c, unique), `description` (255c).
**Attributs Permission** : `id`, `code` (50c, unique, indexé), `libelle` (255c), `module` (50c).
**Règles métier** : 4 rôles fixes, aucune création/suppression, garde-fous décrits au §7. Un rôle a désormais plusieurs utilisateurs comme avant (many-to-one devenu many-to-many côté `User`), sans changement sur la gestion des permissions d'un rôle lui-même.

**Correspondance possible pour la future base Web** : structure directement conservable. **[PROPOSITION]** possibilité de rôles personnalisés par organisation si le Web autorise la création de rôles au-delà des 4 rôles système (décision produit à valider).

## Article, Category, Supplier, ExitReason (`articles`, `categories`, `fournisseurs`, `motifs_sortie`)

**Rôle** : catalogue et référentiels.
**Attributs communs** : `statut` (`StatutActifInactif` : ACTIF/INACTIF).
**Article — attributs propres** : `reference` (50c, unique), `designation` (255c), `category_id` (FK obligatoire), `unite` (20c), `fournisseur_principal_id` (FK optionnelle), `prix_achat_defaut`/`prix_vente`/`cout_moyen_pondere` (MONEY, ≥0), `stock_actuel`/`stock_min`/`stock_max` (QUANTITY, ≥0, `stock_max ≥ stock_min` si renseigné), `emplacement` (100c), `code_barres` (50c, unique **parmi les articles actifs uniquement** — index unique partiel), `description` (1000c).
**Règles métier** : jamais de suppression physique ; `stock_actuel`/`cout_moyen_pondere` exclusivement pilotés par `StockService`, jamais une écriture directe.

**Correspondance possible pour la future base Web** : conservable telle quelle. **[PROPOSITION]** `boutique_id`/`site_id` sur `Article` (et sur les stocks, potentiellement une table de stock par site plutôt qu'un champ unique sur l'article) si le multi-boutiques est retenu — changement structurant, à concevoir avec soin (le stock deviendrait par site, pas global par article).

## Client (`clients`)

**Rôle** : client de l'entreprise.
**Attributs** : `nom` (150c), `telephone`, `email`, `adresse`, `observations`, `statut`.
**Règles métier** : aucune suppression physique ; désactivation n'empêche pas la consultation de l'historique de ventes.

**Correspondance possible pour la future base Web** : conservable telle quelle.

## Entree / EntreeLigne, Sortie / SortieLigne (`entrees`/`entree_lignes`, `sorties`/`sortie_lignes`)

**Rôle** : documents de mouvement de stock hors vente.
**Attributs Entree/Sortie** : `numero` (unique), `date`, `fournisseur_id`/`motif_id`, `user_id`, `commentaire`, `statut` (`StatutOperation` : BROUILLON/VALIDEE/ANNULEE), `annulation_motif` (String(500), nullable — NULL tant que non annulée, renseigné une seule fois à l'annulation, jamais modifié ensuite ; ajouté par la migration `0010_motif_annulation`).
**Attributs ligne** : `article_id`, `quantite` (>0), `prix_unitaire`/`cout_unitaire` (≥0), `montant`.
**Règles métier** : jamais de suppression physique ; workflow Brouillon→Validée→(Annulée) ; toute annulation exige désormais un motif obligatoire (≥5 caractères après trim), vérifié côté service.

**Correspondance possible pour la future base Web** : conservable telle quelle. **[PROPOSITION]** `boutique_id` si multi-boutiques.

## Vente / VenteLigne, Paiement (`ventes`/`vente_lignes`, `paiements`)

**Rôle** : documents de vente et encaissements associés.
**Attributs Vente** : `numero`, `date`, `user_id`, `client_id` (**nullable** — vente comptant), `statut`, `total`, `montant_paye` (dénormalisé, recalculé à chaque `Paiement`), `statut_paiement` (`StatutPaiement` : NON_PAYEE/PARTIELLEMENT_PAYEE/PAYEE), `annulation_motif` (String(500), nullable — même règle que pour Entree/Sortie, ajouté par la migration `0010_motif_annulation`).
**Attributs Paiement** : `vente_id`, `montant` (>0), `date_heure`, `mode_paiement` (texte libre, 50c), `reference` (100c), `user_id`, `commentaire` (500c).
**Règles métier** : `Vente` est le **seul** document physiquement supprimable (brouillon uniquement) ; `Paiement` est strictement immuable (aucune méthode de modification/suppression) ; `montant_paye`/`statut_paiement` sont des totaux courants dénormalisés, jamais la source de vérité (la somme réelle des `Paiement` l'est).

**Correspondance possible pour la future base Web** : conservable telle quelle. **[PROPOSITION]** un enum de modes de paiement structuré (au lieu du texte libre actuel) pourrait être envisagé pour le Web si une intégration comptable est prévue — à valider avec le métier, car cela change une règle actuellement volontairement souple.

## MouvementStock (`mouvements_stock`)

**Rôle** : journal central et immuable de toute variation de stock.
**Attributs** : `date_heure`, `article_id`, `type` (`TypeMouvement` : ENTREE/SORTIE/VENTE/AJUSTEMENT/ANNULATION), `quantite` (signée), `stock_avant`/`stock_apres`, `cout_unitaire`, quatre FK nullables d'origine (`entree_ligne_id`/`sortie_ligne_id`/`vente_ligne_id`/`inventaire_ligne_id`, une seule renseignée par ligne), `mouvement_origine_id` (auto-référence, pour le chaînage d'annulation), `user_id`, `commentaire`.
**Règles métier** : jamais modifié ni supprimé après création ; source de vérité de `Article.stock_actuel`.

**Correspondance possible pour la future base Web** : conservable telle quelle, structure déjà pensée pour la traçabilité à grande échelle. **[PROPOSITION]** `boutique_id` si multi-boutiques (le stock deviendrait un solde par article **et** par site).

## Inventaire / InventaireLigne (`inventaires`/`inventaire_lignes`)

**Rôle** : comptage physique périodique et ajustement du stock.
**Attributs Inventaire** : `numero`, `date`, `user_id`, `statut` (`StatutInventaire` : BROUILLON/VALIDE **uniquement**).
**Attributs ligne** : `stock_theorique` (figé à la construction), `stock_physique` (saisie manuelle), `ecart`.
**Règles métier** : aucune annulation possible une fois validé — décision métier explicite documentée dans le code.

**Correspondance possible pour la future base Web** : conservable telle quelle.

## AuditLog (`audit_logs`)

**Rôle** : journal des opérations sensibles, rétention illimitée.
**Attributs** : `date_heure`, `user_id` (nullable), `action` (100c), `entite` (100c), `entite_id`, `details` (texte libre), `resultat` (`ResultatAudit` : SUCCES/ECHEC).

**Correspondance possible pour la future base Web** : conservable telle quelle. **[PROPOSITION]** enrichissement avec des champs propres à une API (adresse IP, user-agent) si pertinent pour le Web.

## Parametre (`parametres`)

**Rôle** : magasin clé-valeur générique (devise, informations entreprise, configuration de sauvegarde, etc.).
**Attributs** : `cle` (PK, 100c), `valeur` (texte).

**Correspondance possible pour la future base Web** : un magasin clé-valeur générique reste utilisable, mais **[PROPOSITION]** en contexte multi-tenant, chaque paramètre devrait être scoppé par organisation (`organization_id` + `cle` comme clé composite) plutôt qu'une table globale unique comme aujourd'hui.

## Licence (`licences`)

**Rôle** : licence activée localement.
**Attributs** : `client` (150c), `produit` (100c), `edition` (`EditionLicence` : DEMO/STANDARD/PROFESSIONAL/ENTREPRISE), `date_emission`, `date_expiration` (nullable), `max_users`, `max_postes`, `statut` (`StatutLicence` : ACTIVE/EXPIREE/INVALIDE/REVOQUEE, snapshot uniquement — l'état réel est toujours recalculé par vérification cryptographique), `payload_json` (signé), `signature`.

**Correspondance possible pour la future base Web** : structure conservable comme trace locale d'activation, mais en SaaS la source de vérité deviendrait un service de licences centralisé côté serveur (voir §37.10) plutôt qu'une table locale par poste.

---

# 39. Matrice des fonctionnalités

| Fonctionnalité | Desktop V1 | Future Web | Observation |
|---|:---:|:---:|---|
| Articles | ✅ | ✅ (conservé) | Ajout possible d'un rattachement par boutique |
| Catégories | ✅ | ✅ (conservé) | — |
| Fournisseurs | ✅ | ✅ (conservé) | — |
| Clients | ✅ | ✅ (conservé) | — |
| Motifs de sortie | ✅ | ✅ (conservé) | Réservés à l'Administrateur en V1 |
| Entrées | ✅ | ✅ (conservé) | — |
| Sorties | ✅ | ✅ (conservé) | — |
| Ventes | ✅ | ✅ (conservé) | Client optionnel conservé (vente comptant) |
| Paiements | ✅ | ✅ (conservé) | Immuabilité à conserver impérativement |
| Créances | ✅ (vue dérivée des ventes) | ✅ (conservé) | Pas de modèle dédié en V1, réutilise `SaleService` |
| Inventaires | ✅ (sans annulation) | ✅ (conservé, à rediscuter) | Absence d'annulation à revalider comme règle métier permanente ou limitation V1 à lever |
| Mouvements | ✅ (lecture seule) | ✅ (conservé) | Journal immuable |
| Rapports | ✅ (9 rapports, export CSV) | ⚙️ à étendre | Export PDF/Excel envisageable |
| Audit | ✅ (rétention illimitée) | ⚙️ à étendre | Étendre aux événements API/serveur |
| Sauvegardes | ✅ (manuelle + planifiée locale) | ⚙️ à adapter | Vers outillage serveur/infrastructure |
| Licences | ✅ (activation locale hors ligne) | ⚙️ à adapter | Vers gestion centralisée |
| Multi-utilisateur | ⚠️ limité (comptes multiples, un seul actif par poste à la fois) | 🆕 à construire | Sessions concurrentes multi-postes absentes en V1 |
| Multi-postes | ❌ absent | 🆕 à construire | Base locale à un seul poste en V1 |
| Multi-boutiques | ❌ absent | 🆕 à construire | Aucune notion de site dans le modèle actuel |
| API REST | ❌ absent | 🆕 à construire | Aucune couche API en V1 |
| Notifications | ❌ absent | 🆕 à construire | — |
| Authentification Web (jetons/sessions) | ❌ absent | 🆕 à construire | Base Argon2 réutilisable |
| Synchronisation | ❌ absent | 🆕 (si mode déconnecté conservé) | Sans objet si tout-Web |
| Architecture SaaS multi-tenant | ❌ absent | ❓ à trancher | Décision produit préalable requise |

Légende : ✅ existe et fonctionne / ⚙️ existe, nécessite adaptation / 🆕 n'existe pas, à construire / ❌ absent / ❓ décision à prendre.

---

# 40. Matrice des rôles

Source : seed initial de référence (`app/db/seed.py`), état par défaut. Un administrateur peut modifier ces permissions par rôle en usage réel (sous réserve des garde-fous du §7) — le tableau ci-dessous décrit l'état de référence initial, pas nécessairement l'état courant d'une installation donnée.

Cette matrice décrit les permissions **par rôle** : un utilisateur peut posséder plusieurs rôles. Les permissions effectives correspondent à l'union des permissions de tous ses rôles. Exemple : Jean cumule Vendeur + Gestionnaire de stock — il dispose de la colonne « Vendeur » ET de la colonne « Gestionnaire de stock » réunies (une seule connexion, un seul mot de passe).

| Permission | Administrateur | Gestionnaire de stock | Vendeur | Consultation |
|---|:---:|:---:|:---:|:---:|
| DASHBOARD_VIEW | ✓ | ✓ | ✓ | ✓ |
| ARTICLE_VIEW | ✓ | ✓ | ✓ | ✓ |
| ARTICLE_CREATE / UPDATE / ACTIVATE / DEACTIVATE | ✓ | ✓ | ✗ | ✗ |
| CATEGORY_VIEW | ✓ | ✓ | ✗ | ✓ |
| CATEGORY_CREATE / UPDATE / ACTIVATE / DEACTIVATE | ✓ | ✓ | ✗ | ✗ |
| SUPPLIER_VIEW | ✓ | ✓ | ✗ | ✓ |
| SUPPLIER_CREATE / UPDATE / ACTIVATE / DEACTIVATE | ✓ | ✓ | ✗ | ✗ |
| STOCK_REASON_VIEW / CREATE / UPDATE / ACTIVATE / DEACTIVATE | ✓ | ✗ | ✗ | ✗ |
| STOCK_ENTRY_VIEW / CREATE / UPDATE / VALIDATE | ✓ | ✓ | ✗ | ✗ |
| STOCK_ENTRY_CANCEL | ✓ | ✗ | ✗ | ✗ |
| STOCK_EXIT_VIEW / CREATE / UPDATE / VALIDATE | ✓ | ✓ | ✗ | ✗ |
| STOCK_EXIT_CANCEL | ✓ | ✗ | ✗ | ✗ |
| SALE_VIEW / CREATE / UPDATE / VALIDATE / PAYMENT_CREATE | ✓ | ✗ | ✓ | ✗ |
| SALE_CANCEL | ✓ | ✗ | ✗ | ✗ |
| CLIENT_VIEW / CREATE / UPDATE | ✓ | ✓ | ✓ | ✗ |
| CLIENT_ACTIVATE / DEACTIVATE | ✓ | ✓ | ✗ | ✗ |
| STOCK_MOVEMENT_VIEW | ✓ | ✓ | ✗ | ✓ |
| INVENTORY_VIEW / CREATE / UPDATE / VALIDATE | ✓ | ✓ | ✗ | ✗ |
| REPORT_VIEW | ✓ | ✓ | ✗ | ✓ |
| REPORT_EXPORT | ✓ | ✓ | ✗ | ✗ |
| USER_VIEW / CREATE / UPDATE / ACTIVATE / RESET_PASSWORD | ✓ | ✗ | ✗ | ✗ |
| ROLE_VIEW / UPDATE | ✓ | ✗ | ✗ | ✗ |
| SETTINGS_VIEW / UPDATE | ✓ | ✗ | ✗ | ✗ |
| BACKUP_VIEW / CREATE / RESTORE | ✓ | ✗ | ✗ | ✗ |
| AUDIT_VIEW | ✓ | ✗ | ✗ | ✗ |
| LICENSE_VIEW / ACTIVATE | ✓ | ✗ | ✗ | ✗ |
| SYSTEM_RESET_BUSINESS_DATA | ✓ | ✗ | ✗ | ✗ |

**Notes** : le Vendeur peut créer/modifier un client à la volée mais jamais l'activer/désactiver. Les motifs de sortie sont une exclusivité de l'Administrateur (y compris leur simple consultation). Seul l'Administrateur peut annuler une entrée, une sortie ou une vente déjà validée par défaut.

---

# 41. Règles métier — récapitulatif vérifié

Toutes les règles ci-dessous ont été vérifiées directement dans le code source (citations `fichier:ligne`) au cours de cet audit.

| # | Règle | Vérifiée dans |
|---|---|---|
| 1 | Aucun stock négatif : toute opération qui ferait passer `stock_actuel` sous zéro est refusée, sans exception ni contournement de rôle | `app/services/stock/stock_service.py:93-100` |
| 2 | Le stock n'est modifié **que** via `StockService.apply_movement` — jamais d'écriture directe de `Article.stock_actuel` ailleurs dans le code | `app/services/stock/stock_service.py` (point de passage unique, confirmé par absence d'écriture directe dans entries/exits/sales/inventory) |
| 3 | Une entrée validée génère un mouvement de type `ENTREE` par ligne | `app/services/entries/entry_service.py:385-393` |
| 4 | Une sortie validée génère un mouvement de type `SORTIE` (quantité négative) par ligne | `app/services/exits/exit_service.py:408-416` |
| 5 | Une vente validée génère un mouvement de type `VENTE` (quantité négative) par ligne | `app/services/sales/sale_service.py:540-548` |
| 6 | Un paiement ne modifie jamais le stock (aucun appel à `StockService` dans `record_payment`) | `app/services/sales/sale_service.py:630-686` |
| 7 | Une annulation (entrée/sortie/vente) génère un mouvement inverse de type `ANNULATION`, référençant le mouvement d'origine | `entry_service.py:430-439`, `exit_service.py:453-462`, `sale_service.py:602-619` |
| 8 | Les opérations validées (entrée/sortie/vente) ne sont jamais physiquement supprimables — seule une vente en **brouillon** l'est | `sale_service.py:458-479` (seule exception), absence de `delete_` dans `entry_service.py`/`exit_service.py` |
| 9 | Un paiement enregistré est immuable (aucune méthode de modification/suppression) | `app/models/payment.py`, `app/services/sales/sale_service.py` (seules `record_payment`/`list_payments` existent) |
| 10 | Les mouvements de stock sont immuables (journal append-only) | `app/repositories/mouvement_repository.py` (aucune méthode `update`/`delete`) |
| 11 | Un inventaire est définitif en V1 : aucune annulation possible après validation | `app/services/inventory/inventory_service.py:36-39,311-314` |
| 12 | Les dates d'opération (entrée, sortie, vente, inventaire) ne peuvent jamais être dans le futur | `app/utils/dates.py::validate_not_future_date`, appliqué dans les 4 services concernés |
| 13 | Les quantités de ligne sont toujours strictement positives (contrainte `CHECK > 0`) | `app/models/documents.py` (contraintes sur `EntreeLigne`/`SortieLigne`/`VenteLigne`) |
| 14 | Les montants/prix sont toujours ≥ 0 (contrainte `CHECK >= 0`) | idem, colonnes `MONEY` |
| 15 | Tous les montants utilisent `Decimal` (jamais de flottant) | `app/models/types.py::MONEY = Numeric(14,2)`, `QUANTITY = Numeric(14,3)` |
| 16 | Arrondi monétaire centralisé en `ROUND_HALF_UP` | `app/utils/money.py::round_money` |
| 17 | Le CMUP n'est recalculé que sur un mouvement de type `ENTREE` | `app/services/stock/stock_service.py:102-107` |
| 18 | La formule CMUP est : `((stock_avant × CMUP_avant) + (quantité × prix_achat)) / (stock_avant + quantité)` | `app/services/stock/stock_service.py:130-145` |
| 19 | Une licence et une permission RBAC peuvent toutes deux être nécessaires pour une fonctionnalité donnée (double contrôle) | `app/services/licensing/permission_map.py`, `app/services/auth/permission_service.py` |
| 20 | Toute annulation (entrée, sortie, vente validée) exige un motif obligatoire (non vide, non uniquement des espaces, ≥5 caractères après trim), vérifié côté service — jamais uniquement côté interface | `app/services/entries/entry_service.py::_validate_annulation_motif`, `app/services/exits/exit_service.py::_validate_annulation_motif`, `app/services/sales/sale_service.py::_validate_annulation_motif` |
| 21 | Le motif d'annulation est conservé définitivement (`annulation_motif`), jamais modifié après l'annulation, et n'est jamais inventé rétroactivement pour les opérations annulées avant l'introduction de ce champ (`NULL` dans ce cas) | `app/models/documents.py`, migration `0010_motif_annulation` |
