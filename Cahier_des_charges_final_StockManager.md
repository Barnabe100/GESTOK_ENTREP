# Cahier des charges — StockManager Desktop

## 1. Présentation du projet

**StockManager Desktop** est une application Windows de gestion de stock destinée aux petites et moyennes entreprises.

L’application doit permettre de gérer :

- les articles ;
- les catégories ;
- les fournisseurs ;
- les entrées de stock ;
- les sorties de stock ;
- les ventes ;
- les inventaires ;
- les utilisateurs ;
- les rôles et permissions ;
- les rapports ;
- les sauvegardes ;
- les licences commerciales.

### Technologies

- Python 3.x
- PySide6
- SQLite
- SQLAlchemy
- pytest
- PyInstaller

L’application doit fonctionner hors connexion.

---

## 2. Objectifs

L’application doit permettre de :

1. centraliser les données de stock ;
2. connaître le stock disponible en temps réel ;
3. enregistrer et tracer les entrées et sorties ;
4. gérer les ventes ;
5. empêcher les stocks négatifs ;
6. réaliser des inventaires ;
7. contrôler les accès selon les rôles ;
8. produire des rapports ;
9. effectuer des sauvegardes manuelles et automatiques ;
10. restaurer une sauvegarde de manière sécurisée ;
11. gérer des licences commerciales par client ;
12. être distribuée sous forme d’exécutable Windows.

---

## 3. Utilisateurs et rôles

### 3.1 Administrateur

Accès complet à :

- utilisateurs ;
- rôles et permissions ;
- articles ;
- catégories ;
- fournisseurs ;
- entrées ;
- sorties ;
- ventes ;
- inventaires ;
- mouvements ;
- rapports ;
- sauvegardes ;
- restauration ;
- paramètres ;
- licence.

### 3.2 Gestionnaire de stock

Peut gérer :

- articles ;
- catégories ;
- fournisseurs ;
- entrées ;
- sorties ;
- inventaires ;
- mouvements ;
- rapports de stock.

Il ne gère pas les paramètres sensibles, les licences ni les comptes administrateurs.

### 3.3 Vendeur

Peut :

- consulter les articles ;
- consulter le stock disponible ;
- créer des ventes ;
- valider les ventes ;
- consulter son historique de ventes.

Le vendeur ne doit pas modifier directement le stock en dehors du processus de vente.

### 3.4 Consultation

Accès en lecture seule aux données autorisées :

- articles ;
- stocks ;
- mouvements ;
- rapports.

---

## 4. Gestion des articles

Un article doit pouvoir contenir au minimum :

- ID ;
- référence unique ;
- désignation ;
- catégorie ;
- unité ;
- fournisseur principal ;
- prix d’achat/coût unitaire ;
- prix de vente ;
- stock actuel ;
- stock minimum ;
- stock maximum ;
- emplacement ;
- description ;
- statut actif/inactif ;
- date de création ;
- date de modification.

### Règles

- La référence est unique.
- Les champs obligatoires doivent être validés.
- Les quantités ne peuvent pas être négatives.
- Les prix ne peuvent pas être négatifs.
- Un article inactif ne peut pas être utilisé dans une nouvelle opération.

---

## 5. Gestion des catégories

Fonctions :

- créer ;
- modifier ;
- consulter ;
- rechercher ;
- activer/désactiver.

Une catégorie utilisée dans l’historique ne doit pas être supprimée physiquement sans justification.

---

## 6. Gestion des fournisseurs

Informations :

- nom/raison sociale ;
- contact ;
- téléphone ;
- email ;
- adresse ;
- ville ;
- pays ;
- observations ;
- statut.

Fonctions :

- création ;
- modification ;
- consultation ;
- recherche ;
- activation/désactivation.

---

## 7. Entrées de stock

Une entrée doit contenir :

- numéro ;
- date ;
- fournisseur ;
- référence du document ;
- utilisateur ;
- commentaire ;
- statut.

Une entrée comporte plusieurs lignes.

Chaque ligne contient :

- article ;
- quantité ;
- prix unitaire ;
- montant.

### Validation

Lorsqu’une entrée est validée :

`Stock après = Stock avant + quantité`

Chaque ligne validée doit créer le mouvement de stock correspondant.

Le stock ne doit être modifié qu’au moment de la validation.

---

## 8. Sorties de stock

Une sortie peut correspondre à :

- consommation interne ;
- dotation ;
- perte ;
- transfert ;
- échantillon ;
- autre motif configuré.

Elle doit contenir :

- numéro ;
- date ;
- motif ;
- bénéficiaire/service si applicable ;
- référence ;
- utilisateur ;
- commentaire ;
- statut.

### Validation

`Stock après = Stock avant - quantité`

Une sortie ne doit jamais permettre un stock négatif.

---

## 9. Ventes

Le vendeur dispose d’une interface dédiée aux ventes.

Fonctions :

1. rechercher un article ;
2. sélectionner une quantité ;
3. ajouter plusieurs articles ;
4. afficher les prix ;
5. calculer les sous-totaux ;
6. calculer le total ;
7. valider la vente.

### Processus

```text
Vendeur
    ↓
Création de la vente
    ↓
Contrôle du stock
    ↓
Validation
    ↓
StockService
    ↓
Décrémentation du stock
    ↓
Création des mouvements
```

Une vente validée ne doit jamais être appliquée deux fois.

---

## 10. Mouvements de stock

Chaque variation de stock doit être historisée.

Types minimum :

- ENTRÉE ;
- SORTIE ;
- VENTE ;
- AJUSTEMENT ;
- ANNULATION.

Chaque mouvement doit enregistrer :

- date/heure ;
- article ;
- type ;
- quantité ;
- stock avant ;
- stock après ;
- référence de l’opération ;
- utilisateur ;
- commentaire éventuel.

Les mouvements historiques ne doivent pas être modifiés directement.

---

## 11. Inventaires

Le module doit permettre de comparer :

**Stock théorique ↔ Stock physique**

Exemple :

```text
Stock théorique : 100
Stock physique  : 97
Écart           : -3
```

Lors de la validation, l’écart doit générer un mouvement d’ajustement.

L’historique de l’inventaire doit être conservé.

---

## 12. Alertes

### Stock faible

Lorsqu’un article respecte :

`Stock actuel <= Stock minimum`

l’application doit afficher une alerte.

### Rupture

Lorsqu’un article respecte :

`Stock actuel = 0`

l’application doit afficher une alerte de rupture.

---

## 13. Tableau de bord

Le dashboard doit afficher notamment :

- nombre total d’articles actifs ;
- nombre de catégories ;
- nombre de fournisseurs ;
- valeur du stock si disponible ;
- articles en stock faible ;
- articles en rupture ;
- entrées sur une période ;
- sorties sur une période ;
- ventes sur une période ;
- dernières opérations.

Des graphiques pourront être ajoutés.

---

## 14. Authentification et sécurité

L’application doit posséder une page de connexion.

Les mots de passe doivent être stockés sous forme de hash sécurisé et jamais en clair.

Fonctions :

- connexion ;
- déconnexion ;
- changement de mot de passe selon les droits ;
- activation/désactivation d’un compte ;
- contrôle des permissions ;
- journalisation des opérations sensibles.

---

## 15. Base de données

Tables minimales proposées :

```text
users
roles
categories
fournisseurs
articles
entrees
entree_lignes
sorties
sortie_lignes
ventes
vente_lignes
mouvements_stock
inventaires
inventaire_lignes
audit_logs
parametres
licences
```

### Contraintes

- clés primaires et étrangères correctement définies ;
- intégrité référentielle ;
- index sur les colonnes fréquemment recherchées ;
- foreign keys SQLite activées ;
- transactions pour les opérations critiques ;
- suppressions physiques limitées pour préserver l’historique.

---

## 16. Architecture technique

Architecture cible :

```text
PySide6 UI
     ↓
Views
     ↓
Services métier
     ↓
Repositories
     ↓
SQLAlchemy
     ↓
SQLite
```

La logique métier ne doit pas être placée directement dans les fenêtres PySide6.

La gestion du stock doit être centralisée dans un service dédié, par exemple :

```text
StockService
```

Aucune vue ne doit modifier directement la quantité en stock.

---

## 17. Structure de projet recommandée

```text
stock_manager/
├── app/
│   ├── main.py
│   ├── config/
│   ├── models/
│   ├── repositories/
│   ├── services/
│   ├── views/
│   ├── security/
│   ├── backup/
│   ├── licensing/
│   ├── utils/
│   └── resources/
├── tests/
├── docs/
├── requirements.txt
├── README.md
├── build.spec
└── .gitignore
```

---

## 18. Sauvegardes

### 18.1 Sauvegarde manuelle

L’administrateur doit pouvoir lancer :

**Paramètres → Sauvegarde → Sauvegarder maintenant**

Exemple de fichier :

```text
stock_2026-09-16_223000.db
```

L’application doit afficher un message de succès ou d’échec et journaliser l’opération.

### 18.2 Sauvegarde automatique

Configuration :

```text
Sauvegarde automatique : Activée

Fréquence :
- Quotidienne
- Hebdomadaire

Heure :
23:00

Nombre de sauvegardes à conserver :
30
```

La sauvegarde doit utiliser le mécanisme approprié de SQLite afin d’obtenir une copie cohérente de la base.

Si une sauvegarde doit être exécutée à une heure précise alors que l’application est fermée, une tâche Windows Task Scheduler pourra être prévue.

### 18.3 Rotation

Lorsque le nombre maximal de sauvegardes est atteint :

- conserver les plus récentes ;
- supprimer automatiquement les plus anciennes selon la politique configurée.

### 18.4 Restauration

La restauration est réservée à l’administrateur.

Avant toute restauration :

1. demander une confirmation explicite ;
2. créer une sauvegarde de sécurité de la base actuelle ;
3. restaurer la sauvegarde sélectionnée ;
4. vérifier l’intégrité de la base ;
5. recharger ou redémarrer l’application si nécessaire ;
6. journaliser l’opération.

---

## 19. Gestion des licences commerciales

L’application doit être conçue pour être commercialisée auprès de plusieurs clients.

Chaque client doit pouvoir disposer de sa propre licence.

### 19.1 Informations d’une licence

Une licence peut contenir :

- ID licence ;
- client ;
- produit ;
- édition ;
- date d’émission ;
- date d’expiration ;
- nombre maximal d’utilisateurs ;
- nombre maximal de postes ;
- statut ;
- informations complémentaires nécessaires à la validation.

Exemple :

```text
Produit : StockManager
Client : Entreprise XYZ
Édition : Professional
Licence : SM-2026-000123
Expiration : 31/12/2027
Postes autorisés : 2
Utilisateurs autorisés : 5
Statut : ACTIVE
```

### 19.2 Types de licences

Prévoir :

- licence Démo ;
- licence Standard ;
- licence Professional ;
- licence Entreprise ;
- licence Permanente ;
- licence à durée limitée.

### 19.3 Activation

Le système doit permettre :

```text
Achat
   ↓
Génération de licence
   ↓
Fichier de licence
   ↓
Installation
   ↓
Activation
   ↓
Vérification
   ↓
Utilisation
```

L’application doit pouvoir fonctionner hors connexion après activation selon les règles de l’édition de licence.

### 19.4 Sécurité de la licence

La licence doit être signée cryptographiquement.

Architecture :

```text
Outil du développeur
       │
   clé privée
       │
       ↓
Génération de licence
       │
       ↓
Licence signée
       │
       ↓
Application cliente
       │
   clé publique
       │
       ↓
Vérification
```

**La clé privée ne doit jamais être intégrée dans l’application distribuée.**

L’application distribuée ne doit contenir que la clé publique nécessaire à la vérification.

### 19.5 Vérifications

Au démarrage et/ou lors des opérations pertinentes, l’application doit vérifier :

- présence de la licence ;
- validité de la signature ;
- produit ;
- édition ;
- date d’expiration ;
- statut ;
- nombre de postes ;
- nombre d’utilisateurs ;
- intégrité des informations de licence.

Une licence invalide, expirée ou falsifiée doit être refusée avec un message explicite.

### 19.6 Écran de licence

Prévoir :

```text
┌──────────────────────────────────────┐
│ LICENCE                              │
├──────────────────────────────────────┤
│ Client : Entreprise XYZ              │
│ Produit : StockManager               │
│ Édition : Professional               │
│ Licence : SM-2026-000123             │
│ Statut : ACTIVE                      │
│ Expiration : Permanente              │
│ Postes autorisés : 2                 │
├──────────────────────────────────────┤
│ [ Activer une licence ]              │
│ [ Informations licence ]             │
└──────────────────────────────────────┘
```

---

## 20. Audit et journalisation

Les opérations sensibles doivent être journalisées :

- connexion ;
- déconnexion ;
- création/modification utilisateur ;
- entrée ;
- sortie ;
- vente ;
- inventaire ;
- ajustement ;
- sauvegarde ;
- restauration ;
- activation de licence ;
- modification de paramètres.

---

## 21. Rapports

Prévoir :

- état du stock ;
- articles en stock faible ;
- ruptures ;
- entrées ;
- sorties ;
- ventes ;
- mouvements ;
- inventaires ;
- activité utilisateur.

Exports possibles :

- CSV ;
- Excel ;
- PDF.

---

## 22. Interface utilisateur

L’interface doit être :

- moderne ;
- professionnelle ;
- sobre ;
- claire ;
- entièrement en français ;
- cohérente ;
- adaptée à Windows.

Navigation principale :

```text
Dashboard
Articles
Catégories
Fournisseurs
Entrées
Sorties
Ventes
Mouvements
Inventaires
Rapports
Utilisateurs
Paramètres
```

Les fonctions non autorisées doivent être masquées ou désactivées selon le rôle.

---

## 23. Tests

Les tests doivent couvrir au minimum :

- création d’article ;
- unicité des références ;
- catégories ;
- fournisseurs ;
- entrée ;
- sortie ;
- vente ;
- contrôle du stock disponible ;
- impossibilité de stock négatif ;
- calcul stock avant/après ;
- création des mouvements ;
- inventaire ;
- ajustement ;
- transactions et rollback ;
- permissions ;
- sauvegarde ;
- restauration ;
- validation de licence ;
- licence expirée ;
- licence falsifiée ;
- dépassement des limites de licence.

---

## 24. Packaging et déploiement

L’application doit être transformable en exécutable Windows avec PyInstaller.

Exemple :

```text
StockManager.exe
```

Le client ne doit pas avoir besoin d’installer Python.

Les dépendances et ressources nécessaires doivent être correctement embarquées.

La base SQLite de production ne doit pas être stockée dans un répertoire de ressources qui pourrait être remplacé lors d’une mise à jour.

La procédure d’installation et de mise à jour doit être documentée.

---

## 25. Exigences non fonctionnelles

### Performance

Les opérations courantes doivent être rapides pour un volume raisonnable de données.

### Fiabilité

Les opérations critiques doivent être transactionnelles.

### Sécurité

- authentification ;
- hash des mots de passe ;
- contrôle des rôles ;
- journalisation ;
- protection de la clé privée de licence.

### Maintenabilité

Le code doit être :

- modulaire ;
- lisible ;
- documenté ;
- testé ;
- organisé par responsabilités.

### Évolutivité

L’architecture doit permettre l’ajout futur de :

- clients ;
- paiements ;
- codes-barres ;
- multi-dépôts ;
- transferts ;
- API ;
- synchronisation ;
- version web/mobile.

---

# 26. Plan de réalisation

Le développement doit être réalisé progressivement.

```text
1. Analyse
2. Architecture
3. Modèle de données
4. Initialisation du projet
5. Authentification et rôles
6. Catégories
7. Fournisseurs
8. Articles
9. Service de gestion du stock
10. Entrées
11. Sorties
12. Ventes
13. Mouvements
14. Inventaires
15. Dashboard
16. Rapports
17. Sauvegardes
18. Licences
19. Tests globaux
20. Packaging
21. Audit final
```

---

# 27. Critères d’acceptation

Le projet sera considéré comme terminé lorsque :

- l’application démarre correctement ;
- la connexion fonctionne ;
- les quatre rôles fonctionnent ;
- les articles sont gérables ;
- les entrées fonctionnent ;
- les sorties fonctionnent ;
- les ventes fonctionnent ;
- les stocks négatifs sont impossibles ;
- les mouvements sont correctement tracés ;
- les inventaires fonctionnent ;
- le dashboard fonctionne ;
- les rapports fonctionnent ;
- les sauvegardes manuelles fonctionnent ;
- les sauvegardes automatiques fonctionnent ;
- la restauration fonctionne ;
- les licences peuvent être validées ;
- une licence expirée est détectée ;
- une licence falsifiée est rejetée ;
- les tests critiques passent ;
- l’application fonctionne sous Windows sous forme d’exécutable.

---

# 28. Consignes pour Claude Code

Le présent cahier des charges constitue la source de vérité fonctionnelle du projet.

Claude Code ne doit pas développer toute l’application en une seule étape.

## Phase 1 — Analyse

Avant de coder :

1. analyser le cahier des charges ;
2. identifier les ambiguïtés ;
3. identifier les règles métier manquantes ;
4. identifier les risques techniques ;
5. proposer les dépendances ;
6. proposer le plan de développement.

Aucune décision métier importante ne doit être prise silencieusement.

## Phase 2 — Architecture

Présenter avant implémentation :

- architecture ;
- arborescence ;
- modèle de données ;
- relations ;
- services ;
- repositories ;
- stratégie de tests ;
- stratégie de sauvegarde ;
- stratégie de licence ;
- stratégie PyInstaller.

Attendre la validation avant de continuer.

## Phase 3 — Développement

Développer par étapes fonctionnelles courtes.

Pour chaque fonctionnalité :

1. analyser ;
2. implémenter ;
3. tester ;
4. corriger ;
5. vérifier les régressions.

## Règle concernant le stock

Toutes les modifications du stock doivent passer par un service métier centralisé.

Aucune vue PySide6 ne doit modifier directement le stock.

Toute variation doit générer un mouvement.

Les opérations doivent être transactionnelles.

## Règle concernant les licences

La licence doit utiliser une signature cryptographique asymétrique.

La clé privée doit rester exclusivement chez le développeur.

La clé publique peut être intégrée dans l’application.

La clé privée ne doit jamais être présente dans le code, le dépôt Git ou l’exécutable distribué.

## Règle concernant les tests

Une fonctionnalité ne doit pas être considérée comme terminée uniquement parce que le code a été généré.

Claude Code doit exécuter les tests et signaler leur résultat.

## Fin de chaque tâche

Claude Code doit indiquer :

- ce qui a été développé ;
- les fichiers créés ;
- les fichiers modifiés ;
- les tests exécutés ;
- le résultat des tests ;
- les problèmes éventuels ;
- la prochaine étape.

Il ne doit pas modifier inutilement des fichiers sans rapport avec la tâche.

---

# 29. Audit final

À la fin du développement, effectuer un audit complet avant toute correction.

Vérifier :

1. conformité au cahier des charges ;
2. architecture ;
3. qualité du code ;
4. sécurité ;
5. permissions ;
6. intégrité SQLite ;
7. transactions de stock ;
8. absence de stock négatif ;
9. traçabilité ;
10. sauvegarde ;
11. restauration ;
12. licences ;
13. gestion des erreurs ;
14. tests ;
15. performances ;
16. packaging ;
17. documentation.

Pour chaque problème :

- gravité ;
- fichier concerné ;
- description ;
- conséquence ;
- correction proposée.

Présenter d’abord le rapport d’audit, puis attendre validation avant de corriger.

---

# 30. Évolutions futures

Les évolutions pourront inclure :

- gestion avancée des clients ;
- tickets/factures ;
- paiements ;
- codes-barres ;
- lecteurs de codes-barres ;
- multi-dépôts ;
- transferts entre dépôts ;
- import/export Excel avancé ;
- statistiques commerciales avancées ;
- synchronisation réseau ;
- API ;
- application mobile ;
- application web.

---

## Conclusion

StockManager Desktop doit être conçu comme une application professionnelle, fiable, maintenable et commercialisable.

Les fonctionnalités centrales sont :

**Gestion des articles → Gestion du stock → Ventes → Inventaires → Traçabilité → Utilisateurs/Rôles → Sauvegardes → Licences.**

L’architecture doit permettre de faire évoluer le logiciel sans remettre en cause les règles métier ni l’intégrité des données.
