"""Vue de présentation d'un mouvement de stock, partagée par tous les modules
qui en génèrent (Entrées, Sorties, ...) — évite de dupliquer la projection
``MouvementStock`` -> DTO dans chaque service métier."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.models.enums import TypeMouvement
from app.models.movement import MouvementStock


@dataclass(frozen=True)
class MouvementSummary:
    """Vue en lecture seule d'un mouvement de stock, pour la traçabilité
    d'une opération (qui, quand, quel article, quelle quantité, stock
    avant/après)."""

    id: int
    article_id: int
    article_reference: str
    type: TypeMouvement
    quantite: Decimal
    stock_avant: Decimal
    stock_apres: Decimal
    cout_unitaire: Optional[Decimal]
    date_heure: datetime
    user_id: int
    username: str
    commentaire: Optional[str]

    @classmethod
    def from_model(cls, mouvement: MouvementStock) -> "MouvementSummary":
        return cls(
            id=mouvement.id,
            article_id=mouvement.article_id,
            article_reference=mouvement.article.reference,
            type=mouvement.type,
            quantite=mouvement.quantite,
            stock_avant=mouvement.stock_avant,
            stock_apres=mouvement.stock_apres,
            cout_unitaire=mouvement.cout_unitaire,
            date_heure=mouvement.date_heure,
            user_id=mouvement.user_id,
            username=mouvement.user.username,
            commentaire=mouvement.commentaire,
        )
