from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import StatutActifInactif
from app.models.mixins import TimestampMixin
from app.models.types import MONEY, QUANTITY


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    statut: Mapped[StatutActifInactif] = mapped_column(
        SAEnum(StatutActifInactif, native_enum=False, length=20, name="statut_actif_inactif"),
        default=StatutActifInactif.ACTIF,
        nullable=False,
    )

    articles: Mapped[list["Article"]] = relationship("Article", back_populates="category")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Category(id={self.id!r}, nom={self.nom!r})"


class Supplier(TimestampMixin, Base):
    __tablename__ = "fournisseurs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(150), nullable=False)
    contact: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    telephone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    adresse: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ville: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pays: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    observations: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    statut: Mapped[StatutActifInactif] = mapped_column(
        SAEnum(StatutActifInactif, native_enum=False, length=20, name="statut_actif_inactif"),
        default=StatutActifInactif.ACTIF,
        nullable=False,
    )

    articles: Mapped[list["Article"]] = relationship(
        "Article", back_populates="fournisseur_principal"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Supplier(id={self.id!r}, nom={self.nom!r})"


class ExitReason(TimestampMixin, Base):
    """Motifs de sortie administrables (décision métier : table dédiée, cf §6).

    Gestion réservée à l'Administrateur. Un motif actif sera proposé lors de
    la création d'une sortie (module Sorties, phase ultérieure) ; un motif
    désactivé reste visible dans l'historique mais n'est plus proposé pour une
    nouvelle sortie — jamais de suppression physique.
    """

    __tablename__ = "motifs_sortie"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    libelle: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    statut: Mapped[StatutActifInactif] = mapped_column(
        SAEnum(StatutActifInactif, native_enum=False, length=20, name="statut_actif_inactif"),
        default=StatutActifInactif.ACTIF,
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"ExitReason(libelle={self.libelle!r})"


class Article(TimestampMixin, Base):
    __tablename__ = "articles"
    __table_args__ = (
        CheckConstraint("prix_achat_defaut >= 0", name="ck_article_prix_achat_positif"),
        CheckConstraint("prix_vente >= 0", name="ck_article_prix_vente_positif"),
        CheckConstraint("cout_moyen_pondere >= 0", name="ck_article_cmup_positif"),
        CheckConstraint("stock_actuel >= 0", name="ck_article_stock_actuel_positif"),
        CheckConstraint("stock_min >= 0", name="ck_article_stock_min_positif"),
        CheckConstraint("stock_max IS NULL OR stock_max >= 0", name="ck_article_stock_max_positif"),
        CheckConstraint(
            "stock_max IS NULL OR stock_max >= stock_min", name="ck_article_stock_max_gte_min"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    unite: Mapped[str] = mapped_column(String(20), nullable=False)
    fournisseur_principal_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fournisseurs.id"), nullable=True
    )
    prix_achat_defaut: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), nullable=False)
    prix_vente: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), nullable=False)
    cout_moyen_pondere: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), nullable=False)
    stock_actuel: Mapped[Decimal] = mapped_column(QUANTITY, default=Decimal("0"), nullable=False)
    stock_min: Mapped[Decimal] = mapped_column(QUANTITY, default=Decimal("0"), nullable=False)
    stock_max: Mapped[Optional[Decimal]] = mapped_column(QUANTITY, nullable=True)
    emplacement: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    code_barres: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    statut: Mapped[StatutActifInactif] = mapped_column(
        SAEnum(StatutActifInactif, native_enum=False, length=20, name="statut_actif_inactif"),
        default=StatutActifInactif.ACTIF,
        nullable=False,
    )

    category: Mapped["Category"] = relationship("Category", back_populates="articles")
    fournisseur_principal: Mapped[Optional["Supplier"]] = relationship(
        "Supplier", back_populates="articles"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Article(id={self.id!r}, reference={self.reference!r})"
