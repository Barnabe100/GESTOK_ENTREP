"""Accès aux données pour les fournisseurs.

Seule cette classe construit des requêtes SQLAlchemy sur ``fournisseurs`` ;
:class:`SupplierService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique du module Catégories.
"""
from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.catalog import Supplier
from app.models.enums import StatutActifInactif
from app.repositories.base import SQLAlchemyRepository


class SupplierRepository(SQLAlchemyRepository[Supplier]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Supplier)

    def search(self, term: str = "", include_inactive: bool = True) -> list[Supplier]:
        query = self.session.query(Supplier)
        if term:
            like_term = f"%{term}%"
            query = query.filter(
                or_(
                    Supplier.nom.ilike(like_term),
                    Supplier.contact.ilike(like_term),
                    Supplier.ville.ilike(like_term),
                    Supplier.email.ilike(like_term),
                )
            )
        if not include_inactive:
            query = query.filter(Supplier.statut == StatutActifInactif.ACTIF)
        return query.order_by(Supplier.nom).all()

    def count_active(self) -> int:
        """Compteur ciblé pour le Dashboard (§8) — évite de charger tous les
        fournisseurs juste pour en compter le nombre."""
        return (
            self.session.query(func.count(Supplier.id))
            .filter(Supplier.statut == StatutActifInactif.ACTIF)
            .scalar() or 0
        )
