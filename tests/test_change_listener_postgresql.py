"""Tests de ``app.db.change_listener.PostgreSQLChangeListener`` (Chantier D)
contre un serveur PostgreSQL 16.15 réel.

Même convention de fixture que les autres suites PostgreSQL de ce projet
(voir ``tests/test_document_validation_concurrency_postgresql.py``).

Depuis le correctif de revue (résolution du mot de passe via
``PostgreSQLConnectionConfig.resolve_password()``, construction de la
connexion par paramètres séparés plutôt que par interpolation de chaîne),
ce fichier couvre aussi : la résolution depuis le coffre d'identifiants
(via un substitut contrôlé — voir :class:`_FakeCredentialVault`, le coffre
Windows réel ne pouvant pas être exercé dans ce sandbox Linux), la
résolution par variable d'environnement, les mots de passe à caractères
spéciaux, et le comportement après COMMIT/ROLLBACK observé directement via
``PostgreSQLChangeListener.poll()``."""
from __future__ import annotations

import os
import time
from typing import Optional

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.settings import PostgreSQLConnectionConfig, Settings
from app.db import session as db_session_module
from app.db.change_listener import PostgreSQLChangeListener
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from tests.conftest import _full_access_test_licence

_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")
_PG_PASSWORD_ENV_VAR = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_CHANGE_LISTENER"


@pytest.fixture()
def postgresql_initialized_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Settings:
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
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            connection.commit()
        probe_engine.dispose()
    except OperationalError as exc:
        db_session_module.reset_engine_cache()
        pytest.skip(f"Serveur PostgreSQL de test non atteignable ({_PG_HOST}:{_PG_PORT}) : {exc}")

    init_database(settings)
    with db_session_module.session_scope(settings) as session:
        seed_reference_data(session)
        session.add(_full_access_test_licence())

    yield settings

    engine = db_session_module.get_engine(settings)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()
    db_session_module.reset_engine_cache()


def test_poll_returns_empty_set_when_nothing_pending(postgresql_initialized_db: Settings) -> None:
    listener = PostgreSQLChangeListener(postgresql_initialized_db)
    assert listener.poll() == set()
    listener.close()


def test_poll_connects_lazily_on_first_call(postgresql_initialized_db: Settings) -> None:
    listener = PostgreSQLChangeListener(postgresql_initialized_db)
    assert not listener.is_connected
    listener.poll()
    assert listener.is_connected
    listener.close()


def test_poll_receives_a_notification_emitted_by_another_connection(postgresql_initialized_db: Settings) -> None:
    listener = PostgreSQLChangeListener(postgresql_initialized_db)
    listener.poll()  # établit la connexion LISTEN avant l'émission.

    from app.models.catalog import Category

    with db_session_module.session_scope(postgresql_initialized_db) as session:
        session.add(Category(nom="Catégorie listener"))

    time.sleep(0.2)
    assert listener.poll() == {"categories"}
    listener.close()


def test_poll_recovers_after_connection_is_closed_externally(postgresql_initialized_db: Settings) -> None:
    """Simule une coupure réseau : la connexion LISTEN est fermée de
    l'extérieur — le prochain ``poll()`` doit se reconnecter silencieusement
    et redevenir fonctionnel, jamais lever d'exception."""
    listener = PostgreSQLChangeListener(postgresql_initialized_db)
    listener.poll()
    assert listener.is_connected

    listener._connection.close()  # simule une coupure.
    assert listener.poll() == set()  # reconnexion transparente, aucune exception.
    assert listener.is_connected

    from app.models.catalog import Category

    with db_session_module.session_scope(postgresql_initialized_db) as session:
        session.add(Category(nom="Catégorie après reconnexion"))
    time.sleep(0.2)
    assert listener.poll() == {"categories"}
    listener.close()


def test_poll_reflects_commit_but_never_a_rollback(postgresql_initialized_db: Settings) -> None:
    """Exigence explicite de revue : le comportement observé via
    ``PostgreSQLChangeListener.poll()`` lui-même (pas seulement via une
    connexion ``LISTEN`` de test indépendante, déjà couvert par
    ``tests/test_change_notifications_postgresql.py``) doit refléter un
    COMMIT réussi et ne jamais refléter un ROLLBACK."""
    listener = PostgreSQLChangeListener(postgresql_initialized_db)
    listener.poll()  # établit la connexion avant toute émission.

    from app.models.catalog import Category

    try:
        with db_session_module.session_scope(postgresql_initialized_db) as session:
            session.add(Category(nom="Catégorie jamais validée"))
            raise RuntimeError("échec simulé avant la fin de la transaction")
    except RuntimeError:
        pass

    time.sleep(0.2)
    assert listener.poll() == set(), "Un ROLLBACK ne doit jamais produire de notification."

    with db_session_module.session_scope(postgresql_initialized_db) as session:
        session.add(Category(nom="Catégorie validée"))

    time.sleep(0.2)
    assert listener.poll() == {"categories"}, "Un COMMIT doit produire exactement la notification attendue."
    listener.close()


class _FakeCredentialVault:
    """Substitut contrôlé du coffre d'identifiants (voir
    ``app.security.credential_vault``) — le coffre Windows réel ne peut pas
    être exercé dans ce sandbox Linux : ``get_credential_vault()`` y lève
    systématiquement ``CredentialVaultUnavailableError`` par construction
    (voir la docstring de ce module), indépendamment de tout test. Ce
    substitut remplace uniquement l'IMPLÉMENTATION du coffre (même
    interface : ``get_password``/``set_password``/``delete_password``),
    jamais ``PostgreSQLConnectionConfig.resolve_password()`` ni sa logique
    de choix entre coffre et variable d'environnement, qui restent
    exactement le code réel exécuté en production.

    Vérification restant nécessaire sur une installation Windows réelle :
    le bon fonctionnement de ``WindowsCredentialVault`` lui-même (Windows
    Credential Manager réel, backend ``keyring`` réellement actif) combiné
    à ce listener — jamais exercé par ce substitut ni par aucun test de ce
    projet exécuté sous Linux."""

    def __init__(self) -> None:
        self._passwords: dict[str, str] = {}

    def get_password(self, profile_id: str) -> Optional[str]:
        return self._passwords.get(profile_id)

    def set_password(self, profile_id: str, password: str) -> None:
        self._passwords[profile_id] = password

    def delete_password(self, profile_id: str) -> None:
        self._passwords.pop(profile_id, None)


def test_connect_resolves_password_from_credential_vault(
    postgresql_initialized_db: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mode de configuration n°1 (mandat de revue) : mot de passe obtenu
    via le coffre d'identifiants (``credential_key`` renseigné), jamais via
    une variable d'environnement — ``password_env_var`` reste à sa valeur
    par défaut, jamais définie dans l'environnement de ce test, pour
    prouver que ce chemin n'est jamais consulté."""
    fake_vault = _FakeCredentialVault()
    fake_vault.set_password("profil-test-coffre", _PG_PASSWORD)
    monkeypatch.setattr("app.security.credential_vault.get_credential_vault", lambda: fake_vault)

    settings_via_vault = Settings(
        environment="test", db_path=postgresql_initialized_db.db_path,
        log_dir=postgresql_initialized_db.log_dir, log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER,
            credential_key="profil-test-coffre", connect_timeout_seconds=5,
        ),
    )

    listener = PostgreSQLChangeListener(settings_via_vault)
    assert listener.connect() is True
    assert listener.is_connected
    listener.close()


def test_connect_resolves_password_from_environment_variable(postgresql_initialized_db: Settings) -> None:
    """Mode de configuration n°2 (mandat de revue) : mot de passe obtenu
    via la variable d'environnement (``credential_key`` absent) — déjà
    exercé implicitement par tous les autres tests de ce fichier via la
    fixture ``postgresql_initialized_db``, nommé ici explicitement."""
    listener = PostgreSQLChangeListener(postgresql_initialized_db)
    assert listener.connect() is True
    listener.close()


def test_connect_and_poll_work_with_a_password_containing_special_characters(
    postgresql_initialized_db: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mode opératoire explicite de revue : un mot de passe contenant
    ``@``, ``%``, ``:`` et ``/`` ne doit jamais casser la connexion —
    confirme la correction (paramètres séparés transmis à
    ``psycopg.connect()``, jamais une chaîne DSN interpolée). Le mot de
    passe du rôle de test est temporairement changé (une seule connexion
    peut changer SON PROPRE mot de passe sans privilège particulier),
    jamais via un autre rôle ni une opération superutilisateur — restauré
    dans tous les cas, y compris en cas d'échec du test."""
    from psycopg import sql

    special_password = "P@ss!word%100/test:ok"
    special_env_var = "STOCKMANAGER_TEST_PG_PASSWORD_VALUE_SPECIAL_CHARS"

    def _set_role_password(current_password: str, new_password: str) -> None:
        # ``ALTER ROLE ... PASSWORD`` n'accepte pas de paramètre lié (``%s``)
        # — seul un littéral SQL est accepté par la grammaire de cette
        # instruction. ``sql.Literal`` échappe correctement le mot de passe
        # (guillemets, antislash, tout caractère) — jamais une interpolation
        # de chaîne Python brute.
        connection = psycopg.connect(
            host=_PG_HOST, port=_PG_PORT, dbname=_PG_DB, user=_PG_USER,
            password=current_password, autocommit=True,
        )
        try:
            connection.execute(
                sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
                    sql.Identifier(_PG_USER), sql.Literal(new_password)
                )
            )
        finally:
            connection.close()

    _set_role_password(_PG_PASSWORD, special_password)
    try:
        monkeypatch.setenv(special_env_var, special_password)
        settings_special = Settings(
            environment="test", db_path=postgresql_initialized_db.db_path,
            log_dir=postgresql_initialized_db.log_dir, log_level="DEBUG", default_currency="XOF",
            db_backend="postgresql",
            postgresql=PostgreSQLConnectionConfig(
                host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER,
                password_env_var=special_env_var, connect_timeout_seconds=5,
            ),
        )
        listener = PostgreSQLChangeListener(settings_special)
        assert listener.connect() is True
        assert listener.poll() == set()
        listener.close()
    finally:
        _set_role_password(special_password, _PG_PASSWORD)


def test_representative_real_installation_configuration_receives_a_notification(
    postgresql_initialized_db: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mode opératoire explicite de revue (« configuration représentative
    de l'installation réelle ») : combine le chemin coffre d'identifiants
    (celui qu'utilise réellement un poste configuré via l'assistant/
    l'écran d'administration — jamais une variable d'environnement en
    usage réel, voir ``database_admin_service.py``) avec une notification
    PostgreSQL réellement émise et reçue de bout en bout."""
    fake_vault = _FakeCredentialVault()
    fake_vault.set_password("profil-installation-reelle", _PG_PASSWORD)
    monkeypatch.setattr("app.security.credential_vault.get_credential_vault", lambda: fake_vault)

    settings_representative = Settings(
        environment="test", db_path=postgresql_initialized_db.db_path,
        log_dir=postgresql_initialized_db.log_dir, log_level="DEBUG", default_currency="XOF",
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER,
            credential_key="profil-installation-reelle", connect_timeout_seconds=5,
        ),
    )

    listener = PostgreSQLChangeListener(settings_representative)
    listener.poll()  # établit la connexion LISTEN avant l'émission.

    from app.models.catalog import Category

    with db_session_module.session_scope(postgresql_initialized_db) as session:
        session.add(Category(nom="Catégorie configuration réelle"))

    time.sleep(0.2)
    assert listener.poll() == {"categories"}
    listener.close()
