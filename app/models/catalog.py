from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ModeGestionArticle, StatutActifInactif
from app.models.mixins import TimestampMixin, utcnow
from app.models.types import MONEY, QUANTITY

_MODE_GESTION_ARTICLE_TYPE = SAEnum(
    ModeGestionArticle, native_enum=False, length=20, name="mode_gestion_article"
)


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


class UniteArticle(TimestampMixin, Base):
    """Unités proposées dans le menu déroulant « Unité » des articles (§7,
    évolution F) : table de référence dédiée, même principe qu'``ExitReason``,
    pour que ce menu reste extensible (bouton « Nouveau ») sans jamais
    redevenir un champ de saisie libre.

    ``Article.unite`` (inchangé, simple texte) ne référence jamais cette
    table par clé étrangère : un article existant dont l'unité ne figure pas
    ici (saisie libre antérieure à ce lot) continue de s'afficher et de se
    modifier normalement, sans aucune altération silencieuse — seule la
    proposition d'une *nouvelle* unité à la création/modification d'un
    article passe désormais par cette liste fermée.
    """

    __tablename__ = "unites_article"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    libelle: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"UniteArticle(libelle={self.libelle!r})"


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
        # Mission 5 (§2/§3) : les 3 tarifs de vente et de location — défense
        # en profondeur, la validation croisée réelle (avec message métier
        # compréhensible) vit dans ``ArticleService``, jamais seulement ici.
        CheckConstraint(
            "prix_sous_traitant IS NULL OR prix_sous_traitant >= 0",
            name="ck_article_prix_sous_traitant_positif",
        ),
        CheckConstraint(
            "prix_autre_min IS NULL OR prix_autre_min >= 0", name="ck_article_prix_autre_min_positif"
        ),
        CheckConstraint(
            "prix_autre_max IS NULL OR prix_autre_max >= 0", name="ck_article_prix_autre_max_positif"
        ),
        CheckConstraint(
            "prix_autre_min IS NULL OR prix_autre_max IS NULL OR prix_autre_min <= prix_autre_max",
            name="ck_article_prix_autre_min_le_max",
        ),
        CheckConstraint(
            "prix_autre_min IS NULL OR prix_sous_traitant IS NULL OR prix_autre_min <= prix_sous_traitant",
            name="ck_article_prix_autre_min_le_sous_traitant",
        ),
        CheckConstraint(
            "prix_autre_max IS NULL OR prix_autre_max >= prix_vente",
            name="ck_article_prix_autre_max_ge_normal",
        ),
        CheckConstraint(
            "tarif_location_sous_traitant IS NULL OR tarif_location_sous_traitant >= 0",
            name="ck_article_tarif_location_sous_traitant_positif",
        ),
        CheckConstraint(
            "tarif_location_autre_min IS NULL OR tarif_location_autre_min >= 0",
            name="ck_article_tarif_location_autre_min_positif",
        ),
        CheckConstraint(
            "tarif_location_autre_max IS NULL OR tarif_location_autre_max >= 0",
            name="ck_article_tarif_location_autre_max_positif",
        ),
        CheckConstraint(
            "tarif_location_autre_min IS NULL OR tarif_location_autre_max IS NULL "
            "OR tarif_location_autre_min <= tarif_location_autre_max",
            name="ck_article_tarif_location_autre_min_le_max",
        ),
        CheckConstraint(
            "tarif_location_autre_min IS NULL OR tarif_location_sous_traitant IS NULL "
            "OR tarif_location_autre_min <= tarif_location_sous_traitant",
            name="ck_article_tarif_location_autre_min_le_sous_traitant",
        ),
        CheckConstraint(
            "tarif_location_autre_max IS NULL OR tarif_location_autre_max >= tarif_location_jour",
            name="ck_article_tarif_location_autre_max_ge_normal",
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
    # Module Locations (lot dédié) : VENTE par défaut (comportement inchangé
    # pour tout article existant) — bascule explicite et mutuellement
    # exclusive vers LOCATION via ArticleService, jamais modifiée ailleurs ;
    # chaque changement est historisé dans ArticleModeGestionChangement.
    mode_gestion: Mapped[ModeGestionArticle] = mapped_column(
        _MODE_GESTION_ARTICLE_TYPE, default=ModeGestionArticle.VENTE, nullable=False
    )
    # Tarif catalogue journalier de location — None tant que l'article n'a
    # jamais été configuré pour la location. Pré-remplit (mais ne contraint
    # jamais) LocationLigne.tarif_jour, à l'identique de prix_vente vis-à-vis
    # de VenteLigne.prix_unitaire (une vraie saisie historisée par ligne,
    # jamais recalculée rétroactivement si ce tarif catalogue change).
    tarif_location_jour: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)

    # Mission 5 (§2/§3) : trois tarifs de vente et trois tarifs de location,
    # entièrement indépendants (jamais l'un dérivé de l'autre). None tant
    # qu'un tarif n'a jamais été configuré — un article existant avant cette
    # mission a donc les six champs à None, sans valeur arbitraire imposée
    # (§6). ``prix_autre_min``/``prix_autre_max`` ne sont définis qu'en même
    # temps (voir validation croisée dans ArticleService) : ensemble, ils
    # forment l'intervalle autorisé pour le prix personnalisé (« Autre
    # prix ») saisi lors d'une vente/location, jamais un prix fixe.
    prix_sous_traitant: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    prix_autre_min: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    prix_autre_max: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    tarif_location_sous_traitant: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    tarif_location_autre_min: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)
    tarif_location_autre_max: Mapped[Optional[Decimal]] = mapped_column(MONEY, nullable=True)

    category: Mapped["Category"] = relationship("Category", back_populates="articles")
    fournisseur_principal: Mapped[Optional["Supplier"]] = relationship(
        "Supplier", back_populates="articles"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Article(id={self.id!r}, reference={self.reference!r})"


class ArticleModeGestionChangement(Base):
    """Historique immuable des changements de ``Article.mode_gestion``
    (VENTE <-> LOCATION) — jamais modifié ni supprimé après création, à
    l'identique de MouvementStock/Paiement pour leurs propres journaux."""

    __tablename__ = "article_mode_gestion_changements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False, index=True)
    ancien_mode: Mapped[ModeGestionArticle] = mapped_column(_MODE_GESTION_ARTICLE_TYPE, nullable=False)
    nouveau_mode: Mapped[ModeGestionArticle] = mapped_column(_MODE_GESTION_ARTICLE_TYPE, nullable=False)
    date_heure: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    article: Mapped["Article"] = relationship("Article")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"ArticleModeGestionChangement(article_id={self.article_id!r}, "
            f"{self.ancien_mode!r} -> {self.nouveau_mode!r})"
        )
