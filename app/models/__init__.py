"""Modèles SQLAlchemy de StockManager Desktop.

Importer ce module garantit que toutes les classes mappées sont enregistrées
dans ``Base.registry`` avant toute création de schéma ou résolution de
relation (``configure_mappers()``).
"""
from app.models.base import Base
from app.models.rbac import Permission, Role, role_permissions, user_roles
from app.models.user import User
from app.models.catalog import Article, Category, ExitReason, Supplier
from app.models.client import Client
from app.models.documents import (
    Entree,
    EntreeLigne,
    Sortie,
    SortieLigne,
    Vente,
    VenteLigne,
)
from app.models.movement import MouvementStock
from app.models.payment import Paiement
from app.models.inventory import Inventaire, InventaireLigne
from app.models.audit import AuditLog
from app.models.parameter import Parametre
from app.models.license import Licence

__all__ = [
    "Base",
    "Role",
    "Permission",
    "role_permissions",
    "user_roles",
    "User",
    "Category",
    "Supplier",
    "ExitReason",
    "Client",
    "Article",
    "Entree",
    "EntreeLigne",
    "Sortie",
    "SortieLigne",
    "Vente",
    "VenteLigne",
    "Paiement",
    "MouvementStock",
    "Inventaire",
    "InventaireLigne",
    "AuditLog",
    "Parametre",
    "Licence",
]
