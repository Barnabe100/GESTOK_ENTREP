"""Gestion des clients : consultation, recherche, création, modification,
activation/désactivation.

Mêmes principes que le module Fournisseurs : aucune suppression physique, un
client désactivé reste consultable (en particulier dans l'historique des
ventes qui lui sont associées, géré par ``SaleService`` — ce service-ci ne
connaît rien des ventes), mais ne doit plus être proposé pour une nouvelle
vente (voir ``list_clients(..., include_inactive=False)``, utilisé par le
sélecteur de client de ``SaleFormDialog``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.client import Client
from app.models.enums import ResultatAudit, StatutActifInactif
from app.repositories.client_repository import ClientRepository
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.clients")

# Sentinel distinguant « champ non fourni » (conserver la valeur actuelle lors
# d'une modification) de ``None``/chaîne vide (effacer explicitement le champ).
_UNSET = object()

_MAX_LENGTHS = {
    "nom": 150,
    "telephone": 30,
    "email": 150,
    "adresse": 255,
    "observations": 500,
}


@dataclass(frozen=True)
class ClientSummary:
    """Vue en lecture seule d'un client."""

    id: int
    nom: str
    telephone: Optional[str]
    email: Optional[str]
    adresse: Optional[str]
    observations: Optional[str]
    actif: bool
    date_creation: datetime
    date_modification: datetime

    @classmethod
    def from_model(cls, client: Client) -> "ClientSummary":
        return cls(
            id=client.id,
            nom=client.nom,
            telephone=client.telephone,
            email=client.email,
            adresse=client.adresse,
            observations=client.observations,
            actif=client.statut == StatutActifInactif.ACTIF,
            date_creation=client.date_creation,
            date_modification=client.date_modification,
        )


def _clean_optional(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    max_length = _MAX_LENGTHS[field_name]
    if len(value) > max_length:
        raise ValidationError(f"Le champ « {field_name} » ne doit pas dépasser {max_length} caractères.")
    return value


def _validate_name(nom: str) -> str:
    nom = (nom or "").strip()
    if not nom:
        raise ValidationError("Le nom du client est obligatoire.")
    if len(nom) > _MAX_LENGTHS["nom"]:
        raise ValidationError(f"Le nom du client ne doit pas dépasser {_MAX_LENGTHS['nom']} caractères.")
    return nom


def _validate_email(email: Optional[str]) -> Optional[str]:
    email = _clean_optional(email, "email")
    if email is not None and "@" not in email:
        raise ValidationError("L'adresse email du client n'est pas valide.")
    return email


class ClientService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, client_id: Optional[int]) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="clients",
                entite_id=client_id,
                resultat=ResultatAudit.SUCCES,
            )
        )

    def _apply_all_fields(
        self,
        client: Client,
        nom: str,
        telephone: Optional[str],
        email: Optional[str],
        adresse: Optional[str],
        observations: Optional[str],
    ) -> None:
        """Renseigne tous les champs (utilisé à la création : un
        enregistrement neuf n'a pas de valeur existante à préserver)."""
        client.nom = _validate_name(nom)
        client.telephone = _clean_optional(telephone, "telephone")
        client.email = _validate_email(email)
        client.adresse = _clean_optional(adresse, "adresse")
        client.observations = _clean_optional(observations, "observations")

    def _apply_provided_fields(self, client: Client, nom: str, telephone, email, adresse, observations) -> None:
        """Ne modifie que les champs explicitement fournis (utilisé à la
        modification) : un champ omis (``_UNSET``) conserve sa valeur
        actuelle plutôt que d'être silencieusement effacé."""
        client.nom = _validate_name(nom)
        if telephone is not _UNSET:
            client.telephone = _clean_optional(telephone, "telephone")
        if email is not _UNSET:
            client.email = _validate_email(email)
        if adresse is not _UNSET:
            client.adresse = _clean_optional(adresse, "adresse")
        if observations is not _UNSET:
            client.observations = _clean_optional(observations, "observations")

    # -- consultation -----------------------------------------------------------

    def list_clients(self, search: str = "", include_inactive: bool = True) -> list[ClientSummary]:
        self._permissions.require_permission("CLIENT_VIEW")
        with session_scope(self._settings) as session:
            repo = ClientRepository(session)
            clients = repo.search(search, include_inactive=include_inactive)
            return [ClientSummary.from_model(c) for c in clients]

    def get_client(self, client_id: int) -> ClientSummary:
        self._permissions.require_permission("CLIENT_VIEW")
        with session_scope(self._settings) as session:
            repo = ClientRepository(session)
            client = repo.get_by_id(client_id)
            if client is None:
                raise NotFoundError(f"Client {client_id} introuvable.")
            return ClientSummary.from_model(client)

    # -- création / modification -------------------------------------------------

    def create_client(
        self,
        nom: str,
        *,
        telephone: Optional[str] = None,
        email: Optional[str] = None,
        adresse: Optional[str] = None,
        observations: Optional[str] = None,
    ) -> ClientSummary:
        self._permissions.require_permission("CLIENT_CREATE")

        with session_scope(self._settings) as session:
            client = Client(statut=StatutActifInactif.ACTIF)
            self._apply_all_fields(client, nom, telephone, email, adresse, observations)
            session.add(client)
            session.flush()

            self._audit(session, "CLIENT_CREATE", client.id)
            summary = ClientSummary.from_model(client)

        logger.info("Client créé : %s", summary.nom)
        return summary

    def update_client(
        self,
        client_id: int,
        nom: str,
        *,
        telephone=_UNSET,
        email=_UNSET,
        adresse=_UNSET,
        observations=_UNSET,
    ) -> ClientSummary:
        """Modifie un client. ``nom`` est toujours requis ; les autres
        champs, s'ils ne sont pas fournis, conservent leur valeur actuelle
        (jamais effacés silencieusement) — passer explicitement ``None`` ou
        une chaîne vide pour effacer un champ."""
        self._permissions.require_permission("CLIENT_UPDATE")

        with session_scope(self._settings) as session:
            repo = ClientRepository(session)
            client = repo.get_by_id(client_id)
            if client is None:
                raise NotFoundError(f"Client {client_id} introuvable.")

            self._apply_provided_fields(client, nom, telephone, email, adresse, observations)
            session.flush()

            self._audit(session, "CLIENT_UPDATE", client.id)
            summary = ClientSummary.from_model(client)

        logger.info("Client modifié : id=%s -> %s", client_id, summary.nom)
        return summary

    # -- activation / désactivation -----------------------------------------------

    def activate_client(self, client_id: int) -> ClientSummary:
        self._permissions.require_permission("CLIENT_ACTIVATE")
        return self._set_status(client_id, StatutActifInactif.ACTIF, "CLIENT_ACTIVATE")

    def deactivate_client(self, client_id: int) -> ClientSummary:
        """Désactivation (jamais de suppression physique) : l'historique des
        ventes déjà associées à ce client reste entièrement consultable, le
        client n'est simplement plus proposé pour une nouvelle vente."""
        self._permissions.require_permission("CLIENT_DEACTIVATE")
        return self._set_status(client_id, StatutActifInactif.INACTIF, "CLIENT_DEACTIVATE")

    def _set_status(self, client_id: int, statut: StatutActifInactif, action: str) -> ClientSummary:
        with session_scope(self._settings) as session:
            repo = ClientRepository(session)
            client = repo.get_by_id(client_id)
            if client is None:
                raise NotFoundError(f"Client {client_id} introuvable.")

            client.statut = statut
            self._audit(session, action, client.id)
            session.flush()
            summary = ClientSummary.from_model(client)

        logger.info("Client id=%s : %s", client_id, action)
        return summary
