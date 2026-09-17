"""Accès aux données pour les entrées de stock.

Seule cette classe construit des requêtes SQLAlchemy sur ``entrees`` ;
:class:`EntryService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
précédents.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.catalog import Supplier
from app.models.documents import Entree
from app.models.enums import StatutOperation
from app.repositories.base import SQLAlchemyRepository


class EntreeRepository(SQLAlchemyRepository[Entree]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Entree)

    def find_by_numero(self, numero: str) -> Optional[Entree]:
        return self.session.query(Entree).filter(Entree.numero == numero).one_or_none()

    def search(
        self,
        term: str = "",
        fournisseur_id: Optional[int] = None,
        statut: Optional[StatutOperation] = None,
    ) -> list[Entree]:
        query = self.session.query(Entree).join(Entree.fournisseur)
        if term:
            like_term = f"%{term}%"
            query = query.filter(
                or_(
                    Entree.numero.ilike(like_term),
                    Entree.reference_document.ilike(like_term),
                    Supplier.nom.ilike(like_term),
                )
            )
        if fournisseur_id is not None:
            query = query.filter(Entree.fournisseur_id == fournisseur_id)
        if statut is not None:
            query = query.filter(Entree.statut == statut)
        return query.order_by(Entree.date.desc(), Entree.id.desc()).all()

    def count_all(self) -> int:
        """Utilisé pour générer le prochain numéro d'entrée (ENT-NNNNNN).

        Les entrées ne sont jamais physiquement supprimées (seulement
        annulées), ce compteur est donc strictement croissant.
        """
        return self.session.query(func.count(Entree.id)).scalar() or 0
