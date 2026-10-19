"""Module Locations : location d'articles à des clients, avec confirmation,
départ, retour (total ou partiel) et facturation par événement de retour.

Cycle de vie (``StatutLocation``) : BROUILLON -> CONFIRMEE -> EN_COURS ->
RETOURNEE, ou BROUILLON/CONFIRMEE -> ANNULEE — jamais d'annulation après le
départ (décision métier explicite de ce lot : une fois le stock
physiquement sorti, seule une suite de retours peut clore la location).

Trois quantités distinctes par ligne (``LocationLigne``), jamais une
quatrième logique de décompte parallèle à ``StockService`` :
- ``qte_prevue`` : quantité demandée à la création, jamais modifiée après
  (référence/historique).
- ``qte_reservee`` : quantité réservée tant que la location n'est pas
  partie (BROUILLON/CONFIRMEE) — purement informative, n'affecte jamais
  ``Article.stock_actuel`` (qui ne représente que le stock physiquement
  disponible), à l'identique d'une Vente en brouillon qui ne réserve rien
  non plus. Ramenée à 0 au départ.
- ``qte_en_location`` : quantité physiquement sortie et pas encore
  retournée. Décrémentée à chaque retour, qu'il soit en bon état ou
  immobilisé — dans les deux cas, l'article n'est plus « en location ».
- ``qte_immobilisee`` : quantité jamais remise en stock (retour en mauvais
  état). Ne redevient jamais disponible dans ce lot — aucun écran de remise
  en état/mise au rebut (limitation connue et acceptée, voir le compte
  rendu de ce lot).

Facturation (``LocationRetour``) : à chaque événement de retour, le montant
dû est calculé une seule fois et historisé sur ``montant_facture`` (jamais
recalculé ensuite, à l'identique de ``VenteLigne.prix_unitaire``) =
``LocationLigne.tarif_jour`` × nombre de jours entre le départ de la
location et la date de ce retour (minimum 1 jour) × quantité traitée par
cet événement (bon état + immobilisée confondues : les jours de location
sont dus quel que soit l'état de retour). Les paiements effectifs sont un
journal immuable séparé (``LocationPaiement``), à l'identique de
``Paiement`` pour les ventes — jamais un simple champ écrasé.

Caution : montant fixe saisi à la création de la location
(``Location.caution_montant``), restituée/retenue manuellement par
l'utilisateur (``Location.caution_rendue``, jamais calculée
automatiquement) — décision métier explicite de ce lot.

Client facultatif (lot « Client facultatif et création rapide depuis une
location ») : ``Location.client_id`` peut être NULL, à l'identique de
``Vente.client_id`` — aucun impact sur le cycle de vie, les calculs de
frais, la caution ou les paiements, qui n'utilisent jamais le client.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import StatutLocation
from app.models.mixins import TimestampMixin, utcnow
from app.models.types import MONEY, QUANTITY

_STATUT_LOCATION_TYPE = SAEnum(StatutLocation, native_enum=False, length=20, name="statut_location")


class Location(TimestampMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (
        CheckConstraint("caution_montant >= 0", name="ck_location_caution_montant_positif"),
        CheckConstraint("caution_rendue >= 0", name="ck_location_caution_rendue_positif"),
        CheckConstraint("caution_rendue <= caution_montant", name="ck_location_caution_rendue_max"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    # Facultatif (lot « Client facultatif et création rapide depuis une
    # location ») : NULL = aucun client identifié, à l'identique de
    # Vente.client_id (vente comptant) depuis la migration 0006. Avant ce
    # lot, un client était systématiquement exigé (voir migration 0014) ;
    # la migration 0015 assouplit cette contrainte sans toucher aux lignes
    # déjà enregistrées, qui ont toutes un client renseigné.
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    statut: Mapped[StatutLocation] = mapped_column(
        _STATUT_LOCATION_TYPE, default=StatutLocation.BROUILLON, nullable=False
    )
    # NULL tant que le départ n'a pas eu lieu ; renseigné une seule fois par
    # LocationService.depart_location et jamais modifié ensuite — sert de
    # point de départ au calcul de la durée facturée (voir LocationRetour).
    date_depart: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    caution_montant: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), nullable=False)
    # Cumul des restitutions/retenues déjà enregistrées (jamais négatif,
    # jamais supérieur à caution_montant — voir CheckConstraint ci-dessus) ;
    # chaque mouvement individuel n'est pas historisé séparément dans ce lot
    # (décision explicite : simple enregistrement manuel, pas de calcul).
    caution_rendue: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Nullable : NULL tant que la location n'est pas annulée. Renseigné une
    # seule fois par LocationService.cancel_location et jamais modifié
    # ensuite — même convention qu'Entree/Sortie/Vente.annulation_motif.
    annulation_motif: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    lignes: Mapped[list["LocationLigne"]] = relationship(
        "LocationLigne", back_populates="location", cascade="all, delete-orphan"
    )
    paiements: Mapped[list["LocationPaiement"]] = relationship(
        "LocationPaiement",
        back_populates="location",
        cascade="all, delete-orphan",
        order_by="LocationPaiement.id",
    )
    client: Mapped[Optional["Client"]] = relationship("Client")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"Location(numero={self.numero!r}, statut={self.statut!r})"


class LocationLigne(Base):
    __tablename__ = "location_lignes"
    __table_args__ = (
        CheckConstraint("qte_prevue > 0", name="ck_location_ligne_qte_prevue_positive"),
        CheckConstraint("qte_reservee >= 0", name="ck_location_ligne_qte_reservee_positive"),
        CheckConstraint("qte_en_location >= 0", name="ck_location_ligne_qte_en_location_positive"),
        CheckConstraint("qte_immobilisee >= 0", name="ck_location_ligne_qte_immobilisee_positive"),
        CheckConstraint("tarif_jour >= 0", name="ck_location_ligne_tarif_jour_positif"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    qte_prevue: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    qte_reservee: Mapped[Decimal] = mapped_column(QUANTITY, default=Decimal("0"), nullable=False)
    qte_en_location: Mapped[Decimal] = mapped_column(QUANTITY, default=Decimal("0"), nullable=False)
    qte_immobilisee: Mapped[Decimal] = mapped_column(QUANTITY, default=Decimal("0"), nullable=False)
    # Vraie saisie historisée (comme VenteLigne.prix_unitaire), pré-remplie
    # depuis Article.tarif_location_jour mais librement modifiable — jamais
    # recalculée si le tarif catalogue change ensuite.
    tarif_jour: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    location: Mapped["Location"] = relationship("Location", back_populates="lignes")
    article: Mapped["Article"] = relationship("Article")
    retours: Mapped[list["LocationRetour"]] = relationship(
        "LocationRetour",
        back_populates="location_ligne",
        cascade="all, delete-orphan",
        order_by="LocationRetour.id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"LocationLigne(id={self.id!r}, article_id={self.article_id!r})"


class LocationRetour(Base):
    """Un événement de retour (total ou partiel) sur une ligne de location —
    jamais modifié ni supprimé après création (journal immuable, comme
    MouvementStock/Paiement)."""

    __tablename__ = "location_retours"
    __table_args__ = (
        CheckConstraint("quantite_bon_etat >= 0", name="ck_location_retour_bon_etat_positif"),
        CheckConstraint("quantite_immobilisee >= 0", name="ck_location_retour_immobilisee_positif"),
        CheckConstraint(
            "quantite_bon_etat + quantite_immobilisee > 0", name="ck_location_retour_quantite_non_nulle"
        ),
        CheckConstraint("montant_facture >= 0", name="ck_location_retour_montant_positif"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_ligne_id: Mapped[int] = mapped_column(ForeignKey("location_lignes.id"), nullable=False)
    date_retour: Mapped[date] = mapped_column(Date, nullable=False)
    quantite_bon_etat: Mapped[Decimal] = mapped_column(QUANTITY, default=Decimal("0"), nullable=False)
    quantite_immobilisee: Mapped[Decimal] = mapped_column(QUANTITY, default=Decimal("0"), nullable=False)
    montant_facture: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date_heure: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    location_ligne: Mapped["LocationLigne"] = relationship("LocationLigne", back_populates="retours")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"LocationRetour(location_ligne_id={self.location_ligne_id!r}, montant_facture={self.montant_facture!r})"


class LocationPaiement(Base):
    """Journal immuable des paiements reçus sur une location — à l'identique
    de ``Paiement`` pour les ventes (jamais un simple champ écrasé), mais
    volontairement une table distincte : ne touche jamais au journal des
    paiements des ventes."""

    __tablename__ = "location_paiements"
    __table_args__ = (CheckConstraint("montant > 0", name="ck_location_paiement_montant_positif"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    montant: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    date_heure: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    mode_paiement: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    location: Mapped["Location"] = relationship("Location", back_populates="paiements")
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"LocationPaiement(location_id={self.location_id!r}, montant={self.montant!r})"
