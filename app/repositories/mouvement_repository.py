"""Accès aux données pour les mouvements de stock (journal en lecture seule
depuis les modules appelants — seul :class:`StockService` y écrit).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.enums import TypeMouvement
from app.models.movement import MouvementStock
from app.repositories.base import SQLAlchemyRepository


class MouvementRepository(SQLAlchemyRepository[MouvementStock]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, MouvementStock)

    def find_by_entree_ligne(
        self, entree_ligne_id: int, type_mouvement: Optional[TypeMouvement] = None
    ) -> list[MouvementStock]:
        """Retrouve les mouvements générés pour une ligne d'entrée donnée —
        utilisé notamment pour retrouver le mouvement ENTREE d'origine lors
        d'une annulation, afin de le lier via ``mouvement_origine_id``."""
        query = self.session.query(MouvementStock).filter(
            MouvementStock.entree_ligne_id == entree_ligne_id
        )
        if type_mouvement is not None:
            query = query.filter(MouvementStock.type == type_mouvement)
        return query.order_by(MouvementStock.id).all()

    def find_by_sortie_ligne(
        self, sortie_ligne_id: int, type_mouvement: Optional[TypeMouvement] = None
    ) -> list[MouvementStock]:
        """Retrouve les mouvements générés pour une ligne de sortie donnée —
        utilisé notamment pour retrouver le mouvement SORTIE d'origine lors
        d'une annulation, afin de le lier via ``mouvement_origine_id``."""
        query = self.session.query(MouvementStock).filter(
            MouvementStock.sortie_ligne_id == sortie_ligne_id
        )
        if type_mouvement is not None:
            query = query.filter(MouvementStock.type == type_mouvement)
        return query.order_by(MouvementStock.id).all()

    def list_for_article(self, article_id: int) -> list[MouvementStock]:
        return (
            self.session.query(MouvementStock)
            .filter(MouvementStock.article_id == article_id)
            .order_by(MouvementStock.date_heure.desc(), MouvementStock.id.desc())
            .all()
        )
