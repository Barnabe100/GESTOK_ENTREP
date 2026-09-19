"""Accès aux données pour les clients.

Seule cette classe construit des requêtes SQLAlchemy sur ``clients`` ;
:class:`ClientService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique du module
Fournisseurs.
"""
from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.enums import StatutActifInactif
from app.repositories.base import SQLAlchemyRepository


class ClientRepository(SQLAlchemyRepository[Client]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Client)

    def search(self, term: str = "", include_inactive: bool = True) -> list[Client]:
        query = self.session.query(Client)
        if term:
            like_term = f"%{term}%"
            query = query.filter(
                or_(
                    Client.nom.ilike(like_term),
                    Client.telephone.ilike(like_term),
                    Client.email.ilike(like_term),
                )
            )
        if not include_inactive:
            query = query.filter(Client.statut == StatutActifInactif.ACTIF)
        return query.order_by(Client.nom).all()

    def count_active(self) -> int:
        return (
            self.session.query(func.count(Client.id))
            .filter(Client.statut == StatutActifInactif.ACTIF)
            .scalar() or 0
        )
