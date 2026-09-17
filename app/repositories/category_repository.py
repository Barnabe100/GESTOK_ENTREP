"""Accès aux données pour les catégories.

Seule cette classe construit des requêtes SQLAlchemy sur ``categories`` ;
:class:`CategoryService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.catalog import Category
from app.models.enums import StatutActifInactif
from app.repositories.base import SQLAlchemyRepository


class CategoryRepository(SQLAlchemyRepository[Category]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Category)

    def find_by_name(self, nom: str, exclude_id: Optional[int] = None) -> Optional[Category]:
        """Recherche exacte (respecte la contrainte d'unicité définie sur la colonne)."""
        query = self.session.query(Category).filter(Category.nom == nom)
        if exclude_id is not None:
            query = query.filter(Category.id != exclude_id)
        return query.one_or_none()

    def search(self, term: str = "", include_inactive: bool = True) -> list[Category]:
        query = self.session.query(Category)
        if term:
            query = query.filter(Category.nom.ilike(f"%{term}%"))
        if not include_inactive:
            query = query.filter(Category.statut == StatutActifInactif.ACTIF)
        return query.order_by(Category.nom).all()

    def count_active(self) -> int:
        """Compteur ciblé pour le Dashboard (§8) — évite de charger toutes
        les catégories juste pour en compter le nombre."""
        return (
            self.session.query(func.count(Category.id))
            .filter(Category.statut == StatutActifInactif.ACTIF)
            .scalar() or 0
        )
