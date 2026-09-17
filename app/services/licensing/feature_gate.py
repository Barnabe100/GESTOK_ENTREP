"""``FeatureGate`` : point de contrôle unique des fonctionnalités licenciées
(§7). Jamais de ``if edition == "PROFESSIONAL"`` dispersé dans les vues ou
les services — tout contrôle fonctionnel passe par ``can``/``require``, qui
ne s'appuient que sur la liste ``features`` de la charge utile signée
courante (via ``LicenseService``)."""
from __future__ import annotations

from app.services.licensing.license_service import LicenseService, LicenseState
from app.utils.exceptions import LicenseError


class FeatureGate:
    def __init__(self, license_service: LicenseService) -> None:
        self._license_service = license_service

    def can(self, feature_code: str) -> bool:
        info = self._license_service.evaluate()
        return info.state == LicenseState.VALID and feature_code in info.features

    def require(self, feature_code: str) -> None:
        if not self.can(feature_code):
            raise LicenseError(
                f"Cette fonctionnalité ({feature_code}) n'est pas incluse dans la licence active, "
                "ou aucune licence valide n'est présente."
            )
