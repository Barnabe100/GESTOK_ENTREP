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
from typing import TYPE_CHECKING, Optional, Sequence

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


def _validate_role_ids(role_ids: Sequence[int]) -> list[int]:
    """Un utilisateur doit avoir au moins un rôle, jamais deux fois le même
    (§7 du lot multi-rôles) — vérifié ici, côté service, avant toute
    résolution en base : jamais uniquement côté interface."""
    role_ids = list(role_ids or [])
    if not role_ids:
        raise ValidationError("Veuillez sélectionner au moins un rôle.")
    if len(role_ids) != len(set(role_ids)):
        raise ValidationError("Un même rôle ne peut pas être attribué deux fois au même utilisateur.")
    return role_ids


def _resolve_roles(session, role_ids: Sequence[int]) -> list[Role]:
    """Résout et retourne les ``Role`` correspondant à ``role_ids``, dans
    l'ordre fourni. Lève ``NotFoundError`` au premier identifiant inconnu."""
    roles: list[Role] = []
    for role_id in role_ids:
        role = session.get(Role, role_id)
        if role is None:
            raise NotFoundError(f"Rôle {role_id} introuvable.")
        roles.append(role)
    return roles


@dataclass(frozen=True)
class UserSummary:
    """Vue en lecture seule d'un utilisateur, sans le hash de mot de passe.

    ``role_ids``/``role_names`` sont des tuples triés par nom de rôle
    (ordre stable et déterministe pour l'affichage comme pour les tests) —
    un utilisateur a toujours au moins un rôle (§7), jamais aucun."""

    id: int
    username: str
    role_ids: tuple[int, ...]
    role_names: tuple[str, ...]
    actif: bool
    dernier_login: Optional[datetime]

    @classmethod
    def from_model(cls, user: User) -> "UserSummary":
        ordered_roles = sorted(user.roles, key=lambda role: role.nom)
        return cls(
            id=user.id,
            username=user.username,
            role_ids=tuple(role.id for role in ordered_roles),
            role_names=tuple(role.nom for role in ordered_roles),
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
        self, username: str, password: str, role_ids: Sequence[int], actif: bool = True
    ) -> UserSummary:
        """Crée un nouvel utilisateur (écran Administration → Utilisateurs).

        ``role_ids`` : un ou plusieurs rôles (§1/§7 du lot multi-rôles) —
        jamais vide, jamais de doublon (voir ``_validate_role_ids``). Un même
        compte garde un seul mot de passe, quel que soit le nombre de rôles.
        La colonne historique ``User.role_id`` (conservée pour compatibilité,
        voir son commentaire dans ``app/models/user.py``) est renseignée avec
        le premier rôle fourni ; ``User.roles`` (la collection complète) est
        la seule source de vérité pour les permissions et l'appartenance
        réelle aux rôles.

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
        un compte existant. Un utilisateur ayant plusieurs rôles ne compte
        jamais que pour un seul compte actif (§10 du lot multi-rôles) : la
        limite porte sur le nombre de lignes ``User``, jamais sur le nombre
        de rôles détenus."""
        self._permissions.require_permission("USER_CREATE")
        acting_user_id = self._acting_user_id()

        username = _validate_username(username)
        _validate_password(password)
        role_ids = _validate_role_ids(role_ids)

        with session_scope(self._settings) as session:
            roles = _resolve_roles(session, role_ids)

            if session.query(User).filter(User.username == username).one_or_none() is not None:
                raise ConflictError(f"Le nom d'utilisateur « {username} » est déjà utilisé.")

            if actif and self._license_service is not None:
                self._license_service.check_can_activate_user(session)

            user = User(
                username=username,
                password_hash=hash_password(password),
                role_id=roles[0].id,
                roles=roles,
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
            "Utilisateur créé : %s (rôles id=%s, actif=%s, par acteur id=%s)",
            username, role_ids, actif, acting_user_id,
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

            is_administrateur = any(role.nom == _ROLE_ADMINISTRATEUR for role in user.roles)
            if not actif and user.actif and is_administrateur:
                other_active_admins = (
                    session.query(User)
                    .filter(
                        User.roles.any(Role.nom == _ROLE_ADMINISTRATEUR),
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

    def update_user(self, user_id: int, role_ids: Sequence[int]) -> UserSummary:
        """Modifie les rôles d'un utilisateur existant (écran Administration →
        Utilisateurs). Remplace intégralement l'ensemble de ses rôles —
        même convention que le remplacement complet des lignes d'un
        brouillon Entrée/Sortie/Vente : pour conserver les rôles actuels
        sans les modifier, l'appelant (UI) doit les fournir à nouveau (voir
        ``EditUserDialog``, pré-coché avec ``UserSummary.role_ids``). Ne
        modifie jamais le nom d'utilisateur (identifiant de connexion, hors
        périmètre de cette opération) ni le mot de passe.

        ``role_ids`` : un ou plusieurs rôles, jamais vide, jamais de doublon
        (voir ``_validate_role_ids``). La colonne historique ``User.role_id``
        est mise à jour avec le premier rôle fourni (voir ``create_user``).

        Les nouveaux rôles ne prennent effet qu'à la prochaine connexion de
        l'utilisateur concerné : les permissions d'une session déjà ouverte
        sont figées dans son ``CurrentUser`` au moment du login
        (``AuthService.login``) et ne sont jamais recalculées en cours de
        session — aucun mécanisme d'invalidation à ajouter ici.

        Protection du compte administrateur : un utilisateur ne peut pas
        retirer le rôle Administrateur de son propre compte (il resterait
        éventuellement d'autres administrateurs, mais s'auto-verrouiller
        n'est jamais une opération valide). Un autre Administrateur peut en
        revanche légitimement rétrograder un pair, à condition qu'il reste
        au moins un Administrateur actif après l'opération — même garde-fou
        que ``set_active`` (compte des administrateurs actifs autres que la
        cible), appliqué ici indépendamment du rôle de l'acteur : un rôle
        non-Administrateur ayant reçu ``USER_UPDATE`` via l'écran
        Rôles/Permissions ne doit pas non plus pouvoir supprimer le dernier
        Administrateur actif. Ce garde-fou porte sur l'ensemble RÉEL des
        rôles (Administrateur peut désormais être un rôle secondaire parmi
        d'autres), jamais sur un seul rôle « principal »."""
        self._permissions.require_permission("USER_UPDATE")
        acting_user_id = self._acting_user_id()
        role_ids = _validate_role_ids(role_ids)

        with session_scope(self._settings) as session:
            user = session.get(User, user_id)
            if user is None:
                raise NotFoundError(f"Utilisateur {user_id} introuvable.")

            new_roles = _resolve_roles(session, role_ids)
            new_role_names = {role.nom for role in new_roles}

            was_administrateur = any(role.nom == _ROLE_ADMINISTRATEUR for role in user.roles)
            demoting_active_administrateur = (
                was_administrateur
                and _ROLE_ADMINISTRATEUR not in new_role_names
                and user.actif
            )

            if demoting_active_administrateur and user_id == acting_user_id:
                raise ValidationError(
                    "Vous ne pouvez pas retirer votre propre rôle Administrateur."
                )

            if demoting_active_administrateur:
                other_active_admins = (
                    session.query(User)
                    .filter(
                        User.roles.any(Role.nom == _ROLE_ADMINISTRATEUR),
                        User.actif.is_(True),
                        User.id != user_id,
                    )
                    .count()
                )
                if other_active_admins == 0:
                    raise ValidationError(
                        "Impossible de retirer le rôle Administrateur du dernier compte "
                        "Administrateur actif."
                    )

            user.roles = new_roles
            user.role_id = new_roles[0].id
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
            "Rôles modifiés pour l'utilisateur %s : nouveaux rôles id=%s (par acteur id=%s)",
            user_id, role_ids, acting_user_id,
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
