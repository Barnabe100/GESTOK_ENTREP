# StockManager Desktop

Application desktop de gestion de stock (Python, PySide6, SQLAlchemy, SQLite),
fonctionnant hors ligne après activation d'une licence.

Le cahier des charges complet se trouve dans
[`Cahier_des_charges_final_StockManager.md`](Cahier_des_charges_final_StockManager.md).

Ce document distingue deux publics :

- **[Utilisateurs finaux](#version-cliente--utilisation)** : installation et
  utilisation de l'application packagée (`.exe` Windows), sans rien
  installer d'autre.
- **[Développeurs](#version-développeur)** : mise en place de
  l'environnement de développement, tests, migrations, build du package.

## État du projet

Toutes les phases fonctionnelles sont implémentées et validées : socle
technique, authentification/RBAC, catalogue (catégories, fournisseurs,
motifs de sortie, articles), mouvements de stock (entrées, sorties, ventes,
inventaires), rapports, sauvegardes/restauration, licences (Ed25519,
`FeatureGate`), Dashboard. La phase courante (Packaging) prépare la
distribution Windows — voir [`packaging/README.md`](packaging/README.md)
pour le détail du build et son état de validation.

---

## Version cliente — utilisation

Cette section s'adresse à l'utilisateur final d'un poste Windows sur lequel
StockManager Desktop a été installé — **aucun Python ni aucune dépendance de
développement n'est nécessaire** : l'installateur fournit tout ce qu'il
faut.

### Installation

1. Exécuter `StockManager-Setup-<version>.exe` (fourni par votre éditeur ou
   administrateur système).
2. Aucun droit administrateur n'est requis : l'installation se fait par
   défaut dans un dossier propre à l'utilisateur courant.
3. À la fin de l'installation, un raccourci est créé dans le menu Démarrer
   (et sur le Bureau, si la case correspondante a été cochée pendant
   l'installation).

### Premier démarrage

Au tout premier lancement, l'application :

- crée automatiquement sa base de données locale (SQLite) et applique le
  schéma nécessaire ;
- crée un compte **Administrateur** initial (identifiant `admin`, mot de
  passe temporaire généré aléatoirement, affiché dans le journal de
  démarrage — voir « Emplacement des journaux » ci-dessous) ;
- demande de changer ce mot de passe temporaire dès la première connexion.

Aucune licence n'est requise pour démarrer l'application, mais la plupart
des fonctionnalités (rapports, Dashboard, catalogue, mouvements de stock...)
nécessitent qu'une licence valide soit activée.

### Activation d'une licence

Dans le menu **Administration → Licences**, utiliser « Importer / activer
une licence » et sélectionner le fichier de licence (`.lic`) fourni par
l'éditeur. L'écran affiche ensuite le client, l'édition, les dates de
validité, les limites (utilisateurs/postes) et les fonctionnalités
couvertes par cette licence. Aucune connexion Internet n'est nécessaire :
l'activation et toute vérification ultérieure de la licence se font
entièrement hors ligne.

### Emplacement des données

Les données utilisateur (base de données, licence activée, sauvegardes,
journaux) sont **toujours séparées** du dossier d'installation de
l'application, afin qu'une mise à jour ne les efface jamais :

| Donnée | Emplacement (Windows) |
|---|---|
| Base de données SQLite | `%APPDATA%\StockManager\stockmanager.db` |
| Sauvegardes | `%APPDATA%\StockManager\backups\` (dossier configurable dans Administration → Sauvegardes) |
| Journaux applicatifs | `%APPDATA%\StockManager\logs\stockmanager.log` (rotation automatique) |
| Licence activée | dans la base de données elle-même (jamais un fichier séparé après activation) |

### Sauvegarde et restauration

Dans **Administration → Sauvegardes** : sauvegarde manuelle immédiate, ou
sauvegarde automatique planifiée (quotidienne/hebdomadaire, dossier et
rétention configurables). La restauration crée toujours automatiquement une
sauvegarde de sécurité de l'état actuel avant de remplacer la base ; un
redémarrage de l'application est demandé après une restauration réussie.

### Mise à jour

Installer une nouvelle version par-dessus l'ancienne (nouvel exécutable de
`StockManager-Setup-<version>.exe`) : le dossier d'installation est
remplacé, mais **jamais** le contenu de `%APPDATA%\StockManager\` (base,
licence, sauvegardes, journaux), qui vit dans un emplacement totalement
distinct. Si le schéma de base de données a évolué, les migrations
nécessaires s'appliquent automatiquement au démarrage suivant.

### Diagnostic

En cas de problème, consulter `%APPDATA%\StockManager\logs\stockmanager.log`
(journal texte, conservé même après fermeture de l'application — aucune
fenêtre de console n'apparaît en usage normal). Toute erreur inattendue
affiche un message compréhensible à l'écran plutôt qu'un plantage silencieux
ou une trace technique brute ; le détail technique correspondant est
toujours écrit dans ce journal.

### Désinstallation

Depuis le Panneau de configuration Windows (« Applications » /
« Programmes et fonctionnalités ») ou le raccourci créé dans le menu
Démarrer. Les données utilisateur (`%APPDATA%\StockManager\`) ne sont
**jamais** supprimées automatiquement par la désinstallation — à retirer
manuellement si elles ne sont plus nécessaires.

---

## Version développeur

### Prérequis

- Python 3.11+

### Installation

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Copier `.env.example` en `.env` pour surcharger la configuration par défaut
si besoin (chemin de base, niveau de log, devise) — fichier de confort pour
le développement uniquement, jamais utilisé ni embarqué par le package
client.

### Lancer l'application

```bash
python -m app.main
```

Au premier lancement, le schéma de base de données est créé (migrations
Alembic) et les données de référence (rôles, permissions) sont initialisées
automatiquement — identique au comportement de la version packagée.

### Lancer les tests

```bash
pytest
```

Sous Linux sans serveur graphique, préfixer par `QT_QPA_PLATFORM=offscreen`.

### Migrations de base de données

Le schéma est géré par [Alembic](https://alembic.sqlalchemy.org/).

```bash
# Générer une nouvelle migration après modification des modèles
alembic revision --autogenerate -m "description du changement"

# Appliquer les migrations (fait automatiquement au démarrage de l'application)
alembic upgrade head

# Vérifier l'absence de dérive entre les modèles et la dernière migration
alembic check
```

### Licences (développement/tests)

Le générateur de licences (`license_generator/`) est un outil séparé,
détenteur de la clé privée Ed25519 de signature — voir
[`license_generator/README.md`](license_generator/README.md). Il n'est
jamais importé par le code client (`app/`) et n'est jamais inclus dans le
package distribué (voir [`packaging/README.md`](packaging/README.md),
section sécurité).

### Packaging Windows

Voir [`packaging/README.md`](packaging/README.md) pour la configuration
PyInstaller (`stockmanager.spec`), l'installateur Inno Setup et la
procédure de build complète.

### Structure du projet

```text
app/
├── main.py                # point d'entrée
├── version.py              # version applicative (source unique)
├── config/                 # configuration centralisée (Settings)
├── models/                 # modèles SQLAlchemy
├── repositories/           # couche d'accès aux données
├── services/                # cas d'usage métier (dont licensing/, dashboard/)
├── db/                       # session, initialisation, seed des données de référence
├── security/                  # hachage des mots de passe (Argon2)
├── utils/                      # logging, exceptions, gestion d'erreurs, arrondi monétaire, chemins runtime
├── views/                      # fenêtre principale et pages PySide6
└── resources/                  # feuille de style, icônes
migrations/                     # migrations Alembic
license_generator/               # outil séparé de génération de licences (jamais packagé avec le client)
packaging/                        # configuration PyInstaller/Inno Setup, scripts de build
tests/                              # tests pytest
```
