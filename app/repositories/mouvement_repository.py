"""Accès aux données pour les mouvements de stock (journal en lecture seule
depuis les modules appelants — seul :class:`StockService` y écrit).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.enums import TypeMouvement
from app.models.movement import MouvementStock
from app.repositories.base import SQLAlchemyRepository


class MouvementRepository(SQLAlchemyRepository[MouvementStock]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, MouvementStock)

    def search(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        article_id: Optional[int] = None,
        type_mouvement: Optional[TypeMouvement] = None,
        user_id: Optional[int] = None,
    ) -> list[MouvementStock]:
        """Utilisé par le rapport Mouvements. ``date_heure`` porte une heure
        (contrairement aux dates des documents) : ``date_to`` est traité
        comme une borne inclusive sur la journée entière (jusqu'à 23:59:59.999999),
        en comparant à ``< début du jour suivant`` pour éviter tout piège lié
        aux heures/minutes/secondes (§4 du cahier des charges de cette
        phase)."""
        query = self.session.query(MouvementStock).options(
            joinedload(MouvementStock.article), joinedload(MouvementStock.user)
        )
        if date_from is not None:
            query = query.filter(MouvementStock.date_heure >= datetime.combine(date_from, time.min))
        if date_to is not None:
            query = query.filter(MouvementStock.date_heure < datetime.combine(date_to + timedelta(days=1), time.min))
        if article_id is not None:
            query = query.filter(MouvementStock.article_id == article_id)
        if type_mouvement is not None:
            query = query.filter(MouvementStock.type == type_mouvement)
        if user_id is not None:
            query = query.filter(MouvementStock.user_id == user_id)
        return query.order_by(MouvementStock.date_heure.desc(), MouvementStock.id.desc()).all()

    def find_by_entree_ligne(
        self, entree_ligne_id: int, type_mouvement: Optional[TypeMouvement] = None
    ) -> list[MouvementStock]:
        """Retrouve les mouvements générés pour une ligne d'entrée donnée —
        utilisé notamment pour retrouver le mouvement ENTREE d'origine lors
        d'une annulation, afin de le lier via ``mouvement_origine_id``."""
        query = self.session.query(MouvementStock).filter(
            MouvementStock.entree_ligne_id == entree_ligne_id
        )
        if type_mouvement is not None:
            query = query.filter(MouvementStock.type == type_mouvement)
        return query.order_by(MouvementStock.id).all()

    def find_by_sortie_ligne(
        self, sortie_ligne_id: int, type_mouvement: Optional[TypeMouvement] = None
    ) -> list[MouvementStock]:
        """Retrouve les mouvements générés pour une ligne de sortie donnée —
        utilisé notamment pour retrouver le mouvement SORTIE d'origine lors
        d'une annulation, afin de le lier via ``mouvement_origine_id``."""
        query = self.session.query(MouvementStock).filter(
            MouvementStock.sortie_ligne_id == sortie_ligne_id
        )
        if type_mouvement is not None:
            query = query.filter(MouvementStock.type == type_mouvement)
        return query.order_by(MouvementStock.id).all()

    def find_by_vente_ligne(
        self, vente_ligne_id: int, type_mouvement: Optional[TypeMouvement] = None
    ) -> list[MouvementStock]:
        """Retrouve les mouvements générés pour une ligne de vente donnée —
        utilisé notamment pour retrouver le mouvement VENTE d'origine lors
        d'une annulation, afin de le lier via ``mouvement_origine_id``."""
        query = self.session.query(MouvementStock).filter(
            MouvementStock.vente_ligne_id == vente_ligne_id
        )
        if type_mouvement is not None:
            query = query.filter(MouvementStock.type == type_mouvement)
        return query.order_by(MouvementStock.id).all()

    def find_by_inventaire_ligne(self, inventaire_ligne_id: int) -> list[MouvementStock]:
        """Retrouve le mouvement AJUSTEMENT généré pour une ligne d'inventaire
        donnée (aucune annulation possible pour un inventaire — un seul
        mouvement au plus par ligne, ou aucun si l'écart était nul)."""
        return (
            self.session.query(MouvementStock)
            .filter(MouvementStock.inventaire_ligne_id == inventaire_ligne_id)
            .order_by(MouvementStock.id)
            .all()
        )

    def list_for_article(self, article_id: int) -> list[MouvementStock]:
        return (
            self.session.query(MouvementStock)
            .filter(MouvementStock.article_id == article_id)
            .order_by(MouvementStock.date_heure.desc(), MouvementStock.id.desc())
            .all()
        )

    def list_recent(self, limit: int) -> list[MouvementStock]:
        """Les ``limit`` mouvements les plus récents, tous articles confondus
        — utilisé par la section « Activité récente » du Dashboard (§6).
        ``LIMIT`` appliqué en SQL, jamais un chargement de l'historique
        complet suivi d'un découpage en Python (§8)."""
        return (
            self.session.query(MouvementStock)
            .options(joinedload(MouvementStock.article), joinedload(MouvementStock.user))
            .order_by(MouvementStock.date_heure.desc(), MouvementStock.id.desc())
            .limit(limit)
            .all()
        )
