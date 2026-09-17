import os

# Doit être défini avant tout import de PySide6 (y compris via le plugin pytest-qt).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from typing import Callable, Iterator

import pytest

from app.config.settings import Settings, get_settings
from app.db import session as db_session_module
from app.db.init_db import init_database
from app.db.seed import seed_reference_data
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.auth.auth_service import AuthService
from app.services.auth.current_user import CurrentUser
from app.services.auth.permission_service import PermissionService
from app.services.users.user_service import UserService

DEFAULT_TEST_PASSWORD = "MotDePasse!23"


@pytest.fixture()
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Configuration isolée pointant vers une base SQLite temporaire par test."""
    db_path = tmp_path / "test_stockmanager.db"
    monkeypatch.setenv("STOCKMANAGER_ENV", "test")
    monkeypatch.setenv("STOCKMANAGER_DB_PATH", str(db_path))
    monkeypatch.setenv("STOCKMANAGER_LOG_LEVEL", "DEBUG")

    get_settings.cache_clear()
    db_session_module.reset_engine_cache()

    yield get_settings()

    db_session_module.reset_engine_cache()
    get_settings.cache_clear()


@pytest.fixture()
def initialized_db(test_settings: Settings) -> Settings:
    """Base de test migrée (Alembic) et pré-remplie avec les données de référence."""
    init_database(test_settings)
    with db_session_module.session_scope(test_settings) as session:
        seed_reference_data(session)
    return test_settings


@pytest.fixture()
def make_user(initialized_db: Settings) -> Callable[..., None]:
    """Factory de test : crée un utilisateur avec le rôle donné."""

    def _make_user(
        role_name: str, username: str, password: str = DEFAULT_TEST_PASSWORD, actif: bool = True
    ) -> None:
        with db_session_module.session_scope(initialized_db) as session:
            role = session.query(Role).filter_by(nom=role_name).one()
            session.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role_id=role.id,
                    actif=actif,
                )
            )

    return _make_user


@pytest.fixture()
def make_stack(
    initialized_db: Settings,
) -> Callable[[], tuple[AuthService, PermissionService, UserService]]:
    """Construit une pile AuthService/PermissionService/UserService neuve, non connectée."""

    def _make_stack() -> tuple[AuthService, PermissionService, UserService]:
        auth_service = AuthService(initialized_db)
        permission_service = PermissionService(auth_service)
        user_service = UserService(permission_service, initialized_db)
        return auth_service, permission_service, user_service

    return _make_stack


@pytest.fixture()
def login_as(
    make_user: Callable[..., None],
    make_stack: Callable[[], tuple[AuthService, PermissionService, UserService]],
) -> Callable[..., tuple[AuthService, PermissionService, UserService, CurrentUser]]:
    """Crée un utilisateur avec le rôle donné, le connecte, et retourne
    (auth_service, permission_service, user_service, current_user)."""

    counter = {"n": 0}

    def _login_as(role_name: str, password: str = DEFAULT_TEST_PASSWORD):
        counter["n"] += 1
        username = f"test_{role_name.lower().replace(' ', '_')}_{counter['n']}"
        make_user(role_name, username, password)
        auth_service, permission_service, user_service = make_stack()
        current_user = auth_service.login(username, password)
        return auth_service, permission_service, user_service, current_user

    return _login_as
