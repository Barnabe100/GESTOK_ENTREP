from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import StatutOperation
from app.models.mixins import TimestampMixin
from app.models.types import MONEY, QUANTITY

_STATUT_OPERATION_TYPE = SAEnum(
    StatutOperation, native_enum=False, length=20, name="statut_operation"
)


class Entree(TimestampMixin, Base):
    __tablename__ = "entrees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    fournisseur_id: Mapped[int] = mapped_column(ForeignKey("fournisseurs.id"), nullable=False)
    reference_document: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    statut: Mapped[StatutOperation] = mapped_column(
        _STATUT_OPERATION_TYPE, default=StatutOperation.BROUILLON, nullable=False
    )

    lignes: Mapped[list["EntreeLigne"]] = relationship(
        "EntreeLigne", back_populates="entree", cascade="all, delete-orphan"
    )
    fournisseur: Mapped["Supplier"] = relationship("Supplier")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Entree(numero={self.numero!r}, statut={self.statut!r})"


class EntreeLigne(Base):
    __tablename__ = "entree_lignes"
    __table_args__ = (
        CheckConstraint("quantite > 0", name="ck_entree_ligne_quantite_positive"),
        CheckConstraint("prix_unitaire >= 0", name="ck_entree_ligne_prix_positif"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entree_id: Mapped[int] = mapped_column(ForeignKey("entrees.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    quantite: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    prix_unitaire: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    montant: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    entree: Mapped["Entree"] = relationship("Entree", back_populates="lignes")
    article: Mapped["Article"] = relationship("Article")


class Sortie(TimestampMixin, Base):
    __tablename__ = "sorties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    motif_id: Mapped[int] = mapped_column(ForeignKey("motifs_sortie.id"), nullable=False)
    beneficiaire: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    statut: Mapped[StatutOperation] = mapped_column(
        _STATUT_OPERATION_TYPE, default=StatutOperation.BROUILLON, nullable=False
    )

    lignes: Mapped[list["SortieLigne"]] = relationship(
        "SortieLigne", back_populates="sortie", cascade="all, delete-orphan"
    )
    motif: Mapped["ExitReason"] = relationship("ExitReason")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Sortie(numero={self.numero!r}, statut={self.statut!r})"


class SortieLigne(Base):
    __tablename__ = "sortie_lignes"
    __table_args__ = (
        CheckConstraint("quantite > 0", name="ck_sortie_ligne_quantite_positive"),
        CheckConstraint("cout_unitaire >= 0", name="ck_sortie_ligne_cout_positif"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sortie_id: Mapped[int] = mapped_column(ForeignKey("sorties.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    quantite: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    cout_unitaire: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    montant: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    sortie: Mapped["Sortie"] = relationship("Sortie", back_populates="lignes")
    article: Mapped["Article"] = relationship("Article")


class Vente(TimestampMixin, Base):
    __tablename__ = "ventes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    statut: Mapped[StatutOperation] = mapped_column(
        _STATUT_OPERATION_TYPE, default=StatutOperation.BROUILLON, nullable=False
    )
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), nullable=False)

    lignes: Mapped[list["VenteLigne"]] = relationship(
        "VenteLigne", back_populates="vente", cascade="all, delete-orphan"
    )
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Vente(numero={self.numero!r}, statut={self.statut!r})"


class VenteLigne(Base):
    __tablename__ = "vente_lignes"
    __table_args__ = (
        CheckConstraint("quantite > 0", name="ck_vente_ligne_quantite_positive"),
        CheckConstraint("prix_unitaire >= 0", name="ck_vente_ligne_prix_positif"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vente_id: Mapped[int] = mapped_column(ForeignKey("ventes.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    quantite: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    prix_unitaire: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    sous_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    vente: Mapped["Vente"] = relationship("Vente", back_populates="lignes")
    article: Mapped["Article"] = relationship("Article")
