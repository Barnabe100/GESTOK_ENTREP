from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import utcnow
from app.models.types import MONEY


class Paiement(Base):
    """Journal immuable des paiements reçus sur une vente (gestion des
    ventes à crédit et des paiements partiels).

    Volontairement séparé de ``Vente`` (jamais un simple champ « montant
    payé » écrasé à chaque paiement) : chaque paiement est conservé comme
    une ligne d'historique distincte, à l'identique de ``MouvementStock``
    pour le stock. ``Vente.montant_paye``/``Vente.statut_paiement`` restent
    des totaux courants dénormalisés, recalculés dans la même transaction
    que l'insertion d'un ``Paiement`` (voir ``SaleService.record_payment``)
    — jamais la source de vérité, seulement un raccourci de lecture, comme
    ``Article.stock_actuel`` vis-à-vis de ``MouvementStock``.

    Aucune méthode de modification n'est prévue : un paiement enregistré
    n'est jamais corrigé ni supprimé, pour préserver la traçabilité
    financière (voir cahier des charges, §5.11).
    """

    __tablename__ = "paiements"
    __table_args__ = (
        CheckConstraint("montant > 0", name="ck_paiement_montant_positif"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vente_id: Mapped[int] = mapped_column(ForeignKey("ventes.id"), nullable=False, index=True)
    montant: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    date_heure: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    mode_paiement: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    vente: Mapped["Vente"] = relationship("Vente", back_populates="paiements")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Paiement(vente_id={self.vente_id!r}, montant={self.montant!r})"
