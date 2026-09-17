from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import StatutInventaire
from app.models.mixins import TimestampMixin
from app.models.types import QUANTITY


class Inventaire(TimestampMixin, Base):
    __tablename__ = "inventaires"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    statut: Mapped[StatutInventaire] = mapped_column(
        SAEnum(StatutInventaire, native_enum=False, length=20, name="statut_inventaire"),
        default=StatutInventaire.BROUILLON,
        nullable=False,
    )

    lignes: Mapped[list["InventaireLigne"]] = relationship(
        "InventaireLigne", back_populates="inventaire", cascade="all, delete-orphan"
    )
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Inventaire(numero={self.numero!r}, statut={self.statut!r})"


class InventaireLigne(Base):
    __tablename__ = "inventaire_lignes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventaire_id: Mapped[int] = mapped_column(ForeignKey("inventaires.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    stock_theorique: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    stock_physique: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    ecart: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)

    inventaire: Mapped["Inventaire"] = relationship("Inventaire", back_populates="lignes")
    article: Mapped["Article"] = relationship("Article")
