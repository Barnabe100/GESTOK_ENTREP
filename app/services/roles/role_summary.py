"""DTO de présentation pour l'administration des rôles et permissions
(Lot C) — ``RolesPage``/``EditRolePermissionsDialog``.

``PermissionSummary`` ne porte volontairement aucun état de sélection
(« selected ») : ce champ appartient à l'état de saisie de l'UI (quelle
case est cochée dans le formulaire en cours), jamais au DTO renvoyé par le
service — mélanger les deux ferait porter de la logique de présentation à
un objet censé rester une simple vue en lecture seule des données
persistées.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models.rbac import Permission, Role


@dataclass(frozen=True)
class RoleSummary:
    id: int
    nom: str
    description: Optional[str]
    nombre_utilisateurs_actifs: int

    @classmethod
    def from_model(cls, role: Role, nombre_utilisateurs_actifs: int) -> "RoleSummary":
        return cls(
            id=role.id,
            nom=role.nom,
            description=role.description,
            nombre_utilisateurs_actifs=nombre_utilisateurs_actifs,
        )


@dataclass(frozen=True)
class PermissionSummary:
    code: str
    libelle: str
    module: str

    @classmethod
    def from_model(cls, permission: Permission) -> "PermissionSummary":
        return cls(code=permission.code, libelle=permission.libelle, module=permission.module)
