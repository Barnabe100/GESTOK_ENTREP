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
from app.models.rental import Location, LocationLigne, LocationRetour
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
        # Chantier B : tri par date d'enregistrement réelle (date_creation),
        # jamais la date métier (Location.date, modifiable/antidatée) —
        # voir le commentaire équivalent dans vente_repository.py.
        return query.order_by(Location.date_creation.desc(), Location.id.desc()).all()

    def count_all(self) -> int:
        """Utilisé pour générer le prochain numéro de location (LOC-NNNNNN),
        à l'identique de ``VenteRepository.count_all``."""
        return self.session.query(func.count(Location.id)).scalar() or 0

    def count_by_statut(self, statut: StatutLocation) -> int:
        """Comptage instantané (ex. « Locations en cours », Dashboard §6) —
        agrégation SQL plutôt que charger les locations complètes juste pour
        un total (même principe que les compteurs de ``ArticleRepository``)."""
        return self.session.query(func.count(Location.id)).filter(Location.statut == statut).scalar() or 0

    def count_returns_in_period(self, date_from: date, date_to: date) -> int:
        """Nombre d'événements de retour (``LocationRetour``, pas de
        locations) dont la date de retour tombe dans la période (Dashboard
        §6) — distinct du filtre par ``Location.date`` utilisé pour le
        montant facturé/l'évolution : un retour peut survenir bien après la
        date de création de la location qui le porte."""
        return (
            self.session.query(func.count(LocationRetour.id))
            .filter(LocationRetour.date_retour >= date_from, LocationRetour.date_retour <= date_to)
            .scalar()
            or 0
        )
