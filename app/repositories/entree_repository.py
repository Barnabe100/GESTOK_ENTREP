"""Accès aux données pour les entrées de stock.

Seule cette classe construit des requêtes SQLAlchemy sur ``entrees`` ;
:class:`EntryService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
précédents.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.catalog import Supplier
from app.models.documents import Entree, EntreeLigne
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
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> list[Entree]:
        # eager-load fournisseur/user/lignes(+article) : le rapport Entrées
        # parcourt potentiellement des centaines de documents, évite le N+1.
        query = (
            self.session.query(Entree)
            .join(Entree.fournisseur)
            .options(
                joinedload(Entree.fournisseur),
                joinedload(Entree.user),
                selectinload(Entree.lignes).joinedload(EntreeLigne.article),
            )
        )
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
        if date_from is not None:
            query = query.filter(Entree.date >= date_from)
        if date_to is not None:
            query = query.filter(Entree.date <= date_to)
        return query.order_by(Entree.date.desc(), Entree.id.desc()).all()

    def count_all(self) -> int:
        """Utilisé pour générer le prochain numéro d'entrée (ENT-NNNNNN).

        Les entrées ne sont jamais physiquement supprimées (seulement
        annulées), ce compteur est donc strictement croissant.
        """
        return self.session.query(func.count(Entree.id)).scalar() or 0
