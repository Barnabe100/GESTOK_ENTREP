"""Administration des rôles et permissions (Lot C).

Strictement limité à la V1 validée : consultation des 4 rôles système et
modification de leurs permissions. Ne crée, ne renomme, ne supprime et ne
désactive aucun rôle — ces opérations sont explicitement hors périmètre.

Garde-fou critique : le rôle nommé exactement ``"Administrateur"`` ne peut
jamais perdre les permissions nécessaires à l'administration RBAC
elle-même (``ROLE_VIEW``, ``ROLE_UPDATE``) ni la gestion des comptes
utilisateurs (``USER_VIEW``, ``USER_UPDATE``) — sans quoi la fonctionnalité
s'auto-verrouillerait, sans recours possible depuis l'interface. Ce module
ne dépend d'aucune manière de ``UserService`` (non modifié par ce lot) :
la comparaison du nom de rôle est dupliquée ici volontairement, exactement
comme chaque service métier de l'application définit ses propres
constantes plutôt que de partager un état mutable entre modules.
"""
from __future__ import annotations

from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.repositories.role_repository import RoleRepository
from app.services.auth.permission_service import PermissionService
from app.services.roles.role_summary import PermissionSummary, RoleSummary
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.logging_config import get_logger

# Rôle disposant de tous les droits (seedé par app.db.seed) — jamais un
# compte spécial, un rôle comme un autre, mais dont la perte des permissions
# ci-dessous rendrait l'administration RBAC elle-même impossible.
_ROLE_ADMINISTRATEUR = "Administrateur"

# Permissions que le rôle Administrateur ne peut jamais perdre : celles qui
# permettent de revenir sur une mauvaise configuration RBAC (ROLE_*) et de
# gérer les comptes utilisateurs (USER_*), seul autre levier d'administration.
_PROTECTED_ADMIN_PERMISSIONS = frozenset({"ROLE_VIEW", "ROLE_UPDATE", "USER_VIEW", "USER_UPDATE"})

logger = get_logger("services.roles")


class RoleService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def list_roles(self) -> list[RoleSummary]:
        self._permissions.require_permission("ROLE_VIEW")
        with session_scope(self._settings) as session:
            repo = RoleRepository(session)
            return [
                RoleSummary.from_model(role, repo.count_active_users(role.id))
                for role in repo.list_roles()
            ]

    def list_permissions(self) -> list[PermissionSummary]:
        """Toutes les permissions déclarées, triées par module puis libellé
        (voir ``RoleRepository.list_permissions``) — l'appelant (UI) les
        regroupe par ``module`` pour l'affichage, jamais une liste
        redéfinie ailleurs dans le code."""
        self._permissions.require_permission("ROLE_VIEW")
        with session_scope(self._settings) as session:
            repo = RoleRepository(session)
            return [PermissionSummary.from_model(p) for p in repo.list_permissions()]

    def get_role_permissions(self, role_id: int) -> list[str]:
        self._permissions.require_permission("ROLE_VIEW")
        with session_scope(self._settings) as session:
            codes = RoleRepository(session).get_role_permission_codes(role_id)
            if codes is None:
                raise NotFoundError(f"Rôle {role_id} introuvable.")
            return codes

    def update_role_permissions(self, role_id: int, permission_codes: list[str]) -> RoleSummary:
        """Remplace intégralement les permissions du rôle par
        ``permission_codes``. Vérifie, dans cet ordre : la permission
        ``ROLE_UPDATE`` ; l'existence du rôle ; que chaque code demandé
        correspond à une permission réellement déclarée ; le garde-fou
        Administrateur ; le garde-fou « rôle avec utilisateurs actifs ne
        peut pas se retrouver sans aucune permission ». Ne modifie jamais
        ``User``/``password_hash`` ni aucune autre entité que ``Role`` et
        son association ``role_permissions``.
        """
        self._permissions.require_permission("ROLE_UPDATE")
        acting_user_id = self._acting_user_id()
        codes = sorted(set(permission_codes))

        with session_scope(self._settings) as session:
            repo = RoleRepository(session)
            role = repo.get_by_id(role_id)
            if role is None:
                raise NotFoundError(f"Rôle {role_id} introuvable.")

            available = {p.code: p for p in repo.list_permissions()}
            unknown_codes = [code for code in codes if code not in available]
            if unknown_codes:
                raise ValidationError(
                    f"Permission(s) inconnue(s) : {', '.join(unknown_codes)}."
                )

            if role.nom == _ROLE_ADMINISTRATEUR:
                missing = _PROTECTED_ADMIN_PERMISSIONS - set(codes)
                if missing:
                    raise ValidationError(
                        "Impossible de retirer au rôle Administrateur les permissions "
                        "nécessaires à l'administration : " + ", ".join(sorted(missing)) + "."
                    )

            active_users = repo.count_active_users(role_id)
            if active_users > 0 and not codes:
                raise ValidationError(
                    "Impossible de retirer toutes les permissions d'un rôle ayant des "
                    "utilisateurs actifs."
                )

            repo.update_role_permissions(role, [available[code] for code in codes])

            session.add(
                AuditLog(
                    user_id=acting_user_id,
                    action="ROLE_UPDATE",
                    entite="roles",
                    entite_id=role_id,
                    resultat=ResultatAudit.SUCCES,
                    details=f"permissions={','.join(codes) if codes else '(aucune)'}",
                )
            )
            session.flush()
            summary = RoleSummary.from_model(role, active_users)

        logger.info(
            "Permissions du rôle %s mises à jour (par acteur id=%s) : %s",
            role_id, acting_user_id, codes,
        )
        return summary
