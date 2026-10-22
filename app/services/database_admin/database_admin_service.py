"""Service d'administration de la configuration de base de données (Lot D).

Sépare strictement trois responsabilités, jamais mélangées :

1. **Configuration persistante** (``app.config.db_config_store``) : le
   fichier JSON externe, actif/en attente, jamais de secret.
2. **Secrets** (``app.security.credential_vault``) : le mot de passe
   PostgreSQL, jamais dans le fichier ci-dessus.
3. **Application de la configuration** (``app.db.session``/``app.main``) :
   ni ce service, ni les fonctions ci-dessous ne l'effectuent jamais —
   voir règle ci-dessous.

Règle non négociable : **rien dans ce module ne change le moteur actif
pendant que l'application tourne.** Toute préparation (``prepare_*``)
n'écrit que la section ``pending`` du fichier externe ; elle ne devient
``active`` qu'au prochain démarrage complet du processus
(``app.config.db_config_store.promote_pending_to_active``, appelée une
seule fois par ``app.main``, jamais ici).

Deux niveaux délibérément distincts :

- Les fonctions module-niveau (``test_postgresql_connection_unchecked``,
  ``prepare_*_unchecked``, ``cancel_pending_config_unchecked``, préfixées
  ``_unchecked``) contiennent toute la logique réelle, **sans aucun
  contrôle de permission** — elles sont réutilisées par l'assistant de
  première configuration (``app.views.database_setup_wizard``), qui
  s'exécute **avant toute authentification** (aucun utilisateur n'existe
  encore, exactement comme ``app.db.seed.seed_initial_admin``, qui crée le
  tout premier compte administrateur sans vérification de permission non
  plus : il n'y a personne à vérifier).
- :class:`DatabaseAdminService` est la seule façade utilisée après
  connexion (écran d'administration, Lot D.6) : chaque méthode publique
  vérifie ``DATABASE_CONFIG_VIEW``/``DATABASE_CONFIG_UPDATE`` via
  ``PermissionService.require_permission`` — côté service, jamais
  seulement dans l'interface — **avant** de déléguer à la fonction
  ``_unchecked`` correspondante.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from app.config.db_config_store import (
    DbEngineConfig,
    PostgreSQLProfile,
    default_db_config_path,
    load_db_config_file,
    set_pending_config,
)
from app.config.settings import (
    DEFAULT_POSTGRESQL_PORT,
    PostgreSQLConnectionConfig,
    Settings,
    get_settings,
)
from app.db.session import create_db_engine, session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.security.credential_vault import get_credential_vault
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import ConfigurationError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.database_admin")

# Lot D (§4.6 du mandat) : délai court et maîtrisé pour le test de
# connexion interactif — distinct du délai de connexion de l'engine réel
# (DEFAULT_POSTGRESQL_CONNECT_TIMEOUT_SECONDS, 10 s), pour qu'un clic sur
# « Tester la connexion » ne bloque jamais longtemps l'interface, elle-même
# synchrone (décision validée : pas de thread dédié pour ce seul appel).
TEST_CONNECTION_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class PostgreSQLProfileSummary:
    """Vue non sensible d'un profil PostgreSQL — jamais ``credential_key``
    (détail d'implémentation interne) ni, a fortiori, le mot de passe."""

    host: str
    port: int
    database: str
    username: str


@dataclass(frozen=True)
class DbEngineConfigSummary:
    backend: str
    postgresql: Optional[PostgreSQLProfileSummary] = None


@dataclass(frozen=True)
class DatabaseConfigSummary:
    """Vue complète destinée à l'écran d'administration/l'assistant."""

    active: DbEngineConfigSummary
    pending: Optional[DbEngineConfigSummary]

    @property
    def restart_required(self) -> bool:
        return self.pending is not None


def _to_summary(engine_config: DbEngineConfig) -> DbEngineConfigSummary:
    if engine_config.postgresql is None:
        return DbEngineConfigSummary(backend=engine_config.backend)
    profile = engine_config.postgresql
    return DbEngineConfigSummary(
        backend=engine_config.backend,
        postgresql=PostgreSQLProfileSummary(
            host=profile.host, port=profile.port, database=profile.database, username=profile.username,
        ),
    )


def _validate_postgresql_fields(host: str, port: int, database: str, username: str) -> None:
    if not host or not host.strip():
        raise ValidationError("L'hôte du serveur PostgreSQL est obligatoire.")
    if not isinstance(port, int) or isinstance(port, bool) or not (0 < port <= 65535):
        raise ValidationError(f"Le port doit être un entier entre 1 et 65535 (reçu : {port!r}).")
    if not database or not database.strip():
        raise ValidationError("Le nom de la base PostgreSQL est obligatoire.")
    if not username or not username.strip():
        raise ValidationError("L'utilisateur PostgreSQL est obligatoire.")


# == Fonctions module-niveau : logique réelle, sans contrôle de permission ===========
# Réutilisées (a) par DatabaseAdminService ci-dessous, après vérification de
# permission, et (b) directement par l'assistant de première configuration,
# avant toute authentification — voir docstring de module.


def get_config_summary_unchecked(config_path: Path) -> DatabaseConfigSummary:
    config_file = load_db_config_file(config_path)
    return DatabaseConfigSummary(
        active=_to_summary(config_file.active),
        pending=_to_summary(config_file.pending) if config_file.pending is not None else None,
    )


def test_postgresql_connection_unchecked(
    settings: Settings, *, host: str, port: int, database: str, username: str, password: str
) -> None:
    """Tente une connexion réelle avec les paramètres fournis, sans jamais
    rien enregistrer (ni fichier, ni coffre). Lève :class:`ConfigurationError`
    avec un message compréhensible, sans jamais exposer le mot de passe ni
    la chaîne de connexion brute, en cas d'échec."""
    _validate_postgresql_fields(host, port, database, username)
    if not password:
        raise ValidationError("Le mot de passe est obligatoire pour tester la connexion.")

    probe_settings = Settings(
        environment="test", db_path=settings.db_path, log_dir=settings.log_dir,
        log_level=settings.log_level, default_currency=settings.default_currency,
        db_backend="postgresql",
        postgresql=PostgreSQLConnectionConfig(
            host=host, port=port, database=database, username=username,
            password_env_var=f"__stockmanager_test_connection_{uuid.uuid4().hex}__",
            connect_timeout_seconds=TEST_CONNECTION_TIMEOUT_SECONDS,
        ),
    )
    # Le mot de passe fourni n'est jamais écrit sur disque : il est placé
    # dans une variable d'environnement de processus au nom généré
    # aléatoirement ci-dessus, lue une seule fois par resolve_password(),
    # puis immédiatement effacée dans le bloc finally — jamais persistée,
    # jamais journalisée.
    env_var_name = probe_settings.postgresql.password_env_var
    os.environ[env_var_name] = password
    try:
        engine = create_db_engine(probe_settings)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except Exception as exc:
        logger.warning(
            "Test de connexion PostgreSQL échoué (%s:%s/%s) : %s", host, port, database, type(exc).__name__
        )
        raise ConfigurationError(
            "Connexion impossible : vérifiez l'hôte, le port, le nom de la base, "
            "l'utilisateur et le mot de passe, ainsi que l'accessibilité réseau du serveur."
        ) from exc
    finally:
        os.environ.pop(env_var_name, None)


def _cleanup_orphaned_pending_credential(config_path: Path) -> None:
    """Supprime du coffre le secret d'un profil PostgreSQL en attente qui
    va être remplacé ou annulé — jamais celui du profil actif, même si son
    identifiant coïncide avec celui du profil en attente (profil réutilisé
    tel quel, par exemple si seul le port a changé)."""
    current = load_db_config_file(config_path)
    if current.pending is None or current.pending.postgresql is None:
        return

    pending_key = current.pending.postgresql.credential_key
    active_key = (
        current.active.postgresql.credential_key
        if current.active.backend == "postgresql" and current.active.postgresql is not None
        else None
    )
    if pending_key == active_key:
        return

    try:
        get_credential_vault().delete_password(pending_key)
    except ConfigurationError as exc:
        # Le coffre peut être indisponible (ex. tests Linux, service Windows
        # arrêté) : ne bloque jamais la préparation/l'annulation d'une
        # configuration pour autant, mais ne doit jamais passer inaperçu.
        logger.warning("Impossible de nettoyer l'identifiant en attente %r : %s", pending_key, exc)


def prepare_sqlite_pending_config_unchecked(config_path: Path) -> DatabaseConfigSummary:
    _cleanup_orphaned_pending_credential(config_path)
    set_pending_config(config_path, DbEngineConfig(backend="sqlite"))
    return get_config_summary_unchecked(config_path)


def prepare_postgresql_pending_config_unchecked(
    config_path: Path, *, host: str, port: int = DEFAULT_POSTGRESQL_PORT,
    database: str, username: str, password: str,
) -> DatabaseConfigSummary:
    """Enregistre une nouvelle configuration PostgreSQL en attente — le mot
    de passe est écrit dans le coffre d'identifiants (jamais dans le
    fichier JSON), sous un nouvel identifiant de profil (``credential_key``).
    L'ancien profil en attente éventuel, s'il n'est pas celui actuellement
    actif, est supprimé du coffre (remplacement contrôlé, §4.4 du mandat)."""
    _validate_postgresql_fields(host, port, database, username)
    if not password:
        raise ValidationError("Le mot de passe est obligatoire.")

    _cleanup_orphaned_pending_credential(config_path)

    credential_key = f"postgresql-{uuid.uuid4().hex}"
    get_credential_vault().set_password(credential_key, password)

    profile = PostgreSQLProfile(
        host=host.strip(), port=port, database=database.strip(),
        username=username.strip(), credential_key=credential_key,
    )
    set_pending_config(config_path, DbEngineConfig(backend="postgresql", postgresql=profile))
    return get_config_summary_unchecked(config_path)


def cancel_pending_config_unchecked(config_path: Path) -> DatabaseConfigSummary:
    """Annule la configuration en attente — la configuration active et les
    bases existantes ne sont jamais modifiées (§4.3 du mandat)."""
    _cleanup_orphaned_pending_credential(config_path)
    set_pending_config(config_path, None)
    return get_config_summary_unchecked(config_path)


# == Service post-authentification : mêmes opérations, permissions vérifiées =========


class DatabaseAdminService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _effective_settings(self) -> Settings:
        return self._settings or get_settings()

    def _config_path(self) -> Path:
        return default_db_config_path(self._effective_settings().data_dir)

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, action: str, resultat: ResultatAudit, details: Optional[str] = None) -> None:
        with session_scope(self._settings) as session:
            session.add(
                AuditLog(
                    user_id=self._acting_user_id(), action=action, entite="base_de_donnees",
                    entite_id=None, resultat=resultat, details=details,
                )
            )

    # -- consultation ---------------------------------------------------------------

    def get_config_summary(self) -> DatabaseConfigSummary:
        self._permissions.require_permission("DATABASE_CONFIG_VIEW")
        return get_config_summary_unchecked(self._config_path())

    # -- test de connexion (jamais persisté) -----------------------------------------

    def test_postgresql_connection(
        self, *, host: str, port: int, database: str, username: str, password: str
    ) -> None:
        self._permissions.require_permission("DATABASE_CONFIG_UPDATE")
        test_postgresql_connection_unchecked(
            self._effective_settings(), host=host, port=port, database=database,
            username=username, password=password,
        )
        self._audit(
            "DATABASE_CONFIG_TEST", ResultatAudit.SUCCES,
            details=f"test de connexion PostgreSQL réussi ({host}:{port}/{database})",
        )

    # -- préparation d'une configuration en attente -----------------------------------

    def prepare_sqlite_pending_config(self) -> DatabaseConfigSummary:
        self._permissions.require_permission("DATABASE_CONFIG_UPDATE")
        summary = prepare_sqlite_pending_config_unchecked(self._config_path())
        self._audit("DATABASE_CONFIG_UPDATE", ResultatAudit.SUCCES, details="configuration en attente : SQLite")
        return summary

    def prepare_postgresql_pending_config(
        self, *, host: str, port: int = DEFAULT_POSTGRESQL_PORT, database: str, username: str, password: str
    ) -> DatabaseConfigSummary:
        self._permissions.require_permission("DATABASE_CONFIG_UPDATE")
        summary = prepare_postgresql_pending_config_unchecked(
            self._config_path(), host=host, port=port, database=database, username=username, password=password,
        )
        self._audit(
            "DATABASE_CONFIG_UPDATE", ResultatAudit.SUCCES,
            details=f"configuration en attente : PostgreSQL ({host}:{port}/{database})",
        )
        return summary

    # -- annulation --------------------------------------------------------------------

    def cancel_pending_config(self) -> DatabaseConfigSummary:
        self._permissions.require_permission("DATABASE_CONFIG_UPDATE")
        summary = cancel_pending_config_unchecked(self._config_path())
        self._audit("DATABASE_CONFIG_UPDATE", ResultatAudit.SUCCES, details="configuration en attente annulée")
        return summary
