"""Accès aux données pour les locations.

Seule cette classe construit des requêtes SQLAlchemy sur ``locations`` ;
:class:`LocationService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
Ventes/Entrées/Sorties.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.enums import StatutLocation
from app.models.rental import Location, LocationLigne
from app.repositories.base import SQLAlchemyRepository


class LocationRepository(SQLAlchemyRepository[Location]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Location)

    def find_by_numero(self, numero: str) -> Optional[Location]:
        return self.session.query(Location).filter(Location.numero == numero).one_or_none()

    def search(
        self,
        term: str = "",
        statut: Optional[StatutLocation] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        client_id: Optional[int] = None,
    ) -> list[Location]:
        # eager-load user/client/lignes(+article/retours) : la page Locations
        # parcourt potentiellement des centaines de documents, évite le N+1.
        query = self.session.query(Location).options(
            joinedload(Location.user),
            joinedload(Location.client),
            selectinload(Location.lignes).joinedload(LocationLigne.article),
            selectinload(Location.lignes).selectinload(LocationLigne.retours),
            selectinload(Location.paiements),
        )
        if term:
            query = query.filter(Location.numero.ilike(f"%{term}%"))
        if statut is not None:
            query = query.filter(Location.statut == statut)
        if date_from is not None:
            query = query.filter(Location.date >= date_from)
        if date_to is not None:
            query = query.filter(Location.date <= date_to)
        if client_id is not None:
            query = query.filter(Location.client_id == client_id)
        return query.order_by(Location.date.desc(), Location.id.desc()).all()

    def count_all(self) -> int:
        """Utilisé pour générer le prochain numéro de location (LOC-NNNNNN),
        à l'identique de ``VenteRepository.count_all``."""
        return self.session.query(func.count(Location.id)).scalar() or 0
