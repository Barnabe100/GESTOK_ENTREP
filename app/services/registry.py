"""Regroupe les services applicatifs construits au démarrage.

Évite de faire grossir indéfiniment la signature de ``MainWindow`` et de
``run_session`` à chaque nouveau module métier ; centralise aussi leur
construction (chaque service partage la même instance de
``PermissionService``, elle-même liée à l'unique ``AuthService`` de la
session). Réutilisé tel quel par les tests (voir ``tests/conftest.py``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.config.settings import Settings
from app.services.articles.article_service import ArticleService
from app.services.auth.auth_service import AuthService
from app.services.auth.permission_service import PermissionService
from app.services.categories.category_service import CategoryService
from app.services.entries.entry_service import EntryService
from app.services.exit_reasons.exit_reason_service import ExitReasonService
from app.services.exits.exit_service import ExitService
from app.services.suppliers.supplier_service import SupplierService
from app.services.users.user_service import UserService


@dataclass
class ServiceRegistry:
    auth: AuthService
    permissions: PermissionService
    users: UserService
    categories: CategoryService
    suppliers: SupplierService
    exit_reasons: ExitReasonService
    articles: ArticleService
    entries: EntryService
    exits: ExitService


def build_service_registry(settings: Optional[Settings] = None) -> ServiceRegistry:
    auth_service = AuthService(settings)
    permission_service = PermissionService(auth_service)
    return ServiceRegistry(
        auth=auth_service,
        permissions=permission_service,
        users=UserService(permission_service, settings),
        categories=CategoryService(permission_service, settings),
        suppliers=SupplierService(permission_service, settings),
        exit_reasons=ExitReasonService(permission_service, settings),
        articles=ArticleService(permission_service, settings),
        entries=EntryService(permission_service, settings),
        exits=ExitService(permission_service, settings),
    )
