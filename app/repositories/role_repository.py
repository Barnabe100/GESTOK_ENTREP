"""Accès aux données pour l'administration des rôles et permissions
(Lot C). Les tables ``roles``/``permissions``/``role_permissions``
existent depuis la toute première migration (``0001_schema_initial.py``) —
aucune migration n'est nécessaire pour ce module.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.rbac import Permission, Role
from app.models.user import User
from app.repositories.base import SQLAlchemyRepository


class RoleRepository(SQLAlchemyRepository[Role]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Role)

    def list_roles(self) -> list[Role]:
        return self.session.query(Role).order_by(Role.nom).all()

    def count_active_users(self, role_id: int) -> int:
        return (
            self.session.query(User)
            .filter(User.role_id == role_id, User.actif.is_(True))
            .count()
        )

    def list_permissions(self) -> list[Permission]:
        """Toutes les permissions déclarées, triées par module puis libellé
        — l'ordre attendu pour un regroupement par ``Permission.module`` côté
        appelant (service/UI), jamais recalculé ailleurs."""
        return self.session.query(Permission).order_by(Permission.module, Permission.libelle).all()

    def get_role_permission_codes(self, role_id: int) -> Optional[list[str]]:
        """``None`` si le rôle n'existe pas, sinon la liste triée des codes
        de permission actuellement associés (peut être vide)."""
        role = self.session.get(Role, role_id)
        if role is None:
            return None
        return sorted(p.code for p in role.permissions)

    def update_role_permissions(self, role: Role, permissions: list[Permission]) -> Role:
        """Remplace intégralement l'ensemble des permissions du rôle donné,
        de façon transactionnelle (une seule affectation de la relation M-N,
        SQLAlchemy calcule le diff à la place de l'appelant). Le rôle et les
        permissions doivent avoir déjà été validés par l'appelant (existence,
        garde-fous métier) — ce repository ne fait aucune vérification
        métier, uniquement la persistance."""
        role.permissions = permissions
        self.session.flush()
        return role
