"""Gestion des comptes utilisateurs : consultation, activation/désactivation,
réinitialisation de mot de passe.

La création d'utilisateurs (écran dédié) n'est pas couverte par cette phase ;
le compte administrateur initial est créé par ``app.db.seed``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.logging_config import get_logger

MIN_PASSWORD_LENGTH = 8

logger = get_logger("services.users")


@dataclass(frozen=True)
class UserSummary:
    """Vue en lecture seule d'un utilisateur, sans le hash de mot de passe."""

    id: int
    username: str
    role_name: str
    actif: bool
    dernier_login: Optional[datetime]

    @classmethod
    def from_model(cls, user: User) -> "UserSummary":
        return cls(
            id=user.id,
            username=user.username,
            role_name=user.role.nom,
            actif=user.actif,
            dernier_login=user.dernier_login,
        )


class UserService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def list_users(self) -> list[UserSummary]:
        self._permissions.require_permission("USER_VIEW")
        with session_scope(self._settings) as session:
            users = session.query(User).order_by(User.username).all()
            return [UserSummary.from_model(user) for user in users]

    def set_active(self, user_id: int, actif: bool) -> UserSummary:
        """Active ou désactive un compte. Toujours vérifié côté service,
        indépendamment de ce que l'interface affiche ou masque."""
        self._permissions.require_permission("USER_ACTIVATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            user = session.get(User, user_id)
            if user is None:
                raise NotFoundError(f"Utilisateur {user_id} introuvable.")

            user.actif = actif
            action = "USER_ACTIVATE" if actif else "USER_DEACTIVATE"
            session.add(
                AuditLog(
                    user_id=acting_user_id,
                    action=action,
                    entite="users",
                    entite_id=user_id,
                    resultat=ResultatAudit.SUCCES,
                )
            )
            session.flush()
            summary = UserSummary.from_model(user)

        logger.info("Compte %s : %s (par acteur id=%s)", user_id, action, acting_user_id)
        return summary

    def reset_password(self, user_id: int, new_password: str) -> None:
        """Réinitialise le mot de passe d'un utilisateur (action administrative).

        Force ``must_change_password`` afin que le titulaire du compte soit
        contraint de le changer à sa prochaine connexion.
        """
        self._permissions.require_permission("USER_RESET_PASSWORD")
        acting_user_id = self._acting_user_id()

        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
            )

        with session_scope(self._settings) as session:
            user = session.get(User, user_id)
            if user is None:
                raise NotFoundError(f"Utilisateur {user_id} introuvable.")

            user.password_hash = hash_password(new_password)
            user.must_change_password = True
            session.add(
                AuditLog(
                    user_id=acting_user_id,
                    action="USER_RESET_PASSWORD",
                    entite="users",
                    entite_id=user_id,
                    resultat=ResultatAudit.SUCCES,
                )
            )

        logger.info("Mot de passe réinitialisé pour l'utilisateur %s (par acteur id=%s)", user_id, acting_user_id)
