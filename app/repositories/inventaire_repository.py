"""Accès aux données pour les inventaires.

Seule cette classe construit des requêtes SQLAlchemy sur ``inventaires`` ;
:class:`InventoryService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
Entrées/Sorties/Ventes.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import StatutInventaire
from app.models.inventory import Inventaire, InventaireLigne
from app.repositories.base import SQLAlchemyRepository


class InventaireRepository(SQLAlchemyRepository[Inventaire]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Inventaire)

    def find_by_numero(self, numero: str) -> Optional[Inventaire]:
        return self.session.query(Inventaire).filter(Inventaire.numero == numero).one_or_none()

    def search(
        self,
        term: str = "",
        statut: Optional[StatutInventaire] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> list[Inventaire]:
        # eager-load user/lignes(+article) : le rapport Inventaires parcourt
        # potentiellement des dizaines de documents, évite le N+1.
        query = self.session.query(Inventaire).options(
            joinedload(Inventaire.user), selectinload(Inventaire.lignes).joinedload(InventaireLigne.article)
        )
        if term:
            query = query.filter(Inventaire.numero.ilike(f"%{term}%"))
        if statut is not None:
            query = query.filter(Inventaire.statut == statut)
        if date_from is not None:
            query = query.filter(Inventaire.date >= date_from)
        if date_to is not None:
            query = query.filter(Inventaire.date <= date_to)
        return query.order_by(Inventaire.date.desc(), Inventaire.id.desc()).all()

    def count_all(self) -> int:
        """Utilisé pour générer le prochain numéro d'inventaire (INV-NNNNNN).

        Les inventaires validés ne sont jamais physiquement supprimés, ce
        compteur est donc strictement croissant."""
        return self.session.query(func.count(Inventaire.id)).scalar() or 0
