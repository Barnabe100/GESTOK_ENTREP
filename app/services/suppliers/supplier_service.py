"""Gestion des fournisseurs : consultation, recherche, création, modification,
activation/désactivation.

Mêmes principes que le module Catégories : aucune suppression physique, un
fournisseur désactivé reste consultable pour préserver l'historique, mais ne
doit plus être proposé pour de nouvelles opérations (voir
``list_suppliers(..., include_inactive=False)``, destiné aux futurs modules
Articles/Entrées).

Contrairement aux catégories, le modèle validé ne définit aucune contrainte
d'unicité sur le nom d'un fournisseur (deux fournisseurs distincts peuvent
légitimement partager une raison sociale) : aucune vérification d'unicité
n'est donc appliquée ici, par fidélité au modèle de données déjà validé.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.catalog import Supplier
from app.models.enums import ResultatAudit, StatutActifInactif
from app.repositories.supplier_repository import SupplierRepository
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.suppliers")

# Sentinel distinguant « champ non fourni » (conserver la valeur actuelle lors
# d'une modification) de ``None``/chaîne vide (effacer explicitement le champ).
_UNSET = object()

_MAX_LENGTHS = {
    "nom": 150,
    "contact": 150,
    "telephone": 30,
    "email": 150,
    "adresse": 255,
    "ville": 100,
    "pays": 100,
    "observations": 500,
}


@dataclass(frozen=True)
class SupplierSummary:
    """Vue en lecture seule d'un fournisseur."""

    id: int
    nom: str
    contact: Optional[str]
    telephone: Optional[str]
    email: Optional[str]
    adresse: Optional[str]
    ville: Optional[str]
    pays: Optional[str]
    observations: Optional[str]
    actif: bool
    date_creation: datetime
    date_modification: datetime

    @classmethod
    def from_model(cls, supplier: Supplier) -> "SupplierSummary":
        return cls(
            id=supplier.id,
            nom=supplier.nom,
            contact=supplier.contact,
            telephone=supplier.telephone,
            email=supplier.email,
            adresse=supplier.adresse,
            ville=supplier.ville,
            pays=supplier.pays,
            observations=supplier.observations,
            actif=supplier.statut == StatutActifInactif.ACTIF,
            date_creation=supplier.date_creation,
            date_modification=supplier.date_modification,
        )


def _clean_optional(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    max_length = _MAX_LENGTHS[field_name]
    if len(value) > max_length:
        raise ValidationError(
            f"Le champ « {field_name} » ne doit pas dépasser {max_length} caractères."
        )
    return value


def _validate_name(nom: str) -> str:
    nom = (nom or "").strip()
    if not nom:
        raise ValidationError("Le nom (raison sociale) du fournisseur est obligatoire.")
    if len(nom) > _MAX_LENGTHS["nom"]:
        raise ValidationError(
            f"Le nom du fournisseur ne doit pas dépasser {_MAX_LENGTHS['nom']} caractères."
        )
    return nom


def _validate_email(email: Optional[str]) -> Optional[str]:
    email = _clean_optional(email, "email")
    if email is not None and "@" not in email:
        raise ValidationError("L'adresse email du fournisseur n'est pas valide.")
    return email


class SupplierService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, supplier_id: Optional[int]) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="fournisseurs",
                entite_id=supplier_id,
                resultat=ResultatAudit.SUCCES,
            )
        )

    def _apply_all_fields(
        self,
        supplier: Supplier,
        nom: str,
        contact: Optional[str],
        telephone: Optional[str],
        email: Optional[str],
        adresse: Optional[str],
        ville: Optional[str],
        pays: Optional[str],
        observations: Optional[str],
    ) -> None:
        """Renseigne tous les champs (utilisé à la création : un enregistrement
        neuf n'a pas de valeur existante à préserver)."""
        supplier.nom = _validate_name(nom)
        supplier.contact = _clean_optional(contact, "contact")
        supplier.telephone = _clean_optional(telephone, "telephone")
        supplier.email = _validate_email(email)
        supplier.adresse = _clean_optional(adresse, "adresse")
        supplier.ville = _clean_optional(ville, "ville")
        supplier.pays = _clean_optional(pays, "pays")
        supplier.observations = _clean_optional(observations, "observations")

    def _apply_provided_fields(
        self,
        supplier: Supplier,
        nom: str,
        contact,
        telephone,
        email,
        adresse,
        ville,
        pays,
        observations,
    ) -> None:
        """Ne modifie que les champs explicitement fournis (utilisé à la
        modification) : un champ omis (``_UNSET``) conserve sa valeur actuelle
        plutôt que d'être silencieusement effacé."""
        supplier.nom = _validate_name(nom)
        if contact is not _UNSET:
            supplier.contact = _clean_optional(contact, "contact")
        if telephone is not _UNSET:
            supplier.telephone = _clean_optional(telephone, "telephone")
        if email is not _UNSET:
            supplier.email = _validate_email(email)
        if adresse is not _UNSET:
            supplier.adresse = _clean_optional(adresse, "adresse")
        if ville is not _UNSET:
            supplier.ville = _clean_optional(ville, "ville")
        if pays is not _UNSET:
            supplier.pays = _clean_optional(pays, "pays")
        if observations is not _UNSET:
            supplier.observations = _clean_optional(observations, "observations")

    def list_suppliers(self, search: str = "", include_inactive: bool = True) -> list[SupplierSummary]:
        self._permissions.require_permission("SUPPLIER_VIEW")
        with session_scope(self._settings) as session:
            repo = SupplierRepository(session)
            suppliers = repo.search(search, include_inactive=include_inactive)
            return [SupplierSummary.from_model(s) for s in suppliers]

    def get_supplier(self, supplier_id: int) -> SupplierSummary:
        self._permissions.require_permission("SUPPLIER_VIEW")
        with session_scope(self._settings) as session:
            repo = SupplierRepository(session)
            supplier = repo.get_by_id(supplier_id)
            if supplier is None:
                raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")
            return SupplierSummary.from_model(supplier)

    def create_supplier(
        self,
        nom: str,
        *,
        contact: Optional[str] = None,
        telephone: Optional[str] = None,
        email: Optional[str] = None,
        adresse: Optional[str] = None,
        ville: Optional[str] = None,
        pays: Optional[str] = None,
        observations: Optional[str] = None,
    ) -> SupplierSummary:
        self._permissions.require_permission("SUPPLIER_CREATE")

        with session_scope(self._settings) as session:
            supplier = Supplier(statut=StatutActifInactif.ACTIF)
            self._apply_all_fields(
                supplier, nom, contact, telephone, email, adresse, ville, pays, observations
            )
            session.add(supplier)
            session.flush()

            self._audit(session, "SUPPLIER_CREATE", supplier.id)
            summary = SupplierSummary.from_model(supplier)

        logger.info("Fournisseur créé : %s", summary.nom)
        return summary

    def update_supplier(
        self,
        supplier_id: int,
        nom: str,
        *,
        contact=_UNSET,
        telephone=_UNSET,
        email=_UNSET,
        adresse=_UNSET,
        ville=_UNSET,
        pays=_UNSET,
        observations=_UNSET,
    ) -> SupplierSummary:
        """Modifie un fournisseur. ``nom`` est toujours requis ; les autres
        champs, s'ils ne sont pas fournis, conservent leur valeur actuelle
        (jamais effacés silencieusement) — passer explicitement ``None`` ou
        une chaîne vide pour effacer un champ."""
        self._permissions.require_permission("SUPPLIER_UPDATE")

        with session_scope(self._settings) as session:
            repo = SupplierRepository(session)
            supplier = repo.get_by_id(supplier_id)
            if supplier is None:
                raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")

            self._apply_provided_fields(
                supplier, nom, contact, telephone, email, adresse, ville, pays, observations
            )
            session.flush()

            self._audit(session, "SUPPLIER_UPDATE", supplier.id)
            summary = SupplierSummary.from_model(supplier)

        logger.info("Fournisseur modifié : id=%s -> %s", supplier_id, summary.nom)
        return summary

    def activate_supplier(self, supplier_id: int) -> SupplierSummary:
        self._permissions.require_permission("SUPPLIER_ACTIVATE")
        return self._set_status(supplier_id, StatutActifInactif.ACTIF, "SUPPLIER_ACTIVATE")

    def deactivate_supplier(self, supplier_id: int) -> SupplierSummary:
        """Désactivation (jamais de suppression physique)."""
        self._permissions.require_permission("SUPPLIER_DEACTIVATE")
        return self._set_status(supplier_id, StatutActifInactif.INACTIF, "SUPPLIER_DEACTIVATE")

    def _set_status(self, supplier_id: int, statut: StatutActifInactif, action: str) -> SupplierSummary:
        with session_scope(self._settings) as session:
            repo = SupplierRepository(session)
            supplier = repo.get_by_id(supplier_id)
            if supplier is None:
                raise NotFoundError(f"Fournisseur {supplier_id} introuvable.")

            supplier.statut = statut
            self._audit(session, action, supplier.id)
            session.flush()
            summary = SupplierSummary.from_model(supplier)

        logger.info("Fournisseur id=%s : %s", supplier_id, action)
        return summary
