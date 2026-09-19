"""Gestion des comptes utilisateurs : consultation, création,
activation/désactivation, réinitialisation de mot de passe.

Le compte administrateur initial est créé séparément par ``app.db.seed``
(mot de passe généré aléatoirement, jamais choisi) ; ``create_user`` ci-
dessous couvre la création des comptes suivants, depuis l'écran
Administration → Utilisateurs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.utils.logging_config import get_logger

if TYPE_CHECKING:
    from app.services.licensing.license_service import LicenseService

MIN_PASSWORD_LENGTH = 8
MAX_USERNAME_LENGTH = 50  # aligné sur User.username (String(50))

# Nom du rôle disposant de tous les droits (seedé par app.db.seed) — utilisé
# pour les garde-fous de protection du compte administrateur ci-dessous.
# "Administrateur" est un rôle comme un autre, jamais un compte spécial : la
# protection porte sur le nombre de comptes actifs affectés à ce rôle.
_ROLE_ADMINISTRATEUR = "Administrateur"

logger = get_logger("services.users")


def _validate_username(username: str) -> str:
    username = (username or "").strip()
    if not username:
        raise ValidationError("Le nom d'utilisateur est obligatoire.")
    if len(username) > MAX_USERNAME_LENGTH:
        raise ValidationError(
            f"Le nom d'utilisateur ne doit pas dépasser {MAX_USERNAME_LENGTH} caractères."
        )
    return username


def _validate_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
        )


@dataclass(frozen=True)
class RoleSummary:
    """Vue en lecture seule d'un rôle — utilisée pour peupler le sélecteur de
    rôle de l'écran de création d'utilisateur."""

    id: int
    nom: str


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
    def __init__(
        self,
        permission_service: PermissionService,
        settings: Optional[Settings] = None,
        license_service: Optional["LicenseService"] = None,
    ) -> None:
        self._permissions = permission_service
        self._settings = settings
        self._license_service = license_service

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def list_users(self) -> list[UserSummary]:
        self._permissions.require_permission("USER_VIEW")
        with session_scope(self._settings) as session:
            users = session.query(User).order_by(User.username).all()
            return [UserSummary.from_model(user) for user in users]

    def list_roles(self) -> list[RoleSummary]:
        """Rôles disponibles pour l'assignation à un utilisateur — utile pour
        peupler le sélecteur de rôle des écrans de création (``USER_CREATE``)
        et de modification (``USER_UPDATE``). Aucune permission dédiée : l'un
        ou l'autre suffit, pas besoin de connaître l'intention de l'appelant."""
        if not (
            self._permissions.has_permission("USER_CREATE")
            or self._permissions.has_permission("USER_UPDATE")
        ):
            raise PermissionDeniedError("Permission requise : USER_CREATE ou USER_UPDATE")
        with session_scope(self._settings) as session:
            roles = session.query(Role).order_by(Role.nom).all()
            return [RoleSummary(id=role.id, nom=role.nom) for role in roles]

    def create_user(
        self, username: str, password: str, role_id: int, actif: bool = True
    ) -> UserSummary:
        """Crée un nouvel utilisateur (écran Administration → Utilisateurs).

        Le mot de passe saisi par l'administrateur est haché avec le même
        mécanisme que partout ailleurs (``hash_password``, Argon2) — jamais
        stocké en clair. ``must_change_password`` est forcé à ``True``,
        comme pour ``reset_password`` : l'administrateur connaît ce mot de
        passe initial, son titulaire doit donc le changer dès sa première
        connexion.

        Si le compte est créé actif, c'est un deuxième point d'entrée (avec
        ``set_active(actif=True)``) qui augmente le nombre de comptes actifs :
        la limite ``max_users`` de la licence active (§12 de la phase
        Licences) est donc revérifiée ici de la même façon, pour ne jamais
        pouvoir être contournée en créant un compte plutôt qu'en réactivant
        un compte existant."""
        self._permissions.require_permission("USER_CREATE")
        acting_user_id = self._acting_user_id()

        username = _validate_username(username)
        _validate_password(password)

        with session_scope(self._settings) as session:
            role = session.get(Role, role_id)
            if role is None:
                raise NotFoundError(f"Rôle {role_id} introuvable.")

            if session.query(User).filter(User.username == username).one_or_none() is not None:
                raise ConflictError(f"Le nom d'utilisateur « {username} » est déjà utilisé.")

            if actif and self._license_service is not None:
                self._license_service.check_can_activate_user(session)

            user = User(
                username=username,
                password_hash=hash_password(password),
                role_id=role_id,
                actif=actif,
                must_change_password=True,
            )
            session.add(user)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError(f"Le nom d'utilisateur « {username} » est déjà utilisé.") from exc

            session.add(
                AuditLog(
                    user_id=acting_user_id,
                    action="USER_CREATE",
                    entite="users",
                    entite_id=user.id,
                    resultat=ResultatAudit.SUCCES,
                )
            )
            session.flush()
            summary = UserSummary.from_model(user)

        logger.info(
            "Utilisateur créé : %s (rôle id=%s, actif=%s, par acteur id=%s)",
            username, role_id, actif, acting_user_id,
        )
        return summary

    def set_active(self, user_id: int, actif: bool) -> UserSummary:
        """Active ou désactive un compte. Toujours vérifié côté service,
        indépendamment de ce que l'interface affiche ou masque.

        Activer un compte augmente le nombre de comptes actifs — tout comme
        ``create_user(actif=True)`` : c'est donc ici, comme là-bas, qu'est
        vérifiée la limite ``max_users`` de la licence active (§12) —
        comptée sur les seuls comptes actifs, un compte désactivé ne
        consommant pas de place."""
        self._permissions.require_permission("USER_ACTIVATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            user = session.get(User, user_id)
            if user is None:
                raise NotFoundError(f"Utilisateur {user_id} introuvable.")

            if not actif and user.actif and user.role.nom == _ROLE_ADMINISTRATEUR:
                other_active_admins = (
                    session.query(User)
                    .join(Role)
                    .filter(
                        Role.nom == _ROLE_ADMINISTRATEUR,
                        User.actif.is_(True),
                        User.id != user_id,
                    )
                    .count()
                )
                if other_active_admins == 0:
                    raise ValidationError(
                        "Impossible de désactiver le dernier compte Administrateur actif."
                    )

            if actif and not user.actif and self._license_service is not None:
                self._license_service.check_can_activate_user(session)

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

    def update_user(self, user_id: int, role_id: int) -> UserSummary:
        """Modifie le rôle d'un utilisateur existant (écran Administration →
        Utilisateurs). Ne modifie jamais le nom d'utilisateur (identifiant de
        connexion, hors périmètre de cette opération) ni le mot de passe.

        Le nouveau rôle ne prend effet qu'à la prochaine connexion de
        l'utilisateur concerné : les permissions d'une session déjà ouverte
        sont figées dans son ``CurrentUser`` au moment du login
        (``AuthService.login``) et ne sont jamais recalculées en cours de
        session — aucun mécanisme d'invalidation à ajouter ici.

        Protection du compte administrateur : un utilisateur ne peut pas
        retirer le rôle Administrateur de son propre compte (il resterait
        éventuellement d'autres administrateurs, mais s'auto-verrouiller
        n'est jamais une opération valide). Un autre Administrateur peut en
        revanche légitimement rétrograder un pair."""
        self._permissions.require_permission("USER_UPDATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            user = session.get(User, user_id)
            if user is None:
                raise NotFoundError(f"Utilisateur {user_id} introuvable.")

            role = session.get(Role, role_id)
            if role is None:
                raise NotFoundError(f"Rôle {role_id} introuvable.")

            if (
                user.role.nom == _ROLE_ADMINISTRATEUR
                and role.nom != _ROLE_ADMINISTRATEUR
                and user_id == acting_user_id
            ):
                raise ValidationError(
                    "Vous ne pouvez pas retirer votre propre rôle Administrateur."
                )

            # Affecté via la relation ``role`` (et non le seul ``role_id``
            # scalaire) : l'objet ``user`` reste utilisé plus bas dans cette
            # même transaction pour construire le ``UserSummary`` retourné,
            # qui lit ``user.role.nom`` — un simple ``user.role_id = role_id``
            # laisserait la relation déjà chargée (utilisée par la garde
            # ci-dessus) pointer vers l'ancien rôle jusqu'au prochain rechargement.
            user.role = role
            session.add(
                AuditLog(
                    user_id=acting_user_id,
                    action="USER_UPDATE",
                    entite="users",
                    entite_id=user_id,
                    resultat=ResultatAudit.SUCCES,
                )
            )
            session.flush()
            summary = UserSummary.from_model(user)

        logger.info(
            "Rôle modifié pour l'utilisateur %s : nouveau rôle id=%s (par acteur id=%s)",
            user_id, role_id, acting_user_id,
        )
        return summary

    def reset_password(self, user_id: int, new_password: str) -> None:
        """Réinitialise le mot de passe d'un utilisateur (action administrative).

        Force ``must_change_password`` afin que le titulaire du compte soit
        contraint de le changer à sa prochaine connexion.
        """
        self._permissions.require_permission("USER_RESET_PASSWORD")
        acting_user_id = self._acting_user_id()

        _validate_password(new_password)

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
