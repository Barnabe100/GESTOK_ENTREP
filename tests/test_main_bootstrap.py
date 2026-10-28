import logging
import sys

import pytest
from PySide6.QtWidgets import QMessageBox
from sqlalchemy.exc import OperationalError

import app.main as main_module
from app.config.db_config_store import (
    DB_CONFIG_FILE_VERSION,
    DbConfigFile,
    DbEngineConfig,
    PostgreSQLProfile,
    default_db_config_path,
    load_db_config_file,
    write_db_config_file_atomic,
)
from app.config.settings import Settings
from app.db.seed import INITIAL_ADMIN_USERNAME
from app.db.session import session_scope
from app.main import bootstrap
from app.models.rbac import Role
from app.models.user import User
from app.utils import error_handler
from app.utils.exceptions import ConfigurationError


def test_bootstrap_initializes_database_and_seeds_reference_data(test_settings: Settings) -> None:
    bootstrap()

    assert test_settings.db_path.exists()
    with session_scope(test_settings) as session:
        roles = {r.nom for r in session.query(Role).all()}
    assert roles == {"Administrateur", "Gestionnaire de stock", "Vendeur", "Consultation"}


def test_bootstrap_installs_global_exception_handler(test_settings: Settings) -> None:
    original_hook = sys.excepthook
    try:
        bootstrap()
        assert sys.excepthook is error_handler.handle_exception
    finally:
        sys.excepthook = original_hook


def test_bootstrap_configures_logging_with_settings_log_level(test_settings: Settings) -> None:
    bootstrap()
    logger = logging.getLogger("stockmanager")
    assert logger.level == logging.DEBUG  # STOCKMANAGER_LOG_LEVEL=DEBUG dans test_settings


def test_bootstrap_is_idempotent(test_settings: Settings) -> None:
    bootstrap()
    bootstrap()  # ne doit pas échouer ni dupliquer les données de référence

    with session_scope(test_settings) as session:
        assert session.query(Role).count() == 4


def test_bootstrap_creates_initial_admin_account(test_settings: Settings) -> None:
    bootstrap()

    with session_scope(test_settings) as session:
        admin = session.query(User).filter_by(username=INITIAL_ADMIN_USERNAME).one()
        assert [r.nom for r in admin.roles] == ["Administrateur"]
        assert admin.must_change_password is True


def test_bootstrap_does_not_recreate_admin_on_second_run(test_settings: Settings) -> None:
    bootstrap()
    bootstrap()

    with session_scope(test_settings) as session:
        count = session.query(User).filter_by(username=INITIAL_ADMIN_USERNAME).count()
    assert count == 1


# == Lot D.4 : démarrage et gestion des erreurs =======================================
#
# ``apply_pending_db_config_if_any``/``_show_fatal_startup_error`` concentrent
# tout le comportement nouveau de ce lot (application d'une configuration en
# attente avant la résolution de ``Settings`` ; message d'erreur sûr, jamais
# une trace technique brute, lorsque le démarrage échoue). ``bootstrap()``
# lui-même reste couvert par les tests historiques ci-dessus, inchangés.


# -- apply_pending_db_config_if_any : jamais en cours de session, une seule fois ------


def test_noop_when_env_backend_is_set_even_with_a_pending_config(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(tmp_path / "stockmanager.db"))
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "sqlite")
    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(
        path,
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"),
            pending=DbEngineConfig(
                backend="postgresql",
                postgresql=PostgreSQLProfile(host="h", port=5432, database="d", username="u", credential_key="k"),
            ),
        ),
    )

    main_module.apply_pending_db_config_if_any()

    # Le fichier n'a pas été touché : le déploiement scripté (Lot A) ignore
    # toujours ce fichier.
    reloaded = load_db_config_file(path)
    assert reloaded.active.backend == "sqlite"
    assert reloaded.pending is not None


def test_promotes_pending_to_active_when_no_env_backend(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(tmp_path / "stockmanager.db"))
    monkeypatch.delenv("STOCKMANAGER_DB_BACKEND", raising=False)
    path = default_db_config_path(tmp_path)
    write_db_config_file_atomic(
        path,
        DbConfigFile(
            version=DB_CONFIG_FILE_VERSION, active=DbEngineConfig(backend="sqlite"),
            pending=DbEngineConfig(
                backend="postgresql",
                postgresql=PostgreSQLProfile(host="h", port=5432, database="d", username="u", credential_key="k"),
            ),
        ),
    )

    main_module.apply_pending_db_config_if_any()

    reloaded = load_db_config_file(path)
    assert reloaded.active.backend == "postgresql"
    assert reloaded.active.postgresql.host == "h"
    assert reloaded.pending is None


def test_noop_and_no_file_created_when_nothing_pending_and_no_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(tmp_path / "stockmanager.db"))
    monkeypatch.delenv("STOCKMANAGER_DB_BACKEND", raising=False)

    main_module.apply_pending_db_config_if_any()

    assert not default_db_config_path(tmp_path).exists()


# -- _show_fatal_startup_error : jamais de trace technique brute, jamais de secret ----


def test_app_error_message_shown_directly(monkeypatch: pytest.MonkeyPatch, qapp) -> None:
    captured: list[str] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: captured.append(self.text()) or QMessageBox.StandardButton.Ok)

    main_module._show_fatal_startup_error(ConfigurationError("Message métier déjà sûr."))

    assert captured == ["Message métier déjà sûr."]


def test_non_app_error_shows_generic_message_never_the_raw_exception(
    monkeypatch: pytest.MonkeyPatch, qapp
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: captured.append(self.text()) or QMessageBox.StandardButton.Ok)

    raw_exc = RuntimeError(
        "connection to server at \"pg.example.com\" (10.0.0.5), port 5432 failed: "
        "password authentication failed for user \"smuser\" — mot-de-passe-secret"
    )
    main_module._show_fatal_startup_error(raw_exc)

    assert captured == [main_module._GENERIC_STARTUP_FAILURE_MESSAGE]
    assert "mot-de-passe-secret" not in captured[0]
    assert "10.0.0.5" not in captured[0]
    assert "pg.example.com" not in captured[0]


# == Phase accès réseau, point 1 : _recover_from_startup_failure =====================
#
# Offre un chemin de correction (dialogue de configuration, jamais la
# fermeture immédiate de l'application) lorsque ``bootstrap()`` échoue avec
# un moteur PostgreSQL configuré ET que l'échec est une
# ``sqlalchemy.exc.OperationalError`` (convention déjà établie dans tout ce
# projet pour « connexion impossible » — voir par exemple
# tests/test_migrations_postgresql.py, qui s'en sert pour distinguer un
# serveur injoignable d'une véritable erreur de migration). Voir
# ``app.views.database_unreachable_dialog``. Le dialogue réel n'est jamais
# construit ici (nécessiterait un vrai échec de connexion) : un double
# minimal en joue le rôle, piloté par ``monkeypatch`` sur
# ``app.main.DatabaseUnreachableDialog`` — même principe que pour
# ``QMessageBox`` dans les tests ci-dessus.


def _fake_operational_error(message: str) -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception(message))


def _fake_get_settings(settings: Settings):
    """Remplaçant du ``get_settings`` mis en cache (``functools.lru_cache``)
    importé dans ``app.main`` : ``_recover_from_startup_failure`` appelle
    ``get_settings.cache_clear()`` après une correction réussie, un simple
    ``lambda`` n'offrirait donc pas cet attribut."""

    def _get_settings() -> Settings:
        return settings

    _get_settings.cache_clear = lambda: None
    return _get_settings


def _fake_dialog_factory(results: list[int]):
    """Fabrique un remplaçant de ``DatabaseUnreachableDialog`` dont
    ``exec()`` consomme ``results`` dans l'ordre — jamais de fenêtre
    réelle construite ni de blocage, et jamais d'état partagé entre
    tests (``results`` est capturé par fermeture, propre à chaque appel
    de cette fabrique)."""

    class _FakeUnreachableDialog:
        def __init__(self, settings, failure) -> None:
            self.settings = settings
            self.failure = failure

        def exec(self) -> int:
            return results.pop(0)

    return _FakeUnreachableDialog


def test_recover_does_nothing_for_a_scripted_deployment(monkeypatch: pytest.MonkeyPatch, test_settings) -> None:
    monkeypatch.setenv("STOCKMANAGER_DB_BACKEND", "sqlite")
    monkeypatch.setattr(
        main_module, "DatabaseUnreachableDialog",
        lambda *a, **k: pytest.fail("ne doit jamais être construit pour un déploiement scripté."),
    )

    # Un déploiement scripté est écarté avant même toute classification de
    # l'exception (voir l'ordre des vérifications dans
    # ``_recover_from_startup_failure``) : une ``OperationalError`` est
    # écartée exactement comme n'importe quelle autre exception ici.
    original_exc = _fake_operational_error("connexion refusée")
    assert main_module._recover_from_startup_failure(original_exc) is original_exc


def test_recover_does_nothing_when_active_backend_is_sqlite(
    monkeypatch: pytest.MonkeyPatch, test_settings
) -> None:
    monkeypatch.setattr(
        main_module, "DatabaseUnreachableDialog",
        lambda *a, **k: pytest.fail("aucun recours réseau applicable pour SQLite."),
    )

    original_exc = _fake_operational_error("fichier SQLite verrouillé")
    assert main_module._recover_from_startup_failure(original_exc) is original_exc


def test_recover_does_nothing_for_a_non_connection_error_even_with_postgresql_backend(
    monkeypatch: pytest.MonkeyPatch, test_settings
) -> None:
    """Point explicitement demandé en revue : une erreur de migration (ou
    toute autre exception qui n'est pas une ``OperationalError``) ne doit
    jamais être présentée comme une indisponibilité réseau, même lorsque le
    moteur actif est PostgreSQL — modifier l'hôte/le port/les identifiants
    ne peut de toute façon pas corriger un script de migration défaillant."""
    import dataclasses

    from app.config.settings import PostgreSQLConnectionConfig

    pg_settings = dataclasses.replace(
        test_settings, db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u"),
    )
    monkeypatch.setattr(main_module, "get_settings", _fake_get_settings(pg_settings))
    monkeypatch.setattr(
        main_module, "DatabaseUnreachableDialog",
        lambda *a, **k: pytest.fail("jamais affiché pour une erreur qui n'est pas de connexion."),
    )
    monkeypatch.setattr(
        main_module, "bootstrap", lambda: pytest.fail("jamais retenté sans passer par le dialogue.")
    )

    migration_exc = RuntimeError("échec de la migration Alembic 0012 -> 0013 : colonne déjà existante")
    assert main_module._recover_from_startup_failure(migration_exc) is migration_exc


def test_recover_returns_none_when_the_user_corrects_and_bootstrap_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, test_settings
) -> None:
    import dataclasses

    from PySide6.QtWidgets import QDialog

    from app.config.settings import PostgreSQLConnectionConfig

    pg_settings = dataclasses.replace(
        test_settings, db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u"),
    )
    monkeypatch.setattr(main_module, "get_settings", _fake_get_settings(pg_settings))

    monkeypatch.setattr(
        main_module, "DatabaseUnreachableDialog", _fake_dialog_factory([QDialog.DialogCode.Accepted])
    )
    monkeypatch.setattr(main_module, "bootstrap", lambda: None)  # réussit cette fois-ci

    result = main_module._recover_from_startup_failure(_fake_operational_error("connexion refusée"))

    assert result is None


def test_recover_returns_the_original_failure_when_the_user_gives_up(
    monkeypatch: pytest.MonkeyPatch, test_settings
) -> None:
    import dataclasses

    from PySide6.QtWidgets import QDialog

    from app.config.settings import PostgreSQLConnectionConfig

    pg_settings = dataclasses.replace(
        test_settings, db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u"),
    )
    monkeypatch.setattr(main_module, "get_settings", _fake_get_settings(pg_settings))

    monkeypatch.setattr(
        main_module, "DatabaseUnreachableDialog", _fake_dialog_factory([QDialog.DialogCode.Rejected])
    )
    monkeypatch.setattr(
        main_module, "bootstrap", lambda: pytest.fail("ne doit jamais être retenté après un abandon.")
    )

    original_exc = _fake_operational_error("connexion refusée")
    assert main_module._recover_from_startup_failure(original_exc) is original_exc


def test_recover_loops_and_returns_the_latest_failure_after_a_second_unsuccessful_attempt(
    monkeypatch: pytest.MonkeyPatch, test_settings
) -> None:
    import dataclasses

    from PySide6.QtWidgets import QDialog

    from app.config.settings import PostgreSQLConnectionConfig

    pg_settings = dataclasses.replace(
        test_settings, db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u"),
    )
    monkeypatch.setattr(main_module, "get_settings", _fake_get_settings(pg_settings))

    # Acceptée deux fois : une correction (qui échoue encore), puis
    # l'utilisateur renonce après avoir vu la nouvelle erreur.
    monkeypatch.setattr(
        main_module, "DatabaseUnreachableDialog",
        _fake_dialog_factory([QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected]),
    )

    second_failure = _fake_operational_error("toujours injoignable, nouveau message")
    bootstrap_calls = {"n": 0}

    def _bootstrap() -> None:
        bootstrap_calls["n"] += 1
        raise second_failure

    monkeypatch.setattr(main_module, "bootstrap", _bootstrap)

    original_exc = _fake_operational_error("connexion refusée")
    result = main_module._recover_from_startup_failure(original_exc)

    assert bootstrap_calls["n"] == 1
    assert result is second_failure  # jamais l'erreur d'origine, déjà corrigée une fois.


def test_recover_stops_looping_when_a_retry_fails_with_a_non_connection_error(
    monkeypatch: pytest.MonkeyPatch, test_settings
) -> None:
    """Point explicitement demandé en revue : si une correction aboutit à
    une connexion réussie mais que ``bootstrap()`` échoue ensuite pour une
    autre raison (migration, données de référence), le dialogue de
    correction réseau ne doit jamais être réaffiché une seconde fois — la
    nouvelle erreur n'a rien à voir avec la joignabilité du serveur."""
    import dataclasses

    from PySide6.QtWidgets import QDialog

    from app.config.settings import PostgreSQLConnectionConfig

    pg_settings = dataclasses.replace(
        test_settings, db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u"),
    )
    monkeypatch.setattr(main_module, "get_settings", _fake_get_settings(pg_settings))

    dialog_calls = {"n": 0}

    def _counting_dialog_factory(settings, failure):
        dialog_calls["n"] += 1
        return _fake_dialog_factory([QDialog.DialogCode.Accepted])(settings, failure)

    monkeypatch.setattr(main_module, "DatabaseUnreachableDialog", _counting_dialog_factory)

    migration_failure = RuntimeError("échec de la migration Alembic : colonne déjà existante")
    monkeypatch.setattr(main_module, "bootstrap", lambda: (_ for _ in ()).throw(migration_failure))

    original_exc = _fake_operational_error("connexion refusée")
    result = main_module._recover_from_startup_failure(original_exc)

    assert dialog_calls["n"] == 1  # jamais réaffiché pour la nouvelle erreur, non liée au réseau.
    assert result is migration_failure
