"""Gestion des unités proposées pour les articles (§7, évolution F) :
consultation et création. Aucune suppression ni modification — une unité
une fois créée reste disponible (pas de notion de désactivation demandée
pour ce lot, à la différence des motifs de sortie).

Lecture ouverte à quiconque peut consulter les articles (``ARTICLE_VIEW``) ;
création ouverte à quiconque peut créer OU modifier un article
(``ARTICLE_CREATE``/``ARTICLE_UPDATE``) — le bouton « Nouveau » proposé par
ce lot apparaît dans les deux modes du formulaire article, jamais seulement
l'un des deux.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import UniteArticle
from app.repositories.unite_article_repository import UniteArticleRepository
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import ConflictError, PermissionDeniedError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.unites_article")

MAX_LIBELLE_LENGTH = 20


@dataclass(frozen=True)
class UniteArticleSummary:
    id: int
    libelle: str
    date_creation: datetime

    @classmethod
    def from_model(cls, unite: UniteArticle) -> "UniteArticleSummary":
        return cls(id=unite.id, libelle=unite.libelle, date_creation=unite.date_creation)


def _validate_libelle(libelle: str) -> str:
    libelle = (libelle or "").strip()
    if not libelle:
        raise ValidationError("Le libellé de l'unité est obligatoire.")
    if len(libelle) > MAX_LIBELLE_LENGTH:
        raise ValidationError(f"Le libellé de l'unité ne doit pas dépasser {MAX_LIBELLE_LENGTH} caractères.")
    return libelle


def _duplicate_libelle_error(libelle: str) -> ConflictError:
    return ConflictError(f"Une unité équivalente à « {libelle} » existe déjà (espaces et casse ignorés).")


class UniteArticleService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def list_unites(self) -> list[UniteArticleSummary]:
        self._permissions.require_permission("ARTICLE_VIEW")
        with session_scope(self._settings) as session:
            repo = UniteArticleRepository(session)
            return [UniteArticleSummary.from_model(u) for u in repo.list_all_ordered()]

    def create_unite(self, libelle: str) -> UniteArticleSummary:
        if not (
            self._permissions.has_permission("ARTICLE_CREATE")
            or self._permissions.has_permission("ARTICLE_UPDATE")
        ):
            raise PermissionDeniedError("Permission requise : ARTICLE_CREATE ou ARTICLE_UPDATE")
        libelle = _validate_libelle(libelle)

        with session_scope(self._settings) as session:
            repo = UniteArticleRepository(session)
            if repo.find_by_normalized_label(libelle) is not None:
                raise _duplicate_libelle_error(libelle)

            unite = UniteArticle(libelle=libelle)
            session.add(unite)
            try:
                session.flush()
            except IntegrityError as exc:
                raise _duplicate_libelle_error(libelle) from exc

            summary = UniteArticleSummary.from_model(unite)

        logger.info("Unité d'article créée : %s", libelle)
        return summary
