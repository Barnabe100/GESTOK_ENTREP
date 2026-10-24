"""Accès aux données pour les unités d'articles (§7, évolution F).

Seule cette classe construit des requêtes SQLAlchemy sur ``unites_article`` ;
:class:`UniteArticleService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des motifs de sortie.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.catalog import UniteArticle
from app.repositories.base import SQLAlchemyRepository
from app.repositories.exit_reason_repository import normalize_label


class UniteArticleRepository(SQLAlchemyRepository[UniteArticle]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, UniteArticle)

    def find_by_normalized_label(self, libelle: str) -> Optional[UniteArticle]:
        """Recherche insensible à la casse et aux espaces superflus — voir
        ``app.repositories.exit_reason_repository.normalize_label``.

        Table de référence, de taille réduite : un parcours en mémoire est
        largement suffisant."""
        target = normalize_label(libelle)
        for unite in self.session.query(UniteArticle).all():
            if normalize_label(unite.libelle) == target:
                return unite
        return None

    def list_all_ordered(self) -> list[UniteArticle]:
        return self.session.query(UniteArticle).order_by(UniteArticle.libelle).all()
