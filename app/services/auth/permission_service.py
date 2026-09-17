"""Contrôle centralisé des permissions (RBAC) et, depuis la phase Licences,
des droits portés par la licence active (§7-8 du cahier des charges).

Point unique de vérification : toute vue ou tout service qui doit décider si
une action est autorisée passe par ``has_permission`` (affichage) ou
``require_permission`` (exécution, lève si refusé). Aucune condition de rôle
ni de licence ne doit être écrite ailleurs dans le code.

Une action requiert la permission RBAC de l'utilisateur ET, lorsque cette
permission est associée à une fonctionnalité licenciée (voir
``permission_to_feature``), que la licence active l'autorise (§8 : même un
Administrateur ne peut pas contourner une restriction de licence). Les deux
contrôles sont indépendants : RBAC = droits de l'utilisateur, licence =
droits du produit.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Optional

from app.services.auth.auth_service import AuthService
from app.services.auth.current_user import CurrentUser
from app.utils.exceptions import LicenseError, PermissionDeniedError

if TYPE_CHECKING:
    from app.services.licensing.feature_gate import FeatureGate


class PermissionService:
    def __init__(
        self,
        auth_service: AuthService,
        feature_gate: Optional["FeatureGate"] = None,
        permission_to_feature: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._auth_service = auth_service
        self._feature_gate = feature_gate
        self._permission_to_feature = permission_to_feature or {}

    def set_feature_gate(self, feature_gate: "FeatureGate") -> None:
        """Rattachement différé : ``FeatureGate`` dépend de ``LicenseService``,
        qui dépend lui-même de ce ``PermissionService`` (pour vérifier
        ``LICENSE_VIEW``/``LICENSE_ACTIVATE``) — voir l'ordre de construction
        dans ``app.services.registry.build_service_registry``."""
        self._feature_gate = feature_gate

    @property
    def current_user(self) -> Optional[CurrentUser]:
        return self._auth_service.current_user

    def _required_feature(self, code: str) -> Optional[str]:
        return self._permission_to_feature.get(code)

    def has_permission(self, code: str) -> bool:
        user = self.current_user
        if user is None or not user.has_permission(code):
            return False
        feature = self._required_feature(code)
        if feature is None or self._feature_gate is None:
            return True
        return self._feature_gate.can(feature)

    def require_permission(self, code: str) -> None:
        """Lève :class:`PermissionDeniedError` si l'utilisateur n'a pas la
        permission RBAC, ou :class:`LicenseError` si la licence active ne
        couvre pas la fonctionnalité associée — deux causes de refus
        distinctes, pour que l'utilisateur comprenne s'il doit demander un
        droit à son administrateur ou une mise à niveau de licence.

        C'est ce contrôle, exécuté côté service, qui empêche un contournement
        par manipulation de l'interface : même si un écran restait accessible
        par erreur, l'action sous-jacente resterait refusée ici.
        """
        user = self.current_user
        if user is None or not user.has_permission(code):
            raise PermissionDeniedError(f"Permission requise : {code}")

        feature = self._required_feature(code)
        if feature is not None and self._feature_gate is not None and not self._feature_gate.can(feature):
            raise LicenseError(
                f"Cette fonctionnalité ({feature}) n'est pas incluse dans la licence active, "
                "ou aucune licence valide n'est présente."
            )
