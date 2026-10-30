"""Gestion des unités proposées pour les articles (§7, évolution F ; Mission
4 §4, suppression des unités créées par erreur).

Lecture ouverte à quiconque peut consulter les articles (``ARTICLE_VIEW``) ;
création et suppression ouvertes à quiconque peut créer OU modifier un
article (``ARTICLE_CREATE``/``ARTICLE_UPDATE``) — mêmes permissions pour les
deux (Mission 4, §6 : aucune permission dédiée à la gestion des unités
n'existe, celle déjà utilisée pour leur création est donc réutilisée telle
quelle, jamais un contournement RBAC).

Mission 4, §4.3 : jamais de désactivation/archivage pour ce lot — une unité
non utilisée se supprime réellement (``delete_unite``), une unité utilisée
par au moins un article ne peut jamais l'être (voir
``UniteArticleRepository.count_articles_using_label`` : ``Article.unite``
n'est pas une clé étrangère, la protection est donc appliquée ici, au
niveau service, et non par une contrainte SQL)."""
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
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
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


def _require_unite_management_permission(permissions: PermissionService) -> None:
    if not (permissions.has_permission("ARTICLE_CREATE") or permissions.has_permission("ARTICLE_UPDATE")):
        raise PermissionDeniedError("Permission requise : ARTICLE_CREATE ou ARTICLE_UPDATE")


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
        _require_unite_management_permission(self._permissions)
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

    def is_unite_used(self, unite_id: int) -> bool:
        """Mission 4, §4.2/§4.3 : permet à l'appelant (formulaire Article)
        de distinguer, avant de demander confirmation, une unité qui peut
        être supprimée d'une unité protégée — ``delete_unite`` revérifie de
        toute façon cette même condition, jamais contournable depuis l'UI."""
        self._permissions.require_permission("ARTICLE_VIEW")
        with session_scope(self._settings) as session:
            repo = UniteArticleRepository(session)
            unite = repo.get_by_id(unite_id)
            if unite is None:
                raise NotFoundError(f"Unité introuvable (id={unite_id}).")
            return repo.count_articles_using_label(unite.libelle) > 0

    def delete_unite(self, unite_id: int) -> None:
        """Mission 4, §4 : suppression réelle d'une unité créée par erreur —
        jamais possible si au moins un article l'utilise encore (voir
        ``UniteArticleRepository.count_articles_using_label`` : vérification
        toujours revérifiée ici, jamais déléguée à la seule UI), et jamais
        de contournement SQL direct — passe entièrement par le repository,
        comme toute autre suppression de cette application."""
        _require_unite_management_permission(self._permissions)
        with session_scope(self._settings) as session:
            repo = UniteArticleRepository(session)
            unite = repo.get_by_id(unite_id)
            if unite is None:
                raise NotFoundError(f"Unité introuvable (id={unite_id}).")
            libelle = unite.libelle
            if repo.count_articles_using_label(libelle) > 0:
                raise ConflictError(
                    "Cette unité ne peut pas être supprimée car elle est utilisée par des articles."
                )
            repo.delete(unite)

        logger.info("Unité d'article supprimée : %s", libelle)
