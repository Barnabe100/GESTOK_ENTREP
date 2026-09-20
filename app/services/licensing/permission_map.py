"""Correspondance permission RBAC -> fonctionnalité licenciée.

Seules les permissions listées ici sont soumises au contrôle de licence
(``FeatureGate``, via ``PermissionService``) ; toute permission absente de ce
dictionnaire reste régie uniquement par le RBAC (ex. ``SETTINGS_*``,
``ROLE_*``). ``LICENSE_VIEW``/``LICENSE_ACTIVATE`` sont volontairement
exclues : l'écran de licence doit rester accessible même sans licence
valide, sous peine de rendre l'activation elle-même impossible.

``DASHBOARD_VIEW`` est mappée sur ``FEATURE_REPORTS`` (phase Dashboard) :
le Dashboard est une couche de synthèse/visualisation des mêmes données que
les rapports, il réutilise donc la fonctionnalité de licence déjà existante
plutôt que d'en créer une nouvelle (aucune fonctionnalité de licence ne doit
être inventée pour un module qui n'apporte pas de droit métier distinct).
"""
from __future__ import annotations

from app.services.licensing.license_payload import (
    FEATURE_ARTICLES,
    FEATURE_AUDIT,
    FEATURE_BACKUPS,
    FEATURE_CATEGORIES,
    FEATURE_INVENTORY,
    FEATURE_MULTI_USER,
    FEATURE_REPORTS,
    FEATURE_REPORTS_EXPORT,
    FEATURE_SALES,
    FEATURE_STOCK_ENTRIES,
    FEATURE_STOCK_EXITS,
    FEATURE_STOCK_MOVEMENTS,
    FEATURE_SUPPLIERS,
)

# Rattachée à FEATURE_BACKUPS (audit final avant commit, validé) : la
# réinitialisation des données métier réutilise techniquement BackupService
# (sauvegarde de sécurité obligatoire avant toute suppression) et relève de
# la même famille fonctionnelle "maintenance avancée de la base" que
# BACKUP_CREATE/BACKUP_RESTORE, plutôt que de rester disponible sans aucune
# licence valide.

PERMISSION_TO_FEATURE: dict[str, str] = {
    "DASHBOARD_VIEW": FEATURE_REPORTS,
    "ARTICLE_VIEW": FEATURE_ARTICLES,
    "ARTICLE_CREATE": FEATURE_ARTICLES,
    "ARTICLE_UPDATE": FEATURE_ARTICLES,
    "ARTICLE_ACTIVATE": FEATURE_ARTICLES,
    "ARTICLE_DEACTIVATE": FEATURE_ARTICLES,
    "CATEGORY_VIEW": FEATURE_CATEGORIES,
    "CATEGORY_CREATE": FEATURE_CATEGORIES,
    "CATEGORY_UPDATE": FEATURE_CATEGORIES,
    "CATEGORY_ACTIVATE": FEATURE_CATEGORIES,
    "CATEGORY_DEACTIVATE": FEATURE_CATEGORIES,
    "SUPPLIER_VIEW": FEATURE_SUPPLIERS,
    "SUPPLIER_CREATE": FEATURE_SUPPLIERS,
    "SUPPLIER_UPDATE": FEATURE_SUPPLIERS,
    "SUPPLIER_ACTIVATE": FEATURE_SUPPLIERS,
    "SUPPLIER_DEACTIVATE": FEATURE_SUPPLIERS,
    "STOCK_REASON_VIEW": FEATURE_STOCK_EXITS,
    "STOCK_REASON_CREATE": FEATURE_STOCK_EXITS,
    "STOCK_REASON_UPDATE": FEATURE_STOCK_EXITS,
    "STOCK_REASON_ACTIVATE": FEATURE_STOCK_EXITS,
    "STOCK_REASON_DEACTIVATE": FEATURE_STOCK_EXITS,
    "STOCK_ENTRY_VIEW": FEATURE_STOCK_ENTRIES,
    "STOCK_ENTRY_CREATE": FEATURE_STOCK_ENTRIES,
    "STOCK_ENTRY_UPDATE": FEATURE_STOCK_ENTRIES,
    "STOCK_ENTRY_VALIDATE": FEATURE_STOCK_ENTRIES,
    "STOCK_ENTRY_CANCEL": FEATURE_STOCK_ENTRIES,
    "STOCK_EXIT_VIEW": FEATURE_STOCK_EXITS,
    "STOCK_EXIT_CREATE": FEATURE_STOCK_EXITS,
    "STOCK_EXIT_UPDATE": FEATURE_STOCK_EXITS,
    "STOCK_EXIT_VALIDATE": FEATURE_STOCK_EXITS,
    "STOCK_EXIT_CANCEL": FEATURE_STOCK_EXITS,
    "SALE_VIEW": FEATURE_SALES,
    "SALE_CREATE": FEATURE_SALES,
    "SALE_UPDATE": FEATURE_SALES,
    "SALE_VALIDATE": FEATURE_SALES,
    "SALE_CANCEL": FEATURE_SALES,
    "SALE_PAYMENT_CREATE": FEATURE_SALES,
    "STOCK_MOVEMENT_VIEW": FEATURE_STOCK_MOVEMENTS,
    "INVENTORY_VIEW": FEATURE_INVENTORY,
    "INVENTORY_CREATE": FEATURE_INVENTORY,
    "INVENTORY_UPDATE": FEATURE_INVENTORY,
    "INVENTORY_VALIDATE": FEATURE_INVENTORY,
    "REPORT_VIEW": FEATURE_REPORTS,
    "REPORT_EXPORT": FEATURE_REPORTS_EXPORT,
    "BACKUP_VIEW": FEATURE_BACKUPS,
    "BACKUP_CREATE": FEATURE_BACKUPS,
    "BACKUP_RESTORE": FEATURE_BACKUPS,
    "AUDIT_VIEW": FEATURE_AUDIT,
    "SYSTEM_RESET_BUSINESS_DATA": FEATURE_BACKUPS,
    "USER_CREATE": FEATURE_MULTI_USER,
    "USER_UPDATE": FEATURE_MULTI_USER,
    "USER_ACTIVATE": FEATURE_MULTI_USER,
    "USER_RESET_PASSWORD": FEATURE_MULTI_USER,
    # USER_VIEW volontairement exclue : un administrateur avec une licence
    # sans MULTI_USER doit pouvoir consulter la liste des comptes (ex. celui
    # inclus par défaut) sans que la simple consultation soit bloquée.
}
