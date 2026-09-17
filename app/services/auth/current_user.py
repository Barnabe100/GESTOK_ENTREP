"""Représentation de l'utilisateur connecté (session applicative).

Volontairement un objet Python simple, détaché de toute session SQLAlchemy :
il doit rester utilisable après la fermeture de la transaction qui l'a
construit (pas d'accès paresseux à un objet ORM expiré).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role_id: int
    role_name: str
    permissions: frozenset[str]
    must_change_password: bool

    def has_permission(self, code: str) -> bool:
        return code in self.permissions
