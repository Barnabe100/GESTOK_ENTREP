"""Accès aux données pour les motifs de sortie.

Seule cette classe construit des requêtes SQLAlchemy sur ``motifs_sortie`` ;
:class:`ExitReasonService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
Catégories et Fournisseurs.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.catalog import ExitReason
from app.models.enums import StatutActifInactif
from app.repositories.base import SQLAlchemyRepository


def normalize_label(libelle: str) -> str:
    """Normalise un libellé pour la comparaison d'unicité : espaces superflus
    et casse ignorés (« Perte », « perte », «  PERTE  » sont équivalents)."""
    return " ".join((libelle or "").split()).lower()


class ExitReasonRepository(SQLAlchemyRepository[ExitReason]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ExitReason)

    def find_by_normalized_label(
        self, libelle: str, exclude_id: Optional[int] = None
    ) -> Optional[ExitReason]:
        """Recherche insensible à la casse et aux espaces superflus.

        Table de référence, de taille réduite : un parcours en mémoire est
        largement suffisant et évite de dépendre d'une fonction SQL
        spécifique au moteur pour normaliser la comparaison.
        """
        target = normalize_label(libelle)
        for reason in self.session.query(ExitReason).all():
            if exclude_id is not None and reason.id == exclude_id:
                continue
            if normalize_label(reason.libelle) == target:
                return reason
        return None

    def search(self, term: str = "", include_inactive: bool = True) -> list[ExitReason]:
        query = self.session.query(ExitReason)
        if term:
            query = query.filter(ExitReason.libelle.ilike(f"%{term}%"))
        if not include_inactive:
            query = query.filter(ExitReason.statut == StatutActifInactif.ACTIF)
        return query.order_by(ExitReason.libelle).all()
