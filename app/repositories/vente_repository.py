"""Accès aux données pour les ventes.

Seule cette classe construit des requêtes SQLAlchemy sur ``ventes`` ;
:class:`SaleService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
Entrées et Sorties.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.documents import Vente
from app.models.enums import StatutOperation
from app.repositories.base import SQLAlchemyRepository


class VenteRepository(SQLAlchemyRepository[Vente]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Vente)

    def find_by_numero(self, numero: str) -> Optional[Vente]:
        return self.session.query(Vente).filter(Vente.numero == numero).one_or_none()

    def search(self, term: str = "", statut: Optional[StatutOperation] = None) -> list[Vente]:
        query = self.session.query(Vente)
        if term:
            query = query.filter(Vente.numero.ilike(f"%{term}%"))
        if statut is not None:
            query = query.filter(Vente.statut == statut)
        return query.order_by(Vente.date.desc(), Vente.id.desc()).all()

    def count_all(self) -> int:
        """Utilisé pour générer le prochain numéro de vente (VNT-NNNNNN).

        Les ventes validées ne sont jamais physiquement supprimées (seulement
        annulées) ; seul un brouillon jamais validé peut disparaître (voir
        ``SaleService.delete_sale``), ce qui n'affecte pas l'unicité du
        prochain numéro généré (toujours strictement croissant par rapport
        aux ventes existantes au moment de l'appel)."""
        return self.session.query(func.count(Vente.id)).scalar() or 0
