"""Abstraction du futur serveur TechNova de licences (activation centralisée,
comptage réel de ``max_devices``) — voir l'architecture LOCAL/SERVER validée
pour StockManager Desktop.

AUCUNE implémentation réseau n'existe à ce stade. ``UnconfiguredLicenseServerClient``
ci-dessous est la seule implémentation fournie : elle lève systématiquement
``LicenseServerUnavailableError``, jamais une simulation qui ferait croire à
une activation réussie. Le jour où le serveur existera réellement, une
nouvelle implémentation de ``LicenseServerClient`` (client HTTP réel) pourra
la remplacer dans ``app.services.registry`` sans qu'``ActivationService`` ait
à changer : c'est tout l'intérêt de cette interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.licensing.license_payload import LicensePayload
from app.services.licensing.license_service import LicenseInfo
from app.utils.exceptions import LicenseServerUnavailableError

_NOT_CONFIGURED_MESSAGE = "Le serveur TechNova n'est pas encore configuré."


class LicenseServerClient(ABC):
    """Contrat que devra respecter le futur client HTTP réel — trois
    opérations, correspondant aux trois actions du protocole d'activation
    centralisée décrit dans l'architecture LOCAL/SERVER : activer une
    installation, la désactiver (libération de slot lors d'un changement de
    poste), vérifier périodiquement son état (check-in)."""

    @abstractmethod
    def activate(self, license_payload: LicensePayload, device_id: str) -> LicenseInfo:
        """Demande l'autorisation d'activer ``license_payload`` pour
        l'appareil ``device_id``. ``license_payload`` doit déjà avoir été
        validé cryptographiquement en local (voir
        ``LicenseService.validate_license_content``) — cette méthode ne doit
        jamais être appelée avant cette validation locale."""

    @abstractmethod
    def deactivate(self, device_id: str) -> None:
        """Libère le slot d'activation associé à ``device_id`` (changement
        de poste)."""

    @abstractmethod
    def check(self, device_id: str) -> LicenseInfo:
        """Revalide l'état d'activation auprès du serveur (check-in
        périodique)."""


class UnconfiguredLicenseServerClient(LicenseServerClient):
    """Implémentation temporaire, utilisée tant qu'aucun serveur TechNova
    réel n'existe. Ne simule jamais un succès : chaque opération lève
    explicitement ``LicenseServerUnavailableError``, pour qu'une tentative
    d'activation en mode SERVER ne puisse jamais être confondue avec une
    activation réussie — même si la licence fournie est par ailleurs valide
    localement."""

    def activate(self, license_payload: LicensePayload, device_id: str) -> LicenseInfo:
        raise LicenseServerUnavailableError(_NOT_CONFIGURED_MESSAGE)

    def deactivate(self, device_id: str) -> None:
        raise LicenseServerUnavailableError(_NOT_CONFIGURED_MESSAGE)

    def check(self, device_id: str) -> LicenseInfo:
        raise LicenseServerUnavailableError(_NOT_CONFIGURED_MESSAGE)
