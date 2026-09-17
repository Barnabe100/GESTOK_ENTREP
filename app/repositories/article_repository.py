"""Accès aux données pour les articles.

Seule cette classe construit des requêtes SQLAlchemy sur ``articles`` ;
:class:`ArticleService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
Catégories, Fournisseurs et Motifs de sortie.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import Article, Category
from app.models.enums import StatutActifInactif
from app.repositories.base import SQLAlchemyRepository


class ArticleRepository(SQLAlchemyRepository[Article]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Article)

    def find_by_reference(self, reference: str, exclude_id: Optional[int] = None) -> Optional[Article]:
        query = self.session.query(Article).filter(Article.reference == reference)
        if exclude_id is not None:
            query = query.filter(Article.id != exclude_id)
        return query.one_or_none()

    def find_by_barcode(self, code_barres: str, exclude_id: Optional[int] = None) -> Optional[Article]:
        query = self.session.query(Article).filter(Article.code_barres == code_barres)
        if exclude_id is not None:
            query = query.filter(Article.id != exclude_id)
        return query.one_or_none()

    def search(
        self,
        term: str = "",
        category_id: Optional[int] = None,
        include_inactive: bool = True,
        low_stock_only: bool = False,
        out_of_stock_only: bool = False,
    ) -> list[Article]:
        # eager-load category/fournisseur_principal : évite le N+1 lorsque
        # l'appelant (ex. les rapports État du stock/Valorisation) parcourt
        # potentiellement des centaines d'articles pour construire ses lignes.
        query = (
            self.session.query(Article)
            .join(Article.category)
            .options(joinedload(Article.category), joinedload(Article.fournisseur_principal))
        )
        if term:
            like_term = f"%{term}%"
            query = query.filter(
                or_(
                    Article.reference.ilike(like_term),
                    Article.designation.ilike(like_term),
                    Category.nom.ilike(like_term),
                )
            )
        if category_id is not None:
            query = query.filter(Article.category_id == category_id)
        if not include_inactive:
            query = query.filter(Article.statut == StatutActifInactif.ACTIF)
        if low_stock_only:
            query = query.filter(Article.stock_actuel <= Article.stock_min)
        if out_of_stock_only:
            query = query.filter(Article.stock_actuel == Decimal("0"))
        return query.order_by(Article.reference).all()
