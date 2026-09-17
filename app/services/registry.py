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
from app.services.backups.backup_service import BackupService
from app.services.categories.category_service import CategoryService
from app.services.entries.entry_service import EntryService
from app.services.exit_reasons.exit_reason_service import ExitReasonService
from app.services.exits.exit_service import ExitService
from app.services.inventory.inventory_service import InventoryService
from app.services.licensing.feature_gate import FeatureGate
from app.services.licensing.license_service import LicenseService
from app.services.licensing.permission_map import PERMISSION_TO_FEATURE
from app.services.licensing.public_key import PRODUCTION_PUBLIC_KEY_BYTES
from app.services.reports.report_service import ReportService
from app.services.sales.sale_service import SaleService
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
    sales: SaleService
    inventory: InventoryService
    reports: ReportService
    backups: BackupService
    licenses: LicenseService


def build_service_registry(
    settings: Optional[Settings] = None, license_public_key_bytes: bytes = PRODUCTION_PUBLIC_KEY_BYTES
) -> ServiceRegistry:
    """``license_public_key_bytes`` n'est jamais surchargée en production : le
    seul appelant qui la remplace est ``tests/conftest.py``, avec une clé de
    test éphémère (jamais la clé de production, et surtout jamais une clé
    privée — seule la clé publique correspondante est nécessaire ici)."""
    auth_service = AuthService(settings)
    # PermissionService est construit sans FeatureGate : LicenseService en a
    # besoin pour vérifier LICENSE_VIEW/LICENSE_ACTIVATE (permissions non
    # soumises au contrôle de licence, voir permission_map.py), ce qui
    # empêcherait une construction directe FeatureGate -> PermissionService.
    permission_service = PermissionService(auth_service, permission_to_feature=PERMISSION_TO_FEATURE)
    license_service = LicenseService(permission_service, settings, public_key_bytes=license_public_key_bytes)
    permission_service.set_feature_gate(FeatureGate(license_service))

    return ServiceRegistry(
        auth=auth_service,
        permissions=permission_service,
        users=UserService(permission_service, settings, license_service=license_service),
        categories=CategoryService(permission_service, settings),
        suppliers=SupplierService(permission_service, settings),
        exit_reasons=ExitReasonService(permission_service, settings),
        articles=ArticleService(permission_service, settings),
        entries=EntryService(permission_service, settings),
        exits=ExitService(permission_service, settings),
        sales=SaleService(permission_service, settings),
        inventory=InventoryService(permission_service, settings),
        reports=ReportService(permission_service, settings),
        backups=BackupService(permission_service, settings),
        licenses=license_service,
    )
