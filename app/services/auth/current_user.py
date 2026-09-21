"""Représentation de l'utilisateur connecté (session applicative).

Volontairement un objet Python simple, détaché de toute session SQLAlchemy :
il doit rester utilisable après la fermeture de la transaction qui l'a
construit (pas d'accès paresseux à un objet ORM expiré).

Un utilisateur peut avoir plusieurs rôles (voir migration 0011) : ``role_ids``/
``role_names`` sont donc des collections, jamais des scalaires. Les
permissions effectives (``permissions``) sont déjà l'union pré-calculée des
permissions de tous les rôles au moment de la connexion (voir
``AuthService.login``) — ``has_permission`` n'a donc pas besoin de connaître
les rôles individuellement.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role_ids: frozenset[int]
    role_names: tuple[str, ...]
    permissions: frozenset[str]
    must_change_password: bool

    def has_permission(self, code: str) -> bool:
        return code in self.permissions
