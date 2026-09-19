from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import TypeMouvement
from app.models.mixins import utcnow
from app.models.types import MONEY, QUANTITY


class MouvementStock(Base):
    """Journal central et immuable de toute variation de stock.

    Référence l'opération d'origine via l'une des quatre FK nullables
    (une seule est renseignée selon le type de mouvement) plutôt qu'une
    référence polymorphe, afin de préserver l'intégrité référentielle.
    """

    __tablename__ = "mouvements_stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date_heure: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False, index=True)
    type: Mapped[TypeMouvement] = mapped_column(
        SAEnum(TypeMouvement, native_enum=False, length=20, name="type_mouvement"), nullable=False
    )
    # Signée : positive pour une augmentation de stock, négative pour une diminution,
    # de sorte que stock_apres = stock_avant + quantite quel que soit le type.
    quantite: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    stock_avant: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    stock_apres: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    cout_unitaire: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)

    entree_ligne_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("entree_lignes.id"), nullable=True
    )
    sortie_ligne_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sortie_lignes.id"), nullable=True
    )
    vente_ligne_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("vente_lignes.id"), nullable=True
    )
    inventaire_ligne_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventaire_lignes.id"), nullable=True
    )
    mouvement_origine_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("mouvements_stock.id"), nullable=True
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    article: Mapped["Article"] = relationship("Article")
    user: Mapped["User"] = relationship("User")
    mouvement_origine: Mapped[Optional["MouvementStock"]] = relationship(
        "MouvementStock", remote_side="MouvementStock.id"
    )
    # Relations de lecture vers la ligne d'origine (une seule renseignée selon
    # le type de mouvement) : permettent de remonter jusqu'au numéro du
    # document parent (Entree/Sortie/Vente/Inventaire) pour la « référence de
    # l'opération » affichée par la page Mouvements, sans dupliquer cette
    # donnée sur MouvementStock lui-même.
    entree_ligne: Mapped[Optional["EntreeLigne"]] = relationship("EntreeLigne")
    sortie_ligne: Mapped[Optional["SortieLigne"]] = relationship("SortieLigne")
    vente_ligne: Mapped[Optional["VenteLigne"]] = relationship("VenteLigne")
    inventaire_ligne: Mapped[Optional["InventaireLigne"]] = relationship("InventaireLigne")

    def __repr__(self) -> str:  # pragma: no cover
        return f"MouvementStock(type={self.type!r}, article_id={self.article_id!r}, quantite={self.quantite!r})"
