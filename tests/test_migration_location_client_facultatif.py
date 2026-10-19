"""Tests de la migration 0015 (``locations.client_id`` devient facultatif) :
lot « Client facultatif et création rapide depuis une location ».

Contrairement aux migrations précédentes (toutes purement additives), celle-ci
assouplit une contrainte ``NOT NULL`` déjà posée sur une colonne existante —
voir ``migrations/versions/0015_location_client_facultatif.py``. Ces tests
vérifient explicitement, sur une base construite en deux temps (schéma 0014
puis migration vers 0015), qu'une location déjà existante avec un client
traverse la migration sans perte ni altération.
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


def test_client_id_is_nullable_after_upgrade_to_head(tmp_path) -> None:
    db_path = tmp_path / "migration_test.db"
    config = _alembic_config(db_path)

    command.upgrade(config, "head")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    columns = {c["name"]: c["nullable"] for c in sa.inspect(engine).get_columns("locations")}
    assert columns["client_id"] is True


def test_client_id_is_not_nullable_before_this_migration(tmp_path) -> None:
    """Confirme que la contrainte existait bien avant ce lot (0014) — sans
    quoi le test précédent ne démontrerait rien."""
    db_path = tmp_path / "migration_test.db"
    config = _alembic_config(db_path)

    command.upgrade(config, "0014")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    columns = {c["name"]: c["nullable"] for c in sa.inspect(engine).get_columns("locations")}
    assert columns["client_id"] is False


def test_upgrade_preserves_existing_location_with_client(tmp_path) -> None:
    """Une location historique, créée sur le schéma 0014 (client
    obligatoire), doit traverser la migration vers 0015 sans que sa ligne
    ni sa relation client ne soient modifiées ou perdues."""
    db_path = tmp_path / "migration_test.db"
    config = _alembic_config(db_path)
    command.upgrade(config, "0014")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    now = datetime.utcnow().isoformat()
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO roles (nom, description) VALUES ('Administrateur', 'x')"))
        role_id = conn.execute(sa.text("SELECT id FROM roles WHERE nom='Administrateur'")).scalar()
        conn.execute(
            sa.text(
                "INSERT INTO users (username, password_hash, role_id, actif, must_change_password, "
                "date_creation, date_modification) VALUES ('u_migration', 'h', :role_id, 1, 0, :now, :now)"
            ),
            {"role_id": role_id, "now": now},
        )
        user_id = conn.execute(sa.text("SELECT id FROM users WHERE username='u_migration'")).scalar()
        conn.execute(
            sa.text(
                "INSERT INTO clients (nom, statut, date_creation, date_modification) "
                "VALUES ('Client Historique', 'ACTIF', :now, :now)"
            ),
            {"now": now},
        )
        client_id = conn.execute(sa.text("SELECT id FROM clients WHERE nom='Client Historique'")).scalar()
        conn.execute(
            sa.text(
                "INSERT INTO locations (numero, date, client_id, user_id, statut, caution_montant, "
                "caution_rendue, date_creation, date_modification) VALUES "
                "('LOC-HIST', '2026-01-01', :client_id, :user_id, 'BROUILLON', 0, 0, :now, :now)"
            ),
            {"client_id": client_id, "user_id": user_id, "now": now},
        )

    command.upgrade(config, "head")

    with engine.begin() as conn:
        row = conn.execute(
            sa.text("SELECT numero, client_id, statut FROM locations WHERE numero = 'LOC-HIST'")
        ).fetchone()
    assert row is not None
    assert row.client_id == client_id
    assert row.statut == "BROUILLON"


def test_downgrade_restores_not_null_constraint(tmp_path) -> None:
    db_path = tmp_path / "migration_test.db"
    config = _alembic_config(db_path)
    command.upgrade(config, "head")

    command.downgrade(config, "0014")

    engine = sa.create_engine(f"sqlite:///{db_path}")
    columns = {c["name"]: c["nullable"] for c in sa.inspect(engine).get_columns("locations")}
    assert columns["client_id"] is False
