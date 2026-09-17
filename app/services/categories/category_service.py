"""Gestion des catégories : consultation, recherche, création, modification,
activation/désactivation.

Aucune suppression physique (voir cahier des charges §5 et §7) : une
catégorie utilisée dans l'historique ne doit jamais disparaître, seulement
être désactivée. Une catégorie inactive reste consultable mais ne doit plus
être proposée pour de nouvelles opérations (voir ``list_categories(...,
include_inactive=False)``, destiné au futur module Articles).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.catalog import Category
from app.models.enums import ResultatAudit, StatutActifInactif
from app.repositories.category_repository import CategoryRepository
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.logging_config import get_logger

MAX_NAME_LENGTH = 100

logger = get_logger("services.categories")


@dataclass(frozen=True)
class CategorySummary:
    """Vue en lecture seule d'une catégorie."""

    id: int
    nom: str
    actif: bool
    date_creation: datetime
    date_modification: datetime

    @classmethod
    def from_model(cls, category: Category) -> "CategorySummary":
        return cls(
            id=category.id,
            nom=category.nom,
            actif=category.statut == StatutActifInactif.ACTIF,
            date_creation=category.date_creation,
            date_modification=category.date_modification,
        )


def _validate_category_name(nom: str) -> str:
    nom = (nom or "").strip()
    if not nom:
        raise ValidationError("Le nom de la catégorie est obligatoire.")
    if len(nom) > MAX_NAME_LENGTH:
        raise ValidationError(
            f"Le nom de la catégorie ne doit pas dépasser {MAX_NAME_LENGTH} caractères."
        )
    return nom


def _duplicate_name_error(nom: str) -> ConflictError:
    return ConflictError(f"Une catégorie nommée « {nom} » existe déjà.")


class CategoryService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, category_id: Optional[int]) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="categories",
                entite_id=category_id,
                resultat=ResultatAudit.SUCCES,
            )
        )

    def list_categories(self, search: str = "", include_inactive: bool = True) -> list[CategorySummary]:
        self._permissions.require_permission("CATEGORY_VIEW")
        with session_scope(self._settings) as session:
            repo = CategoryRepository(session)
            categories = repo.search(search, include_inactive=include_inactive)
            return [CategorySummary.from_model(c) for c in categories]

    def get_category(self, category_id: int) -> CategorySummary:
        self._permissions.require_permission("CATEGORY_VIEW")
        with session_scope(self._settings) as session:
            repo = CategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError(f"Catégorie {category_id} introuvable.")
            return CategorySummary.from_model(category)

    def create_category(self, nom: str) -> CategorySummary:
        self._permissions.require_permission("CATEGORY_CREATE")
        nom = _validate_category_name(nom)

        with session_scope(self._settings) as session:
            repo = CategoryRepository(session)
            if repo.find_by_name(nom) is not None:
                raise _duplicate_name_error(nom)

            category = Category(nom=nom, statut=StatutActifInactif.ACTIF)
            session.add(category)
            try:
                session.flush()
            except IntegrityError as exc:
                raise _duplicate_name_error(nom) from exc

            self._audit(session, "CATEGORY_CREATE", category.id)
            summary = CategorySummary.from_model(category)

        logger.info("Catégorie créée : %s", nom)
        return summary

    def update_category(self, category_id: int, nom: str) -> CategorySummary:
        self._permissions.require_permission("CATEGORY_UPDATE")
        nom = _validate_category_name(nom)

        with session_scope(self._settings) as session:
            repo = CategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError(f"Catégorie {category_id} introuvable.")

            if repo.find_by_name(nom, exclude_id=category_id) is not None:
                raise _duplicate_name_error(nom)

            category.nom = nom
            try:
                session.flush()
            except IntegrityError as exc:
                raise _duplicate_name_error(nom) from exc

            self._audit(session, "CATEGORY_UPDATE", category.id)
            summary = CategorySummary.from_model(category)

        logger.info("Catégorie modifiée : id=%s -> %s", category_id, nom)
        return summary

    def activate_category(self, category_id: int) -> CategorySummary:
        self._permissions.require_permission("CATEGORY_ACTIVATE")
        return self._set_status(category_id, StatutActifInactif.ACTIF, "CATEGORY_ACTIVATE")

    def deactivate_category(self, category_id: int) -> CategorySummary:
        """Désactivation (jamais de suppression physique, voir §7 du cahier des charges)."""
        self._permissions.require_permission("CATEGORY_DEACTIVATE")
        return self._set_status(category_id, StatutActifInactif.INACTIF, "CATEGORY_DEACTIVATE")

    def _set_status(self, category_id: int, statut: StatutActifInactif, action: str) -> CategorySummary:
        with session_scope(self._settings) as session:
            repo = CategoryRepository(session)
            category = repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError(f"Catégorie {category_id} introuvable.")

            category.statut = statut
            self._audit(session, action, category.id)
            session.flush()
            summary = CategorySummary.from_model(category)

        logger.info("Catégorie id=%s : %s", category_id, action)
        return summary
