"""Authentification, session utilisateur et changement de mot de passe.

Toute vérification de mot de passe passe par ``app.security.password_hashing``
(Argon2) : jamais de comparaison en clair. Toute connexion, déconnexion ou
changement de mot de passe est journalisée dans ``audit_logs``.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.models.user import User
from app.security.password_hashing import hash_password, verify_password
from app.services.auth.current_user import CurrentUser
from app.utils.exceptions import (
    AccountDisabledError,
    AuthenticationError,
    InvalidCredentialsError,
    ValidationError,
)
from app.utils.logging_config import get_logger

MIN_PASSWORD_LENGTH = 8

logger = get_logger("services.auth")


def _validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
        )


class AuthService:
    """Point d'entrée unique pour l'authentification et la session courante.

    Une instance représente la session applicative (desktop, un seul
    utilisateur connecté à la fois par processus).
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings
        self._current_user: Optional[CurrentUser] = None

    @property
    def current_user(self) -> Optional[CurrentUser]:
        return self._current_user

    @property
    def is_authenticated(self) -> bool:
        return self._current_user is not None

    def _log_audit(
        self,
        session: Session,
        user_id: Optional[int],
        action: str,
        resultat: ResultatAudit,
        details: Optional[str] = None,
    ) -> None:
        session.add(
            AuditLog(
                user_id=user_id,
                action=action,
                entite="auth",
                entite_id=user_id,
                details=details,
                resultat=resultat,
            )
        )

    def login(self, username: str, password: str) -> CurrentUser:
        """Authentifie l'utilisateur et ouvre la session courante.

        Lève :class:`InvalidCredentialsError` pour un identifiant inconnu ou
        un mot de passe invalide (même exception pour les deux cas, afin de
        ne jamais révéler si un nom d'utilisateur existe), et
        :class:`AccountDisabledError` pour un compte désactivé.

        Important : l'échec est journalisé puis l'exception est levée
        **après** la sortie du bloc transactionnel, jamais à l'intérieur.
        ``session_scope`` fait un rollback complet sur toute exception non
        interceptée ; lever l'erreur à l'intérieur du bloc effacerait donc
        l'entrée d'audit qu'on vient d'y écrire.
        """
        pending_error: Optional[AuthenticationError] = None
        current_user: Optional[CurrentUser] = None

        with session_scope(self._settings) as session:
            user = session.query(User).filter_by(username=username).one_or_none()

            if user is None:
                self._log_audit(
                    session, None, "LOGIN", ResultatAudit.ECHEC,
                    f"Utilisateur inconnu : {username!r}",
                )
                pending_error = InvalidCredentialsError("Identifiant ou mot de passe incorrect.")
            elif not verify_password(password, user.password_hash):
                self._log_audit(session, user.id, "LOGIN", ResultatAudit.ECHEC, "Mot de passe invalide")
                pending_error = InvalidCredentialsError("Identifiant ou mot de passe incorrect.")
            elif not user.actif:
                self._log_audit(session, user.id, "LOGIN", ResultatAudit.ECHEC, "Compte désactivé")
                pending_error = AccountDisabledError("Ce compte est désactivé.")
            else:
                user.dernier_login = datetime.now(timezone.utc)
                # Permissions effectives = union des permissions de TOUS les
                # rôles de l'utilisateur (§2 du lot multi-rôles) — une
                # permission commune à plusieurs rôles n'apparaît qu'une
                # seule fois grâce au frozenset. Calculé ici, une fois pour
                # toutes à la connexion, jamais recalculé dynamiquement en
                # cours de session (voir docstring de UserService.update_user).
                permissions = frozenset(
                    p.code for role in user.roles for p in role.permissions
                )
                current_user = CurrentUser(
                    id=user.id,
                    username=user.username,
                    role_ids=frozenset(role.id for role in user.roles),
                    role_names=tuple(sorted(role.nom for role in user.roles)),
                    permissions=permissions,
                    must_change_password=user.must_change_password,
                )
                self._log_audit(session, user.id, "LOGIN", ResultatAudit.SUCCES)

        if pending_error is not None:
            raise pending_error

        assert current_user is not None
        self._current_user = current_user
        logger.info("Connexion réussie : %s", current_user.username)
        return current_user

    def logout(self) -> None:
        if self._current_user is None:
            return
        user_id = self._current_user.id
        username = self._current_user.username
        with session_scope(self._settings) as session:
            self._log_audit(session, user_id, "LOGOUT", ResultatAudit.SUCCES)
        self._current_user = None
        logger.info("Déconnexion : %s", username)

    def change_password(self, old_password: str, new_password: str) -> None:
        """Change le mot de passe de l'utilisateur actuellement connecté.

        Exige la connaissance du mot de passe actuel, même pour le
        changement obligatoire du mot de passe temporaire initial.
        """
        if self._current_user is None:
            raise InvalidCredentialsError("Aucun utilisateur connecté.")

        user_id = self._current_user.id
        pending_error: Optional[InvalidCredentialsError] = None

        with session_scope(self._settings) as session:
            user = session.get(User, user_id)
            if user is None or not verify_password(old_password, user.password_hash):
                self._log_audit(
                    session, user_id, "PASSWORD_CHANGE", ResultatAudit.ECHEC,
                    "Mot de passe actuel invalide",
                )
                pending_error = InvalidCredentialsError("Mot de passe actuel invalide.")
            else:
                _validate_password_strength(new_password)
                user.password_hash = hash_password(new_password)
                user.must_change_password = False
                self._log_audit(session, user_id, "PASSWORD_CHANGE", ResultatAudit.SUCCES)

        if pending_error is not None:
            raise pending_error

        self._current_user = replace(self._current_user, must_change_password=False)
        logger.info("Mot de passe changé : %s", self._current_user.username)
