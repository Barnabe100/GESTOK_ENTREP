"""Accès aux données pour les ventes.

Seule cette classe construit des requêtes SQLAlchemy sur ``ventes`` ;
:class:`SaleService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
Entrées et Sorties.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.documents import Vente, VenteLigne
from app.models.enums import StatutOperation
from app.repositories.base import SQLAlchemyRepository


class VenteRepository(SQLAlchemyRepository[Vente]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Vente)

    def find_by_numero(self, numero: str) -> Optional[Vente]:
        return self.session.query(Vente).filter(Vente.numero == numero).one_or_none()

    def search(
        self,
        term: str = "",
        statut: Optional[StatutOperation] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> list[Vente]:
        # eager-load user/lignes(+article) : le rapport Ventes parcourt
        # potentiellement des centaines de documents, évite le N+1.
        query = self.session.query(Vente).options(
            joinedload(Vente.user), selectinload(Vente.lignes).joinedload(VenteLigne.article)
        )
        if term:
            query = query.filter(Vente.numero.ilike(f"%{term}%"))
        if statut is not None:
            query = query.filter(Vente.statut == statut)
        if date_from is not None:
            query = query.filter(Vente.date >= date_from)
        if date_to is not None:
            query = query.filter(Vente.date <= date_to)
        return query.order_by(Vente.date.desc(), Vente.id.desc()).all()

    def count_all(self) -> int:
        """Utilisé pour générer le prochain numéro de vente (VNT-NNNNNN).

        Les ventes validées ne sont jamais physiquement supprimées (seulement
        annulées) ; seul un brouillon jamais validé peut disparaître (voir
        ``SaleService.delete_sale``), ce qui n'affecte pas l'unicité du
        prochain numéro généré (toujours strictement croissant par rapport
        aux ventes existantes au moment de l'appel)."""
        return self.session.query(func.count(Vente.id)).scalar() or 0
