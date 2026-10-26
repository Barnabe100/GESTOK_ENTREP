"""Lot B (compatibilité Alembic/schéma PostgreSQL) : application des
migrations sur une base PostgreSQL 16.15 neuve, et vérification que le
schéma produit respecte les mêmes règles métier que sur SQLite.

Base/rôle de test dédiés (jamais la base applicative, jamais une base
client) : si le serveur ou ces identifiants ne sont pas disponibles, les
tests sont ignorés proprement (``pytest.skip``), jamais présentés comme un
échec de l'application — voir aussi ``tests/test_db_session.py`` pour le
même principe appliqué au socle de connexion (Lot A).

SQLite : voir ``tests/test_migration_location_client_facultatif.py`` et
``tests/test_models_schema.py`` pour les tests de migration déjà existants
sur ce moteur (non dupliqués ici) ; ``test_sqlite_migrations_apply_on_fresh_database``
ci-dessous n'ajoute qu'une vérification de non-régression explicite pour ce
lot : une base neuve migre toujours intégralement sur SQLite après les
changements de ``migrations/env.py``.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.init_db import _alembic_config, init_database

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
# Jamais de valeur de repli en dur ici (même pour un rôle de test) : voir
# PostgreSQLConnectionConfig.resolve_password — un mot de passe absent doit
# toujours échouer explicitement (ou, pour un test, être ignoré proprement),
# jamais retomber silencieusement sur une valeur codée en source.
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_LOT_B"


def test_sqlite_migrations_apply_on_fresh_database(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-régression explicite (Lot B) : les changements apportés à
    ``migrations/env.py`` (rendu conditionnel de ``render_as_batch`` et
    conversion de l'URL en chaîne) ne doivent jamais empêcher une base
    SQLite neuve de migrer intégralement jusqu'à la tête."""
    settings = Settings(
        environment="test", db_path=tmp_path / "fresh.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
    )
    db_session_module.reset_engine_cache()
    init_database(settings)

    engine = db_session_module.get_engine(settings)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert revision == "0017"
    db_session_module.reset_engine_cache()


# -- correctif : mot de passe PostgreSQL percent-encodé (%40, %21...) --------------
#
# alembic.config.Config stocke ses options dans configparser.ConfigParser,
# dont l'interpolation par défaut (BasicInterpolation) interprète tout « % »
# isolé comme le début d'une référence — un mot de passe PostgreSQL
# contenant un caractère spécial (ex. « @ », « ! ») percent-encodé par
# ``URL.render_as_string`` (« %40 », « %21 ») y levait auparavant
# ``ValueError: invalid interpolation syntax`` dès ``_alembic_config``,
# avant toute tentative de connexion — reproduit et corrigé ici.


def test_alembic_config_accepts_percent_encoded_password_characters() -> None:
    """Aucun serveur requis : reproduit directement le défaut constaté sur
    Windows (``ValueError: invalid interpolation syntax``) avec des mots de
    passe fictifs contenant ``%40``/``%21`` une fois percent-encodés."""
    import tempfile
    from pathlib import Path as _Path

    for fake_password in ("P@ssword", "Secret!123", "P@ss!word", "100%Sûr"):
        with tempfile.TemporaryDirectory() as tmp:
            env_var = "STOCKMANAGER_TEST_ALEMBIC_PW"
            os.environ[env_var] = fake_password
            try:
                settings = Settings(
                    environment="test", db_path=_Path(tmp) / "unused.db",
                    log_dir=_Path(tmp) / "logs", log_level="INFO", default_currency="XOF",
                    db_backend="postgresql",
                    postgresql=PostgreSQLConnectionConfig(
                        host="127.0.0.1", port=5432, database="db", username="user",
                        password_env_var=env_var,
                    ),
                )
                # Ne doit jamais lever — c'est exactement le défaut corrigé.
                config = _alembic_config(settings)
                # La valeur relue via get_section (chemin réellement utilisé
                # par migrations/env.py::run_migrations_online, pas
                # seulement get_main_option) doit redonner l'URL
                # percent-encodée d'origine, mot de passe intact — pas
                # seulement « ne pas lever ». Calculé ici, avant la
                # suppression de la variable d'environnement ci-dessous.
                section = config.get_section(config.config_ini_section, {})
                expected_url = settings.sqlalchemy_database_uri.render_as_string(hide_password=False)
            finally:
                del os.environ[env_var]

            assert section["sqlalchemy.url"] == expected_url


def test_alembic_config_never_alters_the_sqlalchemy_url_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le correctif ne doit jamais modifier l'URL utilisée par SQLAlchemy
    lui-même (``Settings.sqlalchemy_database_uri``) — uniquement la copie
    transmise à ``Config`` (échappée pour configparser)."""
    import tempfile
    from pathlib import Path as _Path

    env_var = "STOCKMANAGER_TEST_ALEMBIC_PW_2"
    monkeypatch.setenv(env_var, "P@ss!word")
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            environment="test", db_path=_Path(tmp) / "unused.db",
            log_dir=_Path(tmp) / "logs", log_level="INFO", default_currency="XOF",
            db_backend="postgresql",
            postgresql=PostgreSQLConnectionConfig(
                host="127.0.0.1", port=5432, database="db", username="user", password_env_var=env_var,
            ),
        )
        before = settings.sqlalchemy_database_uri.render_as_string(hide_password=False)
        _alembic_config(settings)
        after = settings.sqlalchemy_database_uri.render_as_string(hide_password=False)
        assert before == after
        assert "%%" not in after  # jamais la version échappée côté SQLAlchemy.


@pytest.fixture()
def postgresql_test_schema(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    """Base PostgreSQL de test dédiée, remise à un schéma vide avant chaque
    test (jamais la base applicative ni une base client), puis nettoyée
    après : isolation stricte, cible vérifiée avant toute opération
    destructive (le nom de base est fixé par variable d'environnement,
    jamais déduit implicitement)."""
    if _PG_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )
    monkeypatch.setenv(_PG_PASSWORD_ENV_VAR, _PG_PASSWORD)
    settings = Settings(
        environment="test", db_path=tmp_path / "unused-for-postgresql.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER,
            password_env_var=_PG_PASSWORD_ENV_VAR, connect_timeout_seconds=5,
        ),
    )
    db_session_module.reset_engine_cache()
    try:
        probe_engine = db_session_module.create_db_engine(settings)
        with probe_engine.connect() as connection:
            # Reset explicite, scopé à cette seule base de test (jamais un
            # DROP DATABASE : seul le schéma applicatif de la base de test
            # dédiée est recréé vide).
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            connection.commit()
        probe_engine.dispose()
    except OperationalError as exc:
        db_session_module.reset_engine_cache()
        pytest.skip(f"Serveur PostgreSQL de test non atteignable ({_PG_HOST}:{_PG_PORT}) : {exc}")

    yield settings

    engine = db_session_module.get_engine(settings)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()
    db_session_module.reset_engine_cache()


def test_postgresql_migrations_apply_on_fresh_database(postgresql_test_schema: Settings) -> None:
    """§5 du mandat Lot B : toutes les migrations s'appliquent sans erreur
    sur une base PostgreSQL 16.15 neuve, jusqu'à la tête (0015)."""
    init_database(postgresql_test_schema)

    engine = db_session_module.get_engine(postgresql_test_schema)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert revision == "0017"


def test_postgresql_partial_unique_index_exists_with_expected_condition(
    postgresql_test_schema: Settings,
) -> None:
    """La migration 0008 doit produire, sur PostgreSQL, un index unique
    partiel restreint aux articles actifs — identique à la restriction déjà
    appliquée via ``sqlite_where`` sur SQLite (voir le correctif
    ``postgresql_where`` de ce lot)."""
    init_database(postgresql_test_schema)
    engine = db_session_module.get_engine(postgresql_test_schema)
    with engine.connect() as connection:
        indexdef = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'ix_articles_code_barres_actif_unique'"
            )
        ).scalar()
    assert indexdef is not None
    assert "UNIQUE" in indexdef
    assert "WHERE" in indexdef
    assert "ACTIF" in indexdef


def test_postgresql_partial_unique_index_enforces_business_rule(
    postgresql_test_schema: Settings,
) -> None:
    """Vérification fonctionnelle (pas seulement structurelle) : deux
    articles ACTIFS ne peuvent jamais partager le même code-barres, mais un
    actif et un inactif le peuvent — exactement la même règle que sur
    SQLite (voir ``tests/test_models_schema.py`` côté SQLite)."""
    init_database(postgresql_test_schema)
    engine = db_session_module.get_engine(postgresql_test_schema)

    def _insert_article(connection, ref: str, code_barres: str, statut: str) -> None:
        connection.execute(
            text(
                "INSERT INTO articles (reference, designation, category_id, unite, "
                "prix_achat_defaut, prix_vente, cout_moyen_pondere, stock_actuel, stock_min, "
                "code_barres, statut, mode_gestion, date_creation, date_modification) "
                "VALUES (:ref, :ref, :category_id, 'unite', 0, 0, 0, 0, 0, "
                ":code_barres, :statut, 'VENTE', now(), now())"
            ),
            {"ref": ref, "category_id": category_id, "code_barres": code_barres, "statut": statut},
        )

    with engine.connect() as connection:
        category_id = connection.execute(
            text(
                "INSERT INTO categories (nom, statut, date_creation, date_modification) "
                "VALUES ('Lot B test', 'ACTIF', now(), now()) RETURNING id"
            )
        ).scalar()
        connection.commit()

        _insert_article(connection, "LOTB-ACTIF-1", "LOTB-CB-1", "ACTIF")
        connection.commit()

        with pytest.raises(Exception):
            with connection.begin():
                _insert_article(connection, "LOTB-ACTIF-2", "LOTB-CB-1", "ACTIF")

    with engine.connect() as connection:
        _insert_article(connection, "LOTB-INACTIF-1", "LOTB-CB-2", "INACTIF")
        connection.commit()
        # Ne doit pas lever : un actif et un inactif peuvent partager le code-barres.
        _insert_article(connection, "LOTB-ACTIF-3", "LOTB-CB-2", "ACTIF")
        connection.commit()


def test_postgresql_numeric_precision_matches_models(postgresql_test_schema: Settings) -> None:
    """§4.D du mandat : ``Numeric(14,2)``/``Numeric(14,3)`` doivent être
    préservés tels quels sur PostgreSQL, jamais convertis en ``float`` ni
    en une précision différente."""
    init_database(postgresql_test_schema)
    engine = db_session_module.get_engine(postgresql_test_schema)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT column_name, numeric_precision, numeric_scale "
                "FROM information_schema.columns "
                "WHERE table_name = 'articles' AND column_name IN "
                "('prix_vente', 'prix_achat_defaut', 'cout_moyen_pondere', "
                "'stock_actuel', 'stock_min')"
            )
        ).all()
    by_column = {row[0]: (row[1], row[2]) for row in rows}
    assert by_column["prix_vente"] == (14, 2)
    assert by_column["prix_achat_defaut"] == (14, 2)
    assert by_column["cout_moyen_pondere"] == (14, 2)
    assert by_column["stock_actuel"] == (14, 3)
    assert by_column["stock_min"] == (14, 3)


def test_postgresql_foreign_keys_and_cascade_are_created(postgresql_test_schema: Settings) -> None:
    """§4.D : les clés étrangères (et leurs règles ON DELETE CASCADE,
    utilisées par ``user_roles``) doivent exister réellement sur
    PostgreSQL, pas seulement sur SQLite."""
    init_database(postgresql_test_schema)
    engine = db_session_module.get_engine(postgresql_test_schema)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT conname, confdeltype FROM pg_constraint "
                "WHERE conrelid = 'user_roles'::regclass AND contype = 'f'"
            )
        ).all()
    assert len(rows) == 2
    # 'c' = CASCADE (voir pg_constraint.confdeltype) pour les deux FK.
    assert all(row[1] == "c" for row in rows)


def test_postgresql_revision_matches_actual_schema_state(postgresql_test_schema: Settings) -> None:
    """§5 : cohérence entre la révision Alembic enregistrée et l'état réel
    du schéma — après ``init_database``, la table la plus récente (module
    Locations, migration 0014/0015) doit exister si et seulement si la
    révision enregistrée est bien la tête (0015)."""
    init_database(postgresql_test_schema)
    engine = db_session_module.get_engine(postgresql_test_schema)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        locations_table_exists = connection.execute(
            text("SELECT to_regclass('public.locations') IS NOT NULL")
        ).scalar()
    assert revision == "0017"
    assert locations_table_exists is True


# -- validation réelle contre un serveur PostgreSQL (correctif percent-encoding) ---

# Mot de passe fictif, jamais le mot de passe réel d'aucun poste client ni
# de la base applicative — appliqué temporairement au seul rôle de test
# dédié, puis restauré en toute circonstance (voir la fixture ci-dessous).
# Contient volontairement les deux caractères signalés dans le défaut
# (« @ » -> %40, « ! » -> %21).
_FAKE_SPECIAL_CHARACTER_PASSWORD = "P@ssw0rd!Test"
_SPECIAL_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_LOT_B_SPECIAL"


def _set_role_password(connection, password: str) -> None:
    # ALTER ROLE n'accepte pas de paramètre lié pour le mot de passe —
    # ``_PG_USER``/``password`` sont ici des constantes de test fixes,
    # jamais une entrée externe : l'échappement des quotes suffit.
    escaped = password.replace("'", "''")
    connection.execute(text(f"ALTER ROLE {_PG_USER} WITH PASSWORD '{escaped}'"))


@pytest.fixture()
def postgresql_test_schema_with_special_password(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
    """Même principe que ``postgresql_test_schema``, mais le mot de passe du
    rôle de test est temporairement remplacé par un mot de passe fictif
    contenant des caractères spéciaux (jamais le mot de passe réel d'un
    poste client) — seul moyen de valider réellement, de bout en bout
    (authentification PostgreSQL comprise), le correctif du défaut constaté
    sur Windows. Le mot de passe d'origine est restauré en toute
    circonstance, y compris si le test échoue."""
    if _PG_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )
    monkeypatch.setenv(_PG_PASSWORD_ENV_VAR, _PG_PASSWORD)
    real_password_settings = Settings(
        environment="test", db_path=tmp_path / "unused-for-postgresql.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER,
            password_env_var=_PG_PASSWORD_ENV_VAR, connect_timeout_seconds=5,
        ),
    )
    db_session_module.reset_engine_cache()
    try:
        probe_engine = db_session_module.create_db_engine(real_password_settings)
        with probe_engine.connect() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            _set_role_password(connection, _FAKE_SPECIAL_CHARACTER_PASSWORD)
            connection.commit()
        probe_engine.dispose()
    except OperationalError as exc:
        db_session_module.reset_engine_cache()
        pytest.skip(f"Serveur PostgreSQL de test non atteignable ({_PG_HOST}:{_PG_PORT}) : {exc}")
    db_session_module.reset_engine_cache()

    monkeypatch.setenv(_SPECIAL_PASSWORD_ENV_VAR, _FAKE_SPECIAL_CHARACTER_PASSWORD)
    special_password_settings = Settings(
        environment="test", db_path=tmp_path / "unused-for-postgresql.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER,
            password_env_var=_SPECIAL_PASSWORD_ENV_VAR, connect_timeout_seconds=5,
        ),
    )

    try:
        yield special_password_settings
    finally:
        db_session_module.reset_engine_cache()
        restore_engine = db_session_module.create_db_engine(special_password_settings)
        with restore_engine.connect() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            _set_role_password(connection, _PG_PASSWORD)
            connection.commit()
        restore_engine.dispose()
        db_session_module.reset_engine_cache()


def test_postgresql_migrations_apply_with_percent_encoded_special_character_password(
    postgresql_test_schema_with_special_password: Settings,
) -> None:
    """Validation réelle de bout en bout (serveur PostgreSQL réel,
    authentification comprise) du défaut constaté sur Windows : les
    migrations doivent s'appliquer jusqu'à la tête même lorsque le mot de
    passe PostgreSQL contient des caractères percent-encodés par
    SQLAlchemy (``%40``, ``%21``) dans l'URL transmise à Alembic."""
    settings = postgresql_test_schema_with_special_password
    url = settings.sqlalchemy_database_uri.render_as_string(hide_password=False)
    assert "%40" in url or "%21" in url  # confirme que le mot de passe est bien percent-encodé dans l'URL testée.

    init_database(settings)  # ne doit jamais lever ValueError: invalid interpolation syntax.

    engine = db_session_module.get_engine(settings)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert revision == "0017"
