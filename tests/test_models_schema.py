from sqlalchemy import inspect

from app.config.settings import Settings
from app.db.session import get_engine
from app.models import Base

EXPECTED_TABLES = {
    "roles",
    "permissions",
    "role_permissions",
    "users",
    "user_roles",
    "categories",
    "fournisseurs",
    "clients",
    "motifs_sortie",
    "articles",
    "entrees",
    "entree_lignes",
    "sorties",
    "sortie_lignes",
    "ventes",
    "vente_lignes",
    "paiements",
    "mouvements_stock",
    "inventaires",
    "inventaire_lignes",
    "audit_logs",
    "parametres",
    "licences",
}


def test_declarative_metadata_declares_all_23_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert len(EXPECTED_TABLES) == 23


def test_alembic_migration_creates_all_tables_in_sqlite(initialized_db: Settings) -> None:
    engine = get_engine(initialized_db)
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())

    assert EXPECTED_TABLES.issubset(actual_tables)
    assert "alembic_version" in actual_tables


def test_alembic_upgrade_head_is_idempotent(initialized_db: Settings) -> None:
    from app.db.init_db import init_database

    # Ré-exécuter l'initialisation ne doit ni échouer ni dupliquer quoi que ce soit.
    init_database(initialized_db)

    engine = get_engine(initialized_db)
    inspector = inspect(engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))


def test_article_reference_has_unique_index(initialized_db: Settings) -> None:
    engine = get_engine(initialized_db)
    inspector = inspect(engine)
    unique_columns = {
        col
        for constraint in inspector.get_unique_constraints("articles")
        for col in constraint["column_names"]
    }
    indexed_unique_columns = {
        col
        for index in inspector.get_indexes("articles")
        if index["unique"]
        for col in index["column_names"]
    }
    assert "reference" in unique_columns or "reference" in indexed_unique_columns


def test_mouvements_stock_date_heure_has_index(initialized_db: Settings) -> None:
    """Lot K : filtres de période (page Mouvements, rapport Mouvements,
    Dashboard) et tri par date décroissante doivent s'appuyer sur un index
    dédié, comme audit_logs.date_heure."""
    engine = get_engine(initialized_db)
    inspector = inspect(engine)
    indexed_columns = {
        col
        for index in inspector.get_indexes("mouvements_stock")
        for col in index["column_names"]
    }
    assert "date_heure" in indexed_columns
