"""Gestion des motifs de sortie : consultation, recherche, création,
modification, activation/désactivation.

Réservée à l'Administrateur (décision métier explicite de cette phase :
toutes les permissions ``STOCK_REASON_*`` ne sont attribuées qu'à ce rôle
dans la matrice RBAC actuelle — voir ``app/db/seed.py``).

Mêmes principes que Catégories/Fournisseurs : aucune suppression physique,
un motif désactivé reste consultable (préserve l'historique) mais ne doit
plus être proposé pour une nouvelle opération — voir
``list_exit_reasons(..., include_inactive=False)``, destiné au futur module
Sorties. Ce module n'implémente pas encore la sélection d'un motif dans un
formulaire de sortie (hors périmètre de cette phase) ; la façon dont un
Vendeur/Gestionnaire y accédera sera définie lors de la phase Sorties.

Particularité par rapport aux catégories : l'unicité du libellé ignore les
espaces superflus et la casse (« Perte », « perte », «  PERTE  » sont
considérés comme un seul et même motif).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.catalog import ExitReason
from app.models.enums import ResultatAudit, StatutActifInactif
from app.repositories.exit_reason_repository import ExitReasonRepository
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.exit_reasons")

MAX_LABEL_LENGTH = 150
MAX_DESCRIPTION_LENGTH = 500


@dataclass(frozen=True)
class ExitReasonSummary:
    """Vue en lecture seule d'un motif de sortie."""

    id: int
    libelle: str
    description: Optional[str]
    actif: bool
    date_creation: datetime
    date_modification: datetime

    @classmethod
    def from_model(cls, reason: ExitReason) -> "ExitReasonSummary":
        return cls(
            id=reason.id,
            libelle=reason.libelle,
            description=reason.description,
            actif=reason.statut == StatutActifInactif.ACTIF,
            date_creation=reason.date_creation,
            date_modification=reason.date_modification,
        )


def _validate_label(libelle: str) -> str:
    libelle = (libelle or "").strip()
    if not libelle:
        raise ValidationError("Le libellé du motif est obligatoire.")
    if len(libelle) > MAX_LABEL_LENGTH:
        raise ValidationError(
            f"Le libellé du motif ne doit pas dépasser {MAX_LABEL_LENGTH} caractères."
        )
    return libelle


def _validate_description(description: Optional[str]) -> Optional[str]:
    if description is None:
        return None
    description = description.strip()
    if not description:
        return None
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(
            f"La description ne doit pas dépasser {MAX_DESCRIPTION_LENGTH} caractères."
        )
    return description


def _duplicate_label_error(libelle: str) -> ConflictError:
    return ConflictError(
        f"Un motif équivalent à « {libelle} » existe déjà (espaces et casse ignorés)."
    )


class ExitReasonService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, reason_id: Optional[int]) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="motifs_sortie",
                entite_id=reason_id,
                resultat=ResultatAudit.SUCCES,
            )
        )

    def list_exit_reasons(self, search: str = "", include_inactive: bool = True) -> list[ExitReasonSummary]:
        self._permissions.require_permission("STOCK_REASON_VIEW")
        with session_scope(self._settings) as session:
            repo = ExitReasonRepository(session)
            reasons = repo.search(search, include_inactive=include_inactive)
            return [ExitReasonSummary.from_model(r) for r in reasons]

    def get_exit_reason(self, reason_id: int) -> ExitReasonSummary:
        self._permissions.require_permission("STOCK_REASON_VIEW")
        with session_scope(self._settings) as session:
            repo = ExitReasonRepository(session)
            reason = repo.get_by_id(reason_id)
            if reason is None:
                raise NotFoundError(f"Motif de sortie {reason_id} introuvable.")
            return ExitReasonSummary.from_model(reason)

    def create_exit_reason(self, libelle: str, description: Optional[str] = None) -> ExitReasonSummary:
        self._permissions.require_permission("STOCK_REASON_CREATE")
        libelle = _validate_label(libelle)
        description = _validate_description(description)

        with session_scope(self._settings) as session:
            repo = ExitReasonRepository(session)
            if repo.find_by_normalized_label(libelle) is not None:
                raise _duplicate_label_error(libelle)

            reason = ExitReason(libelle=libelle, description=description, statut=StatutActifInactif.ACTIF)
            session.add(reason)
            try:
                session.flush()
            except IntegrityError as exc:
                raise _duplicate_label_error(libelle) from exc

            self._audit(session, "STOCK_REASON_CREATE", reason.id)
            summary = ExitReasonSummary.from_model(reason)

        logger.info("Motif de sortie créé : %s", libelle)
        return summary

    def update_exit_reason(
        self, reason_id: int, libelle: str, description: Optional[str] = None
    ) -> ExitReasonSummary:
        self._permissions.require_permission("STOCK_REASON_UPDATE")
        libelle = _validate_label(libelle)
        description = _validate_description(description)

        with session_scope(self._settings) as session:
            repo = ExitReasonRepository(session)
            reason = repo.get_by_id(reason_id)
            if reason is None:
                raise NotFoundError(f"Motif de sortie {reason_id} introuvable.")

            if repo.find_by_normalized_label(libelle, exclude_id=reason_id) is not None:
                raise _duplicate_label_error(libelle)

            reason.libelle = libelle
            reason.description = description
            try:
                session.flush()
            except IntegrityError as exc:
                raise _duplicate_label_error(libelle) from exc

            self._audit(session, "STOCK_REASON_UPDATE", reason.id)
            summary = ExitReasonSummary.from_model(reason)

        logger.info("Motif de sortie modifié : id=%s -> %s", reason_id, libelle)
        return summary

    def activate_exit_reason(self, reason_id: int) -> ExitReasonSummary:
        self._permissions.require_permission("STOCK_REASON_ACTIVATE")
        return self._set_status(reason_id, StatutActifInactif.ACTIF, "STOCK_REASON_ACTIVATE")

    def deactivate_exit_reason(self, reason_id: int) -> ExitReasonSummary:
        """Désactivation (jamais de suppression physique)."""
        self._permissions.require_permission("STOCK_REASON_DEACTIVATE")
        return self._set_status(reason_id, StatutActifInactif.INACTIF, "STOCK_REASON_DEACTIVATE")

    def _set_status(self, reason_id: int, statut: StatutActifInactif, action: str) -> ExitReasonSummary:
        with session_scope(self._settings) as session:
            repo = ExitReasonRepository(session)
            reason = repo.get_by_id(reason_id)
            if reason is None:
                raise NotFoundError(f"Motif de sortie {reason_id} introuvable.")

            reason.statut = statut
            self._audit(session, action, reason.id)
            session.flush()
            summary = ExitReasonSummary.from_model(reason)

        logger.info("Motif de sortie id=%s : %s", reason_id, action)
        return summary
