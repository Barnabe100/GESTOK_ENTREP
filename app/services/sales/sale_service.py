"""Gestion des ventes : consultation, recherche, création, modification,
suppression de brouillon, validation, annulation.

Réutilise strictement :class:`StockService` (aucune deuxième logique de
décrémentation du stock ici ni dans la vue) : toute variation de stock
provoquée par une vente passe par ``StockService.apply_movement``, appelé
dans la même transaction (``session_scope``) que la mise à jour du statut de
la vente — soit tout réussit, soit tout est annulé par un rollback.

Une vente est une opération métier distincte d'une sortie générique : elle
possède son propre document (``Vente``/``VenteLigne``), ne crée jamais de
ligne dans ``sorties``, et son prix unitaire est celui réellement appliqué
au client — une vraie saisie (comme le prix d'achat d'une Entrée), à ne
jamais recalculer rétroactivement à partir du prix catalogue actuel de
l'article (§4 du cahier des charges de cette phase). Le CMUP, lui, n'est
jamais recalculé par une vente (règle StockService n°4, commune à
Sorties/Ventes) — mais le mouvement porte tout de même un ``cout_unitaire``
(le CMUP courant de l'article, coût de valorisation de la sortie de stock),
distinct du prix de vente facturé conservé sur la ligne : c'est la même
convention que pour les Sorties, qui garde le sens de ``cout_unitaire``
cohérent sur tous les mouvements sortants.

Cycle de vie : BROUILLON -> VALIDEE -> (ANNULEE).
- Une vente en BROUILLON ne modifie jamais le stock, reste modifiable, et
  peut être physiquement supprimée (aucun mouvement, aucun historique à
  préserver) — seul document de cette application à autoriser une
  suppression physique, et seulement dans cet état précis.
- La validation (BROUILLON -> VALIDEE) est l'unique moment où le stock est
  modifié : un mouvement VENTE est généré par ligne (quantité négative),
  puis la vente devient non modifiable et non supprimable.
- L'annulation (VALIDEE -> ANNULEE) génère un mouvement ANNULATION par ligne
  (quantité inverse, positive : restaure le stock) ; la vente originale est
  conservée (jamais supprimée), et une vente déjà ANNULEE ne peut pas être
  annulée une seconde fois.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.documents import Vente, VenteLigne
from app.models.enums import ResultatAudit, StatutActifInactif, StatutOperation, TypeMouvement
from app.models.movement import MouvementStock
from app.repositories.article_repository import ArticleRepository
from app.repositories.mouvement_repository import MouvementRepository
from app.repositories.vente_repository import VenteRepository
from app.services.auth.permission_service import PermissionService
from app.services.stock.movement_summary import MouvementSummary
from app.services.stock.stock_service import StockService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.logging_config import get_logger
from app.utils.money import round_money

logger = get_logger("services.sales")


@dataclass(frozen=True)
class VenteLigneInput:
    """Ligne saisie en entrée d'un ``create_sale``/``update_sale``.

    ``prix_unitaire`` est une vraie saisie utilisateur (comme le prix
    d'achat d'une Entrée), pré-remplie dans l'interface avec le prix de
    vente actuel de l'article mais librement modifiable — jamais recalculée
    automatiquement, contrairement au coût d'une Sortie qui est toujours le
    CMUP courant."""

    article_id: int
    quantite: Decimal
    prix_unitaire: Decimal


@dataclass(frozen=True)
class VenteLigneSummary:
    """Vue en lecture seule d'une ligne de vente."""

    id: int
    article_id: int
    article_reference: str
    article_designation: str
    quantite: Decimal
    prix_unitaire: Decimal
    sous_total: Decimal

    @classmethod
    def from_model(cls, ligne: VenteLigne) -> "VenteLigneSummary":
        return cls(
            id=ligne.id,
            article_id=ligne.article_id,
            article_reference=ligne.article.reference,
            article_designation=ligne.article.designation,
            quantite=ligne.quantite,
            prix_unitaire=ligne.prix_unitaire,
            sous_total=ligne.sous_total,
        )


@dataclass(frozen=True)
class VenteSummary:
    """Vue en lecture seule d'une vente, avec ses lignes."""

    id: int
    numero: str
    date: date
    user_id: int
    username: str
    statut: StatutOperation
    total: Decimal
    lignes: list[VenteLigneSummary]
    date_creation: datetime
    date_modification: datetime

    @classmethod
    def from_model(cls, vente: Vente) -> "VenteSummary":
        return cls(
            id=vente.id,
            numero=vente.numero,
            date=vente.date,
            user_id=vente.user_id,
            username=vente.user.username,
            statut=vente.statut,
            total=vente.total,
            lignes=[VenteLigneSummary.from_model(l) for l in vente.lignes],
            date_creation=vente.date_creation,
            date_modification=vente.date_modification,
        )


def _validate_positive_quantity(value: Decimal, field_label: str) -> Decimal:
    if value <= 0:
        raise ValidationError(f"Le champ « {field_label} » doit être strictement positif.")
    return value


def _validate_money(value: Decimal, field_label: str) -> Decimal:
    if value < 0:
        raise ValidationError(f"Le champ « {field_label} » ne peut pas être négatif.")
    return value


class SaleService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings
        self._stock = StockService()

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, sale_id: Optional[int]) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="ventes",
                entite_id=sale_id,
                resultat=ResultatAudit.SUCCES,
            )
        )

    def _build_lignes(self, session, lines: Sequence[VenteLigneInput]) -> list[VenteLigne]:
        article_repo = ArticleRepository(session)
        lignes: list[VenteLigne] = []
        for line in lines:
            quantite = _validate_positive_quantity(line.quantite, "quantité")
            prix_unitaire = _validate_money(line.prix_unitaire, "prix de vente unitaire")

            article = article_repo.get_by_id(line.article_id)
            if article is None:
                raise NotFoundError(f"Article {line.article_id} introuvable.")
            if article.statut != StatutActifInactif.ACTIF:
                raise ValidationError(f"L'article « {article.reference} » est inactif.")

            lignes.append(
                VenteLigne(
                    article_id=article.id,
                    quantite=quantite,
                    prix_unitaire=prix_unitaire,
                    sous_total=round_money(quantite * prix_unitaire),
                )
            )
        return lignes

    @staticmethod
    def _compute_total(lignes: Sequence[VenteLigne]) -> Decimal:
        total = Decimal("0")
        for ligne in lignes:
            total += ligne.sous_total
        return round_money(total)

    # -- consultation -----------------------------------------------------------

    def list_sales(self, search: str = "", statut: Optional[StatutOperation] = None) -> list[VenteSummary]:
        self._permissions.require_permission("SALE_VIEW")
        with session_scope(self._settings) as session:
            repo = VenteRepository(session)
            ventes = repo.search(search, statut=statut)
            return [VenteSummary.from_model(v) for v in ventes]

    def get_sale(self, sale_id: int) -> VenteSummary:
        self._permissions.require_permission("SALE_VIEW")
        with session_scope(self._settings) as session:
            repo = VenteRepository(session)
            vente = repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            return VenteSummary.from_model(vente)

    def get_sale_movements(self, sale_id: int) -> list[MouvementSummary]:
        """Mouvements générés par une vente (VENTE à la validation,
        ANNULATION si la vente a été annulée) — traçabilité complète."""
        self._permissions.require_permission("STOCK_MOVEMENT_VIEW")
        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            mouvement_repo = MouvementRepository(session)

            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")

            movements: list[MouvementStock] = []
            for ligne in vente.lignes:
                movements.extend(mouvement_repo.find_by_vente_ligne(ligne.id))
            movements.sort(key=lambda m: m.id)
            return [MouvementSummary.from_model(m) for m in movements]

    # -- création / modification / suppression -----------------------------------

    def create_sale(
        self,
        date_vente: date,
        lines: Sequence[VenteLigneInput] = (),
    ) -> VenteSummary:
        """Crée une vente en BROUILLON : n'a aucun impact sur le stock."""
        self._permissions.require_permission("SALE_CREATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)

            numero = f"VNT-{vente_repo.count_all() + 1:06d}"

            vente = Vente(
                numero=numero,
                date=date_vente,
                user_id=acting_user_id,
                statut=StatutOperation.BROUILLON,
                total=Decimal("0"),
            )
            vente.lignes = self._build_lignes(session, lines)
            vente.total = self._compute_total(vente.lignes)
            session.add(vente)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError(f"Le numéro « {numero} » est déjà utilisé.") from exc

            self._audit(session, "SALE_CREATE", vente.id)
            summary = VenteSummary.from_model(vente)

        logger.info("Vente créée : %s (brouillon)", numero)
        return summary

    def update_sale(
        self,
        sale_id: int,
        date_vente: date,
        lines: Sequence[VenteLigneInput],
    ) -> VenteSummary:
        """Modifie une vente en BROUILLON (remplace intégralement les
        lignes). Refuse toute modification d'une vente déjà validée ou
        annulée."""
        self._permissions.require_permission("SALE_UPDATE")

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)

            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            if vente.statut != StatutOperation.BROUILLON:
                raise ConflictError("Seule une vente en brouillon peut être modifiée.")

            vente.date = date_vente
            vente.lignes = self._build_lignes(session, lines)
            vente.total = self._compute_total(vente.lignes)
            session.flush()

            self._audit(session, "SALE_UPDATE", vente.id)
            summary = VenteSummary.from_model(vente)

        logger.info("Vente modifiée : id=%s -> %s", sale_id, summary.numero)
        return summary

    def delete_sale(self, sale_id: int) -> None:
        """Supprime physiquement une vente en BROUILLON — le seul document
        de l'application où une suppression physique est possible, car un
        brouillon jamais validé n'a produit aucun mouvement de stock ni
        aucune conséquence sur l'historique. Une vente validée ou annulée
        n'est jamais supprimable (voir docstring de module)."""
        self._permissions.require_permission("SALE_UPDATE")

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)

            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            if vente.statut != StatutOperation.BROUILLON:
                raise ConflictError("Seule une vente en brouillon peut être supprimée.")

            numero = vente.numero
            vente_repo.delete(vente)
            self._audit(session, "SALE_DELETE", sale_id)

        logger.info("Vente supprimée (brouillon) : %s", numero)

    # -- cycle de vie -------------------------------------------------------------

    def validate_sale(self, sale_id: int) -> VenteSummary:
        """BROUILLON -> VALIDEE : seul point de la vie d'une vente où le
        stock est modifié. Revérifie que chaque article est actif (l'état a
        pu changer depuis la création du brouillon) et que le stock
        disponible est suffisant, puis applique un mouvement VENTE par ligne
        dans la même transaction que le changement de statut. Le prix de
        vente facturé (``ligne.prix_unitaire``) n'est jamais recalculé ici :
        c'est la valeur historisée à la création/modification du brouillon
        qui fait foi."""
        self._permissions.require_permission("SALE_VALIDATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            article_repo = ArticleRepository(session)

            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            if vente.statut != StatutOperation.BROUILLON:
                raise ConflictError("Seule une vente en brouillon peut être validée.")
            if not vente.lignes:
                raise ValidationError("Une vente doit contenir au moins une ligne pour être validée.")

            for ligne in vente.lignes:
                article = article_repo.get_by_id(ligne.article_id)
                if article is None:
                    raise NotFoundError(f"Article {ligne.article_id} introuvable.")
                if article.statut != StatutActifInactif.ACTIF:
                    raise ValidationError(f"L'article « {article.reference} » est inactif.")

                self._stock.apply_movement(
                    session,
                    article,
                    TypeMouvement.VENTE,
                    -ligne.quantite,
                    user_id=acting_user_id,
                    cout_unitaire=article.cout_moyen_pondere,
                    vente_ligne_id=ligne.id,
                )

            vente.statut = StatutOperation.VALIDEE
            self._audit(session, "SALE_VALIDATE", vente.id)
            summary = VenteSummary.from_model(vente)

        logger.info("Vente validée : %s", summary.numero)
        return summary

    def cancel_sale(self, sale_id: int) -> VenteSummary:
        """VALIDEE -> ANNULEE : génère un mouvement ANNULATION par ligne
        (quantité inverse, positive) restaurant le stock. Conserve
        l'opération originale (jamais de suppression), refuse toute
        double annulation, et refuse l'opération dans son intégralité —
        sans aucune modification, grâce au rollback de ``session_scope`` —
        si elle s'avérait incohérente."""
        self._permissions.require_permission("SALE_CANCEL")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            article_repo = ArticleRepository(session)
            mouvement_repo = MouvementRepository(session)

            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            if vente.statut != StatutOperation.VALIDEE:
                raise ConflictError("Seule une vente validée peut être annulée.")

            for ligne in vente.lignes:
                article = article_repo.get_by_id(ligne.article_id)
                if article is None:
                    raise NotFoundError(f"Article {ligne.article_id} introuvable.")

                origines = mouvement_repo.find_by_vente_ligne(ligne.id, TypeMouvement.VENTE)
                mouvement_origine_id = origines[-1].id if origines else None

                self._stock.apply_movement(
                    session,
                    article,
                    TypeMouvement.ANNULATION,
                    ligne.quantite,
                    user_id=acting_user_id,
                    cout_unitaire=article.cout_moyen_pondere,
                    vente_ligne_id=ligne.id,
                    mouvement_origine_id=mouvement_origine_id,
                )

            vente.statut = StatutOperation.ANNULEE
            self._audit(session, "SALE_CANCEL", vente.id)
            summary = VenteSummary.from_model(vente)

        logger.info("Vente annulée : %s", summary.numero)
        return summary
