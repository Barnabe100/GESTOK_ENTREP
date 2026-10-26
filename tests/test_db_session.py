import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.session import create_db_engine, get_engine, session_scope
from app.models.rbac import Role


def test_engine_connects_to_sqlite_file(test_settings: Settings) -> None:
    engine = get_engine(test_settings)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar()
    assert result == 1
    assert test_settings.db_path.exists()


def test_foreign_keys_pragma_is_enabled_on_every_connection(test_settings: Settings) -> None:
    engine = get_engine(test_settings)
    with engine.connect() as connection:
        value = connection.execute(text("PRAGMA foreign_keys")).scalar()
    assert value == 1


def test_session_scope_commits_on_success(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        session.add(Role(nom="TestRole", description="rôle de test"))

    with session_scope(initialized_db) as session:
        role = session.query(Role).filter_by(nom="TestRole").one_or_none()
    assert role is not None


def test_session_scope_rolls_back_on_exception(initialized_db: Settings) -> None:
    class _Boom(Exception):
        pass

    try:
        with session_scope(initialized_db) as session:
            session.add(Role(nom="RoleQuiDoitDisparaitre", description=""))
            session.flush()
            raise _Boom("échec volontaire")
    except _Boom:
        pass

    with session_scope(initialized_db) as session:
        role = session.query(Role).filter_by(nom="RoleQuiDoitDisparaitre").one_or_none()
    assert role is None


# -- Lot A (socle multi-moteur) : options conditionnelles au dialecte, sans serveur ---
#
# Ces tests n'exigent aucun serveur PostgreSQL réel : ``create_engine`` ne se
# connecte jamais tant qu'aucune requête n'est exécutée (SQLAlchemy est
# toujours paresseux à la construction) — seuls les arguments transmis sont
# vérifiés, via un espion posé sur ``sqlalchemy.create_engine``.


def _make_postgresql_settings(tmp_path, *, connect_timeout_seconds: int = 7) -> Settings:
    return Settings(
        environment="test",
        db_path=tmp_path / "unused-for-postgresql-backend.db",
        log_dir=tmp_path / "logs",
        log_level="DEBUG",
        default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host="pg.example.com", port=5432, database="stockmanager", username="smuser",
            connect_timeout_seconds=connect_timeout_seconds,
        ),
    )


def test_postgresql_engine_receives_no_sqlite_option(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    from sqlalchemy import create_engine as real_create_engine

    def _spy_create_engine(url, **kwargs):
        captured.update(kwargs)
        return real_create_engine(url, **kwargs)

    monkeypatch.setenv("STOCKMANAGER_DB_PASSWORD", "s3cret")
    monkeypatch.setattr("sqlalchemy.create_engine", _spy_create_engine)

    settings = _make_postgresql_settings(tmp_path)
    engine = create_db_engine(settings)

    assert "check_same_thread" not in captured.get("connect_args", {})
    assert captured["connect_args"]["connect_timeout"] == 7
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_postgresql_engine_enables_pool_pre_ping_and_recycle(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chantier A (audit multi-postes) : une connexion du pool restée
    inactive peut être fermée silencieusement par un intermédiaire réseau
    (pare-feu/routeur) sans que l'application ne le sache avant de tenter de
    la réutiliser — ``pool_pre_ping`` doit être actif pour PostgreSQL."""
    captured: dict = {}
    from sqlalchemy import create_engine as real_create_engine

    def _spy_create_engine(url, **kwargs):
        captured.update(kwargs)
        return real_create_engine(url, **kwargs)

    monkeypatch.setenv("STOCKMANAGER_DB_PASSWORD", "s3cret")
    monkeypatch.setattr("sqlalchemy.create_engine", _spy_create_engine)

    settings = _make_postgresql_settings(tmp_path)
    create_db_engine(settings)

    assert captured["pool_pre_ping"] is True
    assert captured["pool_recycle"] == 1800


def test_sqlite_engine_still_receives_check_same_thread(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-régression explicite : l'ajout de la branche PostgreSQL ne doit
    jamais altérer les options déjà appliquées pour SQLite."""
    captured: dict = {}
    from sqlalchemy import create_engine as real_create_engine

    def _spy_create_engine(url, **kwargs):
        captured.update(kwargs)
        return real_create_engine(url, **kwargs)

    monkeypatch.setattr("sqlalchemy.create_engine", _spy_create_engine)

    settings = Settings(
        environment="test", db_path=tmp_path / "stockmanager.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
    )
    engine = create_db_engine(settings)

    assert captured["connect_args"] == {"check_same_thread": False}
    assert "connect_timeout" not in captured["connect_args"]
    assert "pool_pre_ping" not in captured
    assert "pool_recycle" not in captured
    assert engine.dialect.name == "sqlite"


def test_create_db_engine_raises_explicitly_when_postgresql_config_missing(tmp_path) -> None:
    settings = Settings(
        environment="test", db_path=tmp_path / "unused.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql", postgresql=None,
    )
    with pytest.raises(ValueError, match="postgresql"):
        create_db_engine(settings)


# -- Lot A : intégration réelle contre un serveur PostgreSQL atteignable -------------
#
# Serveur utilisé pour cette exécution : PostgreSQL 16.15 (seule version
# disponible dans cet environnement de développement) — la cible officielle
# PostgreSQL 18.x retenue pour ce chantier reste à valider séparément dans un
# environnement qui la fournit réellement (voir le rapport de ce lot). Ces
# tests ne portent que sur le socle de connexion/session lui-même (URL, pool,
# délai de connexion, fermeture), indépendant de cette précision de version ;
# ils ne valident ni le schéma ni les migrations (réservés au Lot B).
#
# Base/rôle de test dédiés (jamais la base applicative) : si le serveur ou
# ces identifiants ne sont pas disponibles, le test est ignoré proprement
# (``pytest.skip``), jamais présenté comme un échec de l'application.

_PG_INTEGRATION_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_INTEGRATION_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_INTEGRATION_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_INTEGRATION_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
# Jamais de valeur de repli en dur ici (même pour un rôle de test) : voir
# PostgreSQLConnectionConfig.resolve_password — un mot de passe absent doit
# toujours échouer explicitement (ou, pour un test, être ignoré proprement),
# jamais retomber silencieusement sur une valeur codée en source.
_PG_INTEGRATION_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_INTEGRATION_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE"


@pytest.fixture()
def postgresql_integration_settings(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    if _PG_INTEGRATION_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )
    monkeypatch.setenv(_PG_INTEGRATION_PASSWORD_ENV_VAR, _PG_INTEGRATION_PASSWORD)
    settings = Settings(
        environment="test", db_path=tmp_path / "unused-for-postgresql.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_INTEGRATION_HOST, port=_PG_INTEGRATION_PORT, database=_PG_INTEGRATION_DB,
            username=_PG_INTEGRATION_USER, password_env_var=_PG_INTEGRATION_PASSWORD_ENV_VAR,
            connect_timeout_seconds=5,
        ),
    )
    db_session_module.reset_engine_cache()
    try:
        probe_engine = create_db_engine(settings)
        with probe_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        probe_engine.dispose()
    except OperationalError as exc:
        db_session_module.reset_engine_cache()
        pytest.skip(f"Serveur PostgreSQL de test non atteignable ({_PG_INTEGRATION_HOST}:{_PG_INTEGRATION_PORT}) : {exc}")

    yield settings
    db_session_module.reset_engine_cache()


def test_postgresql_engine_connects_for_real(postgresql_integration_settings: Settings) -> None:
    engine = get_engine(postgresql_integration_settings)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar()
    assert result == 1


def test_postgresql_engine_reports_psycopg3_dialect(postgresql_integration_settings: Settings) -> None:
    engine = get_engine(postgresql_integration_settings)
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"


def test_postgresql_session_scope_commits_on_success(postgresql_integration_settings: Settings) -> None:
    """Même garantie transactionnelle que pour SQLite (voir
    ``test_session_scope_commits_on_success`` ci-dessus), vérifiée ici avec
    un serveur PostgreSQL réel plutôt qu'avec le schéma applicatif (réservé
    au Lot B) : une table jetable, créée et supprimée par le test
    lui-même."""
    engine = get_engine(postgresql_integration_settings)
    with engine.connect() as connection:
        connection.execute(text("DROP TABLE IF EXISTS lot_a_scratch"))
        connection.execute(text("CREATE TABLE lot_a_scratch (id serial PRIMARY KEY, label text)"))
        connection.commit()
    try:
        with session_scope(postgresql_integration_settings) as session:
            session.execute(text("INSERT INTO lot_a_scratch (label) VALUES ('committed')"))

        with session_scope(postgresql_integration_settings) as session:
            rows = session.execute(text("SELECT label FROM lot_a_scratch")).scalars().all()
        assert rows == ["committed"]
    finally:
        with engine.connect() as connection:
            connection.execute(text("DROP TABLE IF EXISTS lot_a_scratch"))
            connection.commit()


def test_postgresql_session_scope_rolls_back_on_exception(postgresql_integration_settings: Settings) -> None:
    engine = get_engine(postgresql_integration_settings)
    with engine.connect() as connection:
        connection.execute(text("DROP TABLE IF EXISTS lot_a_scratch_rollback"))
        connection.execute(text("CREATE TABLE lot_a_scratch_rollback (id serial PRIMARY KEY, label text)"))
        connection.commit()

    class _Boom(Exception):
        pass

    try:
        try:
            with session_scope(postgresql_integration_settings) as session:
                session.execute(text("INSERT INTO lot_a_scratch_rollback (label) VALUES ('should-vanish')"))
                session.flush()
                raise _Boom("échec volontaire")
        except _Boom:
            pass

        with session_scope(postgresql_integration_settings) as session:
            rows = session.execute(text("SELECT label FROM lot_a_scratch_rollback")).scalars().all()
        assert rows == []
    finally:
        with engine.connect() as connection:
            connection.execute(text("DROP TABLE IF EXISTS lot_a_scratch_rollback"))
            connection.commit()


def test_postgresql_connection_fails_explicitly_with_wrong_password(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§3.B : une erreur de connexion doit être explicite — jamais un blocage
    indéfini ni une exception générique illisible — et ne doit jamais faire
    apparaître le mot de passe tenté dans le message d'erreur."""
    monkeypatch.setenv("STOCKMANAGER_TEST_WRONG_PG_PASSWORD", "mot-de-passe-invalide")
    settings = Settings(
        environment="test", db_path=tmp_path / "unused.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_INTEGRATION_HOST, port=_PG_INTEGRATION_PORT, database=_PG_INTEGRATION_DB,
            username=_PG_INTEGRATION_USER, password_env_var="STOCKMANAGER_TEST_WRONG_PG_PASSWORD",
            connect_timeout_seconds=5,
        ),
    )
    db_session_module.reset_engine_cache()
    engine = create_db_engine(settings)
    try:
        with pytest.raises(OperationalError) as exc_info:
            with engine.connect():
                pass
        assert "mot-de-passe-invalide" not in str(exc_info.value)
    finally:
        engine.dispose()
        db_session_module.reset_engine_cache()


def test_postgresql_connection_fails_explicitly_for_unreachable_host(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Indisponibilité réseau (§6 du mandat produit) : un hôte inexistant
    doit échouer dans un délai borné (``connect_timeout_seconds``), jamais
    bloquer l'application indéfiniment."""
    import time

    monkeypatch.setenv("STOCKMANAGER_TEST_UNREACHABLE_PG_PASSWORD", "peu-importe")
    settings = Settings(
        environment="test", db_path=tmp_path / "unused.db",
        log_dir=tmp_path / "logs", log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            # Adresse non routable (RFC 5737, bloc réservé à la documentation) :
            # garantit un échec de connexion, jamais une réussite accidentelle.
            host="192.0.2.1", port=5432, database="stockmanager", username="smuser",
            password_env_var="STOCKMANAGER_TEST_UNREACHABLE_PG_PASSWORD",
            connect_timeout_seconds=3,
        ),
    )
    db_session_module.reset_engine_cache()
    engine = create_db_engine(settings)
    try:
        started = time.monotonic()
        with pytest.raises(OperationalError):
            with engine.connect():
                pass
        elapsed = time.monotonic() - started
        assert elapsed < 15  # largement au-delà du délai configuré (3 s), jamais un blocage indéfini
    finally:
        engine.dispose()
        db_session_module.reset_engine_cache()
