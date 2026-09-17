"""Contrôle centralisé des permissions (RBAC).

Point unique de vérification : toute vue ou tout service qui doit décider
si une action est autorisée passe par ``has_permission`` (affichage) ou
``require_permission`` (exécution, lève si refusé). Aucune condition de
rôle ne doit être écrite ailleurs dans le code.
"""
from __future__ import annotations

from typing import Optional

from app.services.auth.auth_service import AuthService
from app.services.auth.current_user import CurrentUser
from app.utils.exceptions import PermissionDeniedError


class PermissionService:
    def __init__(self, auth_service: AuthService) -> None:
        self._auth_service = auth_service

    @property
    def current_user(self) -> Optional[CurrentUser]:
        return self._auth_service.current_user

    def has_permission(self, code: str) -> bool:
        user = self.current_user
        return user is not None and user.has_permission(code)

    def require_permission(self, code: str) -> None:
        """Lève :class:`PermissionDeniedError` si la permission n'est pas accordée.

        C'est ce contrôle, exécuté côté service, qui empêche un contournement
        par manipulation de l'interface : même si un écran restait accessible
        par erreur, l'action sous-jacente resterait refusée ici.
        """
        if not self.has_permission(code):
            raise PermissionDeniedError(f"Permission requise : {code}")
