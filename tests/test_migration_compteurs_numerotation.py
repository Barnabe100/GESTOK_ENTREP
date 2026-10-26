"""Tests de la migration 0017 (compteurs de numérotation atomique) : audit
multi-poste — voir ``migrations/versions/0017_compteurs_numerotation.py``
et ``app.models.counters.CompteurNumerotation``.

Même convention que ``tests/test_migration_location_client_facultatif.py``
(base construite en deux temps, schéma 0016 puis migration vers 0017) :
vérifie explicitement que l'initialisation des compteurs ne réattribue
jamais un numéro déjà porté par un document existant, même lorsque le
nombre de lignes (``COUNT(*)``) est inférieur au plus grand numéro déjà
attribué (brouillon supprimé) — exactement le risque que ce lot vise à
éliminer.
"""
from datetime import datetime

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.utils.runtime_paths import app_root


def _alembic_config(db_path) -> Config:
    root = app_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _insert_role_and_user(conn, now: str) -> int:
    conn.execute(sa.text("INSERT INTO roles (nom, description) VALUES ('Administrateur', 'x')"))
    role_id = conn.execute(sa.text("SELECT id FROM roles WHERE nom='Administrateur'")).scalar()
    conn.execute(
        sa.text(
            "INSERT INTO users (username, password_hash, role_id, actif, must_change_password, "
            "date_creation, date_modification) VALUES ('u_migration', 'h', :role_id, 1, 0, :now, :now)"
        ),
        {"role_id": role_id, "now": now},
    )
    return conn.execute(sa.text("SELECT id FROM users WHERE username='u_migration'")).scalar()


def test_upgrade_creates_one_counter_row_per_document_type_on_fresh_database(tmp_path) -> None:
    db_path = tmp_path / "migration_test.db"
    config = _alembic_config(db_path)

    command.upgrade(config, "head")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        rows = conn.execute(
            sa.text("SELECT type_document, valeur FROM compteurs_numerotation ORDER BY type_document")
        ).fetchall()
    assert {r.type_document: r.valeur for r in rows} == {
        "ENT": 0, "INV": 0, "LOC": 0, "SOR": 0, "VNT": 0,
    }


def test_upgrade_initializes_counter_from_max_existing_numero_not_row_count(tmp_path) -> None:
    """Scénario central de ce lot : seule ``VNT-000005`` existe (les
    brouillons 1 à 4 ont été créés puis supprimés sans laisser de trace,
    voir ``SaleService.create_sale``) — ``COUNT(*)`` vaudrait 1, ce qui
    ferait réattribuer ``VNT-000002`` au prochain document avec l'ancien
    mécanisme. Le compteur doit être initialisé à 5 (le plus grand numéro
    déjà attribué), jamais à 1."""
    db_path = tmp_path / "migration_test.db"
    config = _alembic_config(db_path)
    command.upgrade(config, "0016")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    now = datetime.utcnow().isoformat()
    with engine.begin() as conn:
        user_id = _insert_role_and_user(conn, now)
        conn.execute(
            sa.text(
                "INSERT INTO ventes (numero, date, user_id, statut, total, montant_paye, "
                "statut_paiement, date_creation, date_modification) VALUES "
                "('VNT-000005', '2026-01-01', :user_id, 'BROUILLON', 100, 0, 'NON_PAYEE', :now, :now)"
            ),
            {"user_id": user_id, "now": now},
        )

    command.upgrade(config, "head")

    with engine.begin() as conn:
        valeur = conn.execute(
            sa.text("SELECT valeur FROM compteurs_numerotation WHERE type_document='VNT'")
        ).scalar()
    assert valeur == 5


def test_upgrade_preserves_existing_documents_unchanged(tmp_path) -> None:
    """Migration purement additive : aucun document existant n'est modifié."""
    db_path = tmp_path / "migration_test.db"
    config = _alembic_config(db_path)
    command.upgrade(config, "0016")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    now = datetime.utcnow().isoformat()
    with engine.begin() as conn:
        user_id = _insert_role_and_user(conn, now)
        conn.execute(
            sa.text(
                "INSERT INTO ventes (numero, date, user_id, statut, total, montant_paye, "
                "statut_paiement, date_creation, date_modification) VALUES "
                "('VNT-000042', '2026-01-01', :user_id, 'BROUILLON', 100, 0, 'NON_PAYEE', :now, :now)"
            ),
            {"user_id": user_id, "now": now},
        )

    command.upgrade(config, "head")

    with engine.begin() as conn:
        row = conn.execute(
            sa.text("SELECT numero, statut, total FROM ventes WHERE numero = 'VNT-000042'")
        ).fetchone()
    assert row is not None
    assert row.statut == "BROUILLON"
    assert row.total == 100


def test_downgrade_removes_compteurs_table_only(tmp_path) -> None:
    db_path = tmp_path / "migration_test.db"
    config = _alembic_config(db_path)
    command.upgrade(config, "head")

    command.downgrade(config, "0016")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    table_names = sa.inspect(engine).get_table_names()
    assert "compteurs_numerotation" not in table_names
    assert "ventes" in table_names
