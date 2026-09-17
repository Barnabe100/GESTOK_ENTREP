# StockManager Desktop

Application desktop de gestion de stock (Python, PySide6, SQLAlchemy, SQLite).

Le cahier des charges complet se trouve dans
[`Cahier_des_charges_final_StockManager.md`](Cahier_des_charges_final_StockManager.md).

## État du projet

**Phase 1 — Socle technique** (implémentée) : structure du projet, configuration,
modèles SQLAlchemy validés, migrations Alembic, connexion SQLite (foreign keys
activées), logging, gestion centralisée des erreurs, fenêtre principale
PySide6 et navigation de base.

Les fonctionnalités métier (ventes, entrées, sorties, inventaires, rapports,
licences) seront implémentées dans les phases suivantes, une fois validées.

## Prérequis

- Python 3.11+

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
```

Copier `.env.example` en `.env` pour surcharger la configuration par défaut
si besoin (chemin de base, niveau de log, devise).

## Lancer l'application

```bash
python -m app.main
```

Au premier lancement, le schéma de base de données est créé (migrations
Alembic) et les données de référence (rôles, permissions) sont initialisées
automatiquement.

## Lancer les tests

```bash
pytest
```

Sous Linux sans serveur graphique, préfixer par `QT_QPA_PLATFORM=offscreen`.

## Migrations de base de données

Le schéma est géré par [Alembic](https://alembic.sqlalchemy.org/).

```bash
# Générer une nouvelle migration après modification des modèles
alembic revision --autogenerate -m "description du changement"

# Appliquer les migrations (fait automatiquement au démarrage de l'application)
alembic upgrade head
```

## Structure du projet

```text
app/
├── main.py            # point d'entrée
├── config/            # configuration centralisée (Settings)
├── models/            # modèles SQLAlchemy (schéma validé, 20 tables)
├── repositories/       # couche d'accès aux données (interfaces + SQLAlchemy)
├── services/           # cas d'usage métier (vide en Phase 1)
├── db/                 # session, initialisation, seed des données de référence
├── security/            # hachage des mots de passe (Argon2)
├── utils/                # logging, exceptions, gestion d'erreurs, arrondi monétaire
├── views/                # fenêtre principale et pages PySide6
└── resources/            # feuille de style, icônes
migrations/               # migrations Alembic
tests/                     # tests pytest
```
