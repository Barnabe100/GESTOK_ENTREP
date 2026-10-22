"""Lot D.3 : service d'administration de la configuration de base de
données — voir ``app.services.database_admin.database_admin_service``.

Le coffre d'identifiants réel (Windows Credential Manager) n'existe pas
dans cet environnement Linux : ``get_credential_vault()`` y refuse
toujours explicitement (voir ``tests/test_credential_vault.py``), ce qui
est le comportement correct et déjà testé séparément. Pour tester la
logique du service indépendamment de cette contrainte de plateforme (séparation
des responsabilités, §4.3 du mandat : la persistance du fichier ne doit pas
dépendre du coffre), ces tests remplacent ``get_credential_vault`` par un
faux coffre en mémoire, explicitement un double de test — jamais un
mécanisme de secours que le code de production utiliserait lui-même."""
from __future__ import annotations

import os
from typing import Optional

import pytest

from app.config.db_config_store import default_db_config_path, load_db_config_file
from app.utils.exceptions import ConfigurationError, PermissionDeniedError, ValidationError

# -- serveur PostgreSQL de test réel (test de connexion), même convention
# que tests/test_db_session.py — jamais de mot de passe de repli codé en dur.
_PG_HOST = os.environ.get("STOCKMANAGER_TEST_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.environ.get("STOCKMANAGER_TEST_PG_PORT", "5432"))
_PG_DB = os.environ.get("STOCKMANAGER_TEST_PG_DB", "stockmanager_test")
_PG_USER = os.environ.get("STOCKMANAGER_TEST_PG_USER", "stockmanager_test")
_PG_PASSWORD = os.environ.get("STOCKMANAGER_TEST_PG_PASSWORD")


class _FakeVault:
    """Coffre en mémoire, pour les tests de ce fichier uniquement — jamais
    utilisé par le code de production (voir docstring de module)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get_password(self, profile_id: str) -> Optional[str]:
        return self._store.get(profile_id)

    def set_password(self, profile_id: str, password: str) -> None:
        self._store[profile_id] = password

    def delete_password(self, profile_id: str) -> None:
        self._store.pop(profile_id, None)


@pytest.fixture()
def fake_vault(monkeypatch: pytest.MonkeyPatch) -> _FakeVault:
    vault = _FakeVault()
    monkeypatch.setattr(
        "app.services.database_admin.database_admin_service.get_credential_vault", lambda: vault
    )
    return vault


# -- consultation : permissions ---------------------------------------------------------


def test_admin_can_read_default_config_summary(login_as) -> None:
    stack, _ = login_as("Administrateur")
    summary = stack.database_admin.get_config_summary()
    assert summary.active.backend == "sqlite"
    assert summary.active.postgresql is None
    assert summary.pending is None
    assert summary.restart_required is False


def test_non_admin_cannot_read_config_summary(login_as) -> None:
    stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        stack.database_admin.get_config_summary()


def test_non_admin_without_any_role_permission_cannot_read(login_as) -> None:
    stack, _ = login_as("Consultation")
    with pytest.raises(PermissionDeniedError):
        stack.database_admin.get_config_summary()


# -- préparation : permissions, jamais de changement à chaud -------------------------


def test_non_admin_cannot_prepare_postgresql_pending_config(login_as, fake_vault, initialized_db) -> None:
    stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        stack.database_admin.prepare_postgresql_pending_config(
            host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret",
        )
    # Aucun effet de bord : ni fichier, ni entrée dans le coffre.
    config_file = load_db_config_file(default_db_config_path(initialized_db.data_dir))
    assert config_file.pending is None
    assert fake_vault._store == {}


def test_admin_prepares_postgresql_pending_config_without_touching_active(
    login_as, fake_vault
) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.database_admin.prepare_postgresql_pending_config(
        host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret-value",
    )

    assert summary.active.backend == "sqlite"  # jamais modifié par une préparation.
    assert summary.pending is not None
    assert summary.pending.backend == "postgresql"
    assert summary.pending.postgresql.host == "pg.example.com"
    assert summary.pending.postgresql.port == 5432
    assert summary.pending.postgresql.database == "stockmanager"
    assert summary.pending.postgresql.username == "smuser"
    assert summary.restart_required is True

    # Le mot de passe a bien été déposé dans le coffre (ici le faux coffre
    # de test), jamais dans le résumé ni dans le fichier externe.
    assert "s3cret-value" in fake_vault._store.values()


def test_prepared_postgresql_config_summary_never_exposes_password_or_credential_key(
    login_as, fake_vault
) -> None:
    stack, _ = login_as("Administrateur")
    summary = stack.database_admin.prepare_postgresql_pending_config(
        host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret-value",
    )
    # PostgreSQLProfileSummary ne porte que host/port/database/username.
    assert not hasattr(summary.pending.postgresql, "credential_key")
    assert not hasattr(summary.pending.postgresql, "password")
    assert "s3cret-value" not in repr(summary)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"host": "", "port": 5432, "database": "d", "username": "u", "password": "p"},
        {"host": "h", "port": 0, "database": "d", "username": "u", "password": "p"},
        {"host": "h", "port": 70000, "database": "d", "username": "u", "password": "p"},
        {"host": "h", "port": 5432, "database": "", "username": "u", "password": "p"},
        {"host": "h", "port": 5432, "database": "d", "username": "", "password": "p"},
        {"host": "h", "port": 5432, "database": "d", "username": "u", "password": ""},
    ],
)
def test_prepare_postgresql_rejects_invalid_fields(login_as, fake_vault, kwargs) -> None:
    stack, _ = login_as("Administrateur")
    with pytest.raises(ValidationError):
        stack.database_admin.prepare_postgresql_pending_config(**kwargs)


def test_admin_prepares_sqlite_pending_config(login_as, fake_vault) -> None:
    stack, _ = login_as("Administrateur")
    stack.database_admin.prepare_postgresql_pending_config(
        host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret",
    )

    summary = stack.database_admin.prepare_sqlite_pending_config()

    assert summary.active.backend == "sqlite"
    assert summary.pending.backend == "sqlite"
    assert summary.pending.postgresql is None


# -- annulation : préserve intégralement la configuration active ---------------------


def test_cancel_pending_config_preserves_active_and_clears_pending(login_as, fake_vault) -> None:
    stack, _ = login_as("Administrateur")
    stack.database_admin.prepare_postgresql_pending_config(
        host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret",
    )

    summary = stack.database_admin.cancel_pending_config()

    assert summary.active.backend == "sqlite"
    assert summary.pending is None
    assert summary.restart_required is False


def test_cancel_pending_config_removes_orphaned_credential_from_vault(login_as, fake_vault) -> None:
    stack, _ = login_as("Administrateur")
    stack.database_admin.prepare_postgresql_pending_config(
        host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret",
    )
    assert len(fake_vault._store) == 1

    stack.database_admin.cancel_pending_config()

    assert fake_vault._store == {}


def test_non_admin_cannot_cancel_pending_config(login_as, fake_vault) -> None:
    admin_stack, _ = login_as("Administrateur")
    admin_stack.database_admin.prepare_postgresql_pending_config(
        host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret",
    )

    vendeur_stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        vendeur_stack.database_admin.cancel_pending_config()

    # L'état en attente créé par l'administrateur n'a pas été altéré par la tentative refusée.
    summary = admin_stack.database_admin.get_config_summary()
    assert summary.pending is not None


def test_replacing_pending_postgresql_profile_removes_previous_orphaned_credential(
    login_as, fake_vault
) -> None:
    stack, _ = login_as("Administrateur")
    stack.database_admin.prepare_postgresql_pending_config(
        host="first.example.com", port=5432, database="db1", username="u1", password="p1",
    )
    assert len(fake_vault._store) == 1

    stack.database_admin.prepare_postgresql_pending_config(
        host="second.example.com", port=5432, database="db2", username="u2", password="p2",
    )

    # Un seul secret subsiste (celui du nouveau profil en attente) : l'ancien
    # a été supprimé, jamais laissé orphelin dans le coffre.
    assert len(fake_vault._store) == 1
    assert "p2" in fake_vault._store.values()
    assert "p1" not in fake_vault._store.values()


def test_switching_pending_back_to_sqlite_cleans_up_postgresql_credential(login_as, fake_vault) -> None:
    stack, _ = login_as("Administrateur")
    stack.database_admin.prepare_postgresql_pending_config(
        host="pg.example.com", port=5432, database="stockmanager", username="smuser", password="s3cret",
    )
    assert len(fake_vault._store) == 1

    stack.database_admin.prepare_sqlite_pending_config()

    assert fake_vault._store == {}


# -- test de connexion : serveur PostgreSQL 16.15 réel --------------------------------
#
# Base/rôle de test dédiés (jamais la base applicative) : si le serveur ou
# STOCKMANAGER_TEST_PG_PASSWORD ne sont pas disponibles, ces tests sont
# ignorés proprement, jamais présentés comme un échec de l'application.


@pytest.fixture()
def _skip_if_no_pg_server() -> None:
    if _PG_PASSWORD is None:
        pytest.skip(
            "STOCKMANAGER_TEST_PG_PASSWORD non défini : voir la documentation "
            "de ce lot pour configurer un serveur PostgreSQL de test."
        )


def test_non_admin_cannot_test_connection(login_as, _skip_if_no_pg_server) -> None:
    stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        stack.database_admin.test_postgresql_connection(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER, password=_PG_PASSWORD,
        )


def test_admin_test_connection_succeeds_against_real_server(login_as, _skip_if_no_pg_server) -> None:
    stack, _ = login_as("Administrateur")
    # Ne lève pas — c'est l'assertion elle-même : une connexion réelle réussie.
    stack.database_admin.test_postgresql_connection(
        host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER, password=_PG_PASSWORD,
    )


def test_admin_test_connection_fails_explicitly_with_wrong_password(login_as, _skip_if_no_pg_server) -> None:
    stack, _ = login_as("Administrateur")
    with pytest.raises(ConfigurationError) as exc_info:
        stack.database_admin.test_postgresql_connection(
            host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER, password="mot-de-passe-invalide",
        )
    assert "mot-de-passe-invalide" not in str(exc_info.value)


def test_admin_test_connection_fails_explicitly_for_unreachable_host(login_as, _skip_if_no_pg_server) -> None:
    stack, _ = login_as("Administrateur")
    with pytest.raises(ConfigurationError):
        # Adresse non routable (RFC 5737, bloc réservé à la documentation) :
        # garantit un échec de connexion dans le délai court configuré,
        # jamais un blocage indéfini.
        stack.database_admin.test_postgresql_connection(
            host="192.0.2.1", port=5432, database=_PG_DB, username=_PG_USER, password="peu-importe",
        )


def test_test_connection_never_persists_anything(login_as, _skip_if_no_pg_server, initialized_db) -> None:
    stack, _ = login_as("Administrateur")
    stack.database_admin.test_postgresql_connection(
        host=_PG_HOST, port=_PG_PORT, database=_PG_DB, username=_PG_USER, password=_PG_PASSWORD,
    )
    config_file = load_db_config_file(default_db_config_path(initialized_db.data_dir))
    assert config_file.active.backend == "sqlite"
    assert config_file.pending is None
