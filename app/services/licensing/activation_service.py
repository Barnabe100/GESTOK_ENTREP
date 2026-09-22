"""Orchestration du choix de mode d'activation (LOCAL/SERVER, voir
``ActivationMode``) — ne remplace jamais ``LicenseService``, qui reste
l'unique autorité de validation cryptographique et de stockage des licences
(voir son docstring). Cette classe décide seulement, selon le mode configuré
pour CETTE installation, si une activation passe directement par
``LicenseService`` (LOCAL, comportement strictement inchangé) ou doit
d'abord obtenir l'autorisation d'un serveur TechNova (SERVER, préparé mais
non implémenté à ce stade — voir ``LicenseServerClient``).
"""
from __future__ import annotations

from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.repositories.parameter_repository import ParameterRepository
from app.services.auth.permission_service import PermissionService
from app.services.licensing.activation_mode import ActivationMode
from app.services.licensing.license_server_client import LicenseServerClient
from app.services.licensing.license_service import LicenseInfo, LicenseService

_KEY_ACTIVATION_MODE = "activation.mode"


class ActivationService:
    def __init__(
        self,
        license_service: LicenseService,
        license_server_client: LicenseServerClient,
        permission_service: PermissionService,
        settings: Optional[Settings] = None,
    ) -> None:
        self._license_service = license_service
        self._license_server_client = license_server_client
        self._permissions = permission_service
        self._settings = settings

    # -- mode d'activation --------------------------------------------------

    def get_mode(self) -> ActivationMode:
        self._permissions.require_permission("LICENSE_VIEW")
        return self._read_mode()

    def set_mode(self, mode: ActivationMode) -> None:
        self._permissions.require_permission("LICENSE_ACTIVATE")
        # ActivationMode(mode) normalise aussi bien un membre d'énumération
        # qu'une simple chaîne "LOCAL"/"SERVER" (ex. une valeur repassée par
        # un widget Qt qui a déballé le sous-type ``str``) — jamais de
        # confiance aveugle dans le type exact fourni par l'appelant.
        mode = ActivationMode(mode)
        with session_scope(self._settings) as session:
            ParameterRepository(session).set_value(_KEY_ACTIVATION_MODE, mode.value)

    def _read_mode(self) -> ActivationMode:
        """Sans vérification de permission : utilisé en interne par
        ``activate()``, qui a déjà sa propre vérification via
        ``LicenseService``/``LicenseServerClient`` — évite un couplage
        fragile entre ``LICENSE_VIEW`` et ``LICENSE_ACTIVATE``."""
        with session_scope(self._settings) as session:
            stored = ParameterRepository(session).get_value(_KEY_ACTIVATION_MODE)
        return ActivationMode.from_stored_value(stored)

    # -- activation ---------------------------------------------------------

    def activate(self, file_content: str) -> LicenseInfo:
        """Point d'entrée unique d'activation, quel que soit le mode.

        LOCAL : délègue entièrement à ``LicenseService.activate_license()``
        — comportement strictement identique à avant l'introduction du mode
        d'activation.

        SERVER : valide intégralement la licence en local (même logique que
        LOCAL, jamais dupliquée — voir
        ``LicenseService.validate_license_content``), MAIS ne l'enregistre
        jamais avant l'autorisation du serveur. Comme aucun serveur réel
        n'existe à ce stade, ``LicenseServerClient`` lève systématiquement
        une erreur explicite : une tentative SERVER ne peut donc jamais être
        confondue avec une activation réussie, même si la licence est
        localement valide."""
        mode = self._read_mode()
        if mode is ActivationMode.SERVER:
            return self._activate_via_server(file_content)
        return self._license_service.activate_license(file_content)

    def _activate_via_server(self, file_content: str) -> LicenseInfo:
        # Validation cryptographique locale complète, SANS enregistrement :
        # le serveur pourra encore refuser (quota max_devices, révocation)
        # une fois qu'il existera réellement — rien n'est persisté avant son
        # autorisation, même si la licence est valide localement.
        payload = self._license_service.validate_license_content(file_content)
        device_id = self._license_service.get_device_id()
        return self._license_server_client.activate(payload, device_id)
