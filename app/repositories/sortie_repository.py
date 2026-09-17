"""Accès aux données pour les sorties de stock.

Seule cette classe construit des requêtes SQLAlchemy sur ``sorties`` ;
:class:`ExitService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique du module Entrées.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.catalog import ExitReason
from app.models.documents import Sortie
from app.models.enums import StatutOperation
from app.repositories.base import SQLAlchemyRepository


class SortieRepository(SQLAlchemyRepository[Sortie]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Sortie)

    def find_by_numero(self, numero: str) -> Optional[Sortie]:
        return self.session.query(Sortie).filter(Sortie.numero == numero).one_or_none()

    def search(
        self,
        term: str = "",
        motif_id: Optional[int] = None,
        statut: Optional[StatutOperation] = None,
    ) -> list[Sortie]:
        query = self.session.query(Sortie).join(Sortie.motif)
        if term:
            like_term = f"%{term}%"
            query = query.filter(
                or_(
                    Sortie.numero.ilike(like_term),
                    Sortie.reference.ilike(like_term),
                    Sortie.beneficiaire.ilike(like_term),
                    ExitReason.libelle.ilike(like_term),
                )
            )
        if motif_id is not None:
            query = query.filter(Sortie.motif_id == motif_id)
        if statut is not None:
            query = query.filter(Sortie.statut == statut)
        return query.order_by(Sortie.date.desc(), Sortie.id.desc()).all()

    def count_all(self) -> int:
        """Utilisé pour générer le prochain numéro de sortie (SOR-NNNNNN).

        Les sorties ne sont jamais physiquement supprimées (seulement
        annulées), ce compteur est donc strictement croissant.
        """
        return self.session.query(func.count(Sortie.id)).scalar() or 0
