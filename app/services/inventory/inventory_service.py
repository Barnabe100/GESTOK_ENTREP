"""Gestion des inventaires : consultation, recherche, création, modification,
validation.

Réutilise strictement :class:`StockService` (aucune deuxième logique de
correction du stock ici ni dans la vue) : toute variation de stock provoquée
par un inventaire passe par ``StockService.apply_movement``, appelé dans la
même transaction (``session_scope``) que la mise à jour du statut de
l'inventaire — soit tout réussit, soit tout est annulé par un rollback.

Règle de capture du stock théorique (§4 du cahier des charges de cette
phase) : ``stock_theorique`` est figé sur chaque ``InventaireLigne`` au
moment où la ligne est construite (création ou modification du brouillon,
voir ``_build_lignes``) — jamais recalculé à la validation. L'écart
(``ecart = stock_physique - stock_theorique``) est donc lui aussi figé dès
cet instant et reflète fidèlement le comptage réellement effectué, même si
le stock réel a évolué entre-temps (autre mouvement validé). À la
validation, ce même écart figé est appliqué comme quantité signée du
mouvement AJUSTEMENT : ``StockService.apply_movement`` calcule alors
``stock_avant``/``stock_après`` à partir du stock RÉEL à cet instant (pas du
``stock_theorique`` figé), ce qui garantit que la correction s'applique
correctement même en cas de mouvements intercurrents, tout en refusant
l'opération si le résultat deviendrait négatif (défense assurée par
StockService lui-même, aucune duplication ici).

Règle de valorisation CMUP (§8) : un ajustement d'inventaire (positif ou
négatif) utilise le type ``AJUSTEMENT`` déjà défini dans
``TypeMouvement`` — jamais ``ENTREE``/``SORTIE``/``VENTE``. Comme
``StockService`` ne recalcule le CMUP que sur un mouvement ``ENTREE``
(règle déjà validée, commune à Sorties/Ventes), un ajustement d'inventaire
ne recalcule jamais le CMUP, qu'il soit positif ou négatif — aucune
nouvelle règle n'a été inventée : c'est la même logique de valorisation déjà
encapsulée dans ``StockService`` que pour les Sorties/Ventes. Le
``cout_unitaire`` porté par le mouvement est le CMUP courant de l'article
(coût de valorisation de la correction), jamais recalculé rétroactivement.

Cycle de vie : BROUILLON -> VALIDE (uniquement — volontairement PAS
d'ANNULE : aucune permission ``INVENTORY_CANCEL`` n'existe en V1, un
inventaire validé ne peut jamais être annulé ni supprimé physiquement ; une
correction ultérieure passe par un nouvel inventaire).
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
from app.models.enums import ResultatAudit, StatutActifInactif, StatutInventaire, TypeMouvement
from app.models.inventory import Inventaire, InventaireLigne
from app.models.movement import MouvementStock
from app.repositories.article_repository import ArticleRepository
from app.repositories.inventaire_repository import InventaireRepository
from app.repositories.mouvement_repository import MouvementRepository
from app.services.auth.permission_service import PermissionService
from app.services.stock.movement_summary import MouvementSummary
from app.services.stock.stock_service import StockService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.inventory")


@dataclass(frozen=True)
class InventaireLigneInput:
    """Ligne saisie en entrée d'un ``create_inventory``/``update_inventory``.

    Ne comporte volontairement aucun ``stock_theorique`` : cette valeur n'est
    jamais une saisie utilisateur, elle est systématiquement capturée depuis
    ``article.stock_actuel`` au moment de la construction de la ligne (voir
    docstring de module)."""

    article_id: int
    stock_physique: Decimal


@dataclass(frozen=True)
class InventaireLigneSummary:
    """Vue en lecture seule d'une ligne d'inventaire."""

    id: int
    article_id: int
    article_reference: str
    article_designation: str
    stock_theorique: Decimal
    stock_physique: Decimal
    ecart: Decimal

    @classmethod
    def from_model(cls, ligne: InventaireLigne) -> "InventaireLigneSummary":
        return cls(
            id=ligne.id,
            article_id=ligne.article_id,
            article_reference=ligne.article.reference,
            article_designation=ligne.article.designation,
            stock_theorique=ligne.stock_theorique,
            stock_physique=ligne.stock_physique,
            ecart=ligne.ecart,
        )


@dataclass(frozen=True)
class InventaireSummary:
    """Vue en lecture seule d'un inventaire, avec ses lignes."""

    id: int
    numero: str
    date: date
    user_id: int
    username: str
    statut: StatutInventaire
    lignes: list[InventaireLigneSummary]
    date_creation: datetime
    date_modification: datetime

    @property
    def ecart_total(self) -> Decimal:
        total = Decimal("0")
        for ligne in self.lignes:
            total += ligne.ecart
        return total

    @classmethod
    def from_model(cls, inventaire: Inventaire) -> "InventaireSummary":
        return cls(
            id=inventaire.id,
            numero=inventaire.numero,
            date=inventaire.date,
            user_id=inventaire.user_id,
            username=inventaire.user.username,
            statut=inventaire.statut,
            lignes=[InventaireLigneSummary.from_model(l) for l in inventaire.lignes],
            date_creation=inventaire.date_creation,
            date_modification=inventaire.date_modification,
        )


def _validate_non_negative_quantity(value: Decimal, field_label: str) -> Decimal:
    if value < 0:
        raise ValidationError(f"Le champ « {field_label} » ne peut pas être négatif.")
    return value


class InventoryService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings
        self._stock = StockService()

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, inventaire_id: Optional[int]) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="inventaires",
                entite_id=inventaire_id,
                resultat=ResultatAudit.SUCCES,
            )
        )

    def _build_lignes(self, session, lines: Sequence[InventaireLigneInput]) -> list[InventaireLigne]:
        article_repo = ArticleRepository(session)
        lignes: list[InventaireLigne] = []
        for line in lines:
            stock_physique = _validate_non_negative_quantity(line.stock_physique, "stock compté")

            article = article_repo.get_by_id(line.article_id)
            if article is None:
                raise NotFoundError(f"Article {line.article_id} introuvable.")
            if article.statut != StatutActifInactif.ACTIF:
                raise ValidationError(f"L'article « {article.reference} » est inactif.")

            # Capture figée du stock théorique à cet instant précis (voir
            # docstring de module) : jamais recalculée à la validation.
            stock_theorique = article.stock_actuel
            lignes.append(
                InventaireLigne(
                    article_id=article.id,
                    stock_theorique=stock_theorique,
                    stock_physique=stock_physique,
                    ecart=stock_physique - stock_theorique,
                )
            )
        return lignes

    # -- consultation -----------------------------------------------------------

    def list_inventories(
        self, search: str = "", statut: Optional[StatutInventaire] = None
    ) -> list[InventaireSummary]:
        self._permissions.require_permission("INVENTORY_VIEW")
        with session_scope(self._settings) as session:
            repo = InventaireRepository(session)
            inventaires = repo.search(search, statut=statut)
            return [InventaireSummary.from_model(i) for i in inventaires]

    def get_inventory(self, inventory_id: int) -> InventaireSummary:
        self._permissions.require_permission("INVENTORY_VIEW")
        with session_scope(self._settings) as session:
            repo = InventaireRepository(session)
            inventaire = repo.get_by_id(inventory_id)
            if inventaire is None:
                raise NotFoundError(f"Inventaire {inventory_id} introuvable.")
            return InventaireSummary.from_model(inventaire)

    def get_inventory_movements(self, inventory_id: int) -> list[MouvementSummary]:
        """Mouvements AJUSTEMENT générés par un inventaire validé (une ligne
        dont l'écart était nul n'en génère aucun) — traçabilité complète."""
        self._permissions.require_permission("STOCK_MOVEMENT_VIEW")
        with session_scope(self._settings) as session:
            inventaire_repo = InventaireRepository(session)
            mouvement_repo = MouvementRepository(session)

            inventaire = inventaire_repo.get_by_id(inventory_id)
            if inventaire is None:
                raise NotFoundError(f"Inventaire {inventory_id} introuvable.")

            movements: list[MouvementStock] = []
            for ligne in inventaire.lignes:
                movements.extend(mouvement_repo.find_by_inventaire_ligne(ligne.id))
            movements.sort(key=lambda m: m.id)
            return [MouvementSummary.from_model(m) for m in movements]

    # -- création / modification -------------------------------------------------

    def create_inventory(
        self,
        date_inventaire: date,
        lines: Sequence[InventaireLigneInput] = (),
    ) -> InventaireSummary:
        """Crée un inventaire en BROUILLON : n'a aucun impact sur le stock."""
        self._permissions.require_permission("INVENTORY_CREATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            inventaire_repo = InventaireRepository(session)

            numero = f"INV-{inventaire_repo.count_all() + 1:06d}"

            inventaire = Inventaire(
                numero=numero,
                date=date_inventaire,
                user_id=acting_user_id,
                statut=StatutInventaire.BROUILLON,
            )
            inventaire.lignes = self._build_lignes(session, lines)
            session.add(inventaire)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError(f"Le numéro « {numero} » est déjà utilisé.") from exc

            self._audit(session, "INVENTORY_CREATE", inventaire.id)
            summary = InventaireSummary.from_model(inventaire)

        logger.info("Inventaire créé : %s (brouillon)", numero)
        return summary

    def update_inventory(
        self,
        inventory_id: int,
        date_inventaire: date,
        lines: Sequence[InventaireLigneInput],
    ) -> InventaireSummary:
        """Modifie un inventaire en BROUILLON (remplace intégralement les
        lignes ; chaque ligne recapture un stock théorique à jour au moment
        de cette modification). Refuse toute modification d'un inventaire
        déjà validé."""
        self._permissions.require_permission("INVENTORY_UPDATE")

        with session_scope(self._settings) as session:
            inventaire_repo = InventaireRepository(session)

            inventaire = inventaire_repo.get_by_id(inventory_id)
            if inventaire is None:
                raise NotFoundError(f"Inventaire {inventory_id} introuvable.")
            if inventaire.statut != StatutInventaire.BROUILLON:
                raise ConflictError("Seul un inventaire en brouillon peut être modifié.")

            inventaire.date = date_inventaire
            inventaire.lignes = self._build_lignes(session, lines)
            session.flush()

            self._audit(session, "INVENTORY_UPDATE", inventaire.id)
            summary = InventaireSummary.from_model(inventaire)

        logger.info("Inventaire modifié : id=%s -> %s", inventory_id, summary.numero)
        return summary

    # -- cycle de vie -------------------------------------------------------------

    def validate_inventory(self, inventory_id: int) -> InventaireSummary:
        """BROUILLON -> VALIDE : seul point de la vie d'un inventaire où le
        stock est modifié. Pour chaque ligne dont l'écart figé (capturé à la
        création/modification du brouillon) est non nul, applique un
        mouvement AJUSTEMENT dans la même transaction que le changement de
        statut. Un écart nul ne génère aucun mouvement. Aucune annulation
        n'est possible après validation (pas de permission
        ``INVENTORY_CANCEL`` en V1) : toute correction ultérieure devra
        passer par un nouvel inventaire."""
        self._permissions.require_permission("INVENTORY_VALIDATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            inventaire_repo = InventaireRepository(session)
            article_repo = ArticleRepository(session)

            inventaire = inventaire_repo.get_by_id(inventory_id)
            if inventaire is None:
                raise NotFoundError(f"Inventaire {inventory_id} introuvable.")
            if inventaire.statut != StatutInventaire.BROUILLON:
                raise ConflictError("Seul un inventaire en brouillon peut être validé.")
            if not inventaire.lignes:
                raise ValidationError("Un inventaire doit contenir au moins une ligne pour être validé.")

            for ligne in inventaire.lignes:
                if ligne.ecart == 0:
                    continue

                article = article_repo.get_by_id(ligne.article_id)
                if article is None:
                    raise NotFoundError(f"Article {ligne.article_id} introuvable.")
                if article.statut != StatutActifInactif.ACTIF:
                    raise ValidationError(f"L'article « {article.reference} » est inactif.")

                self._stock.apply_movement(
                    session,
                    article,
                    TypeMouvement.AJUSTEMENT,
                    ligne.ecart,
                    user_id=acting_user_id,
                    cout_unitaire=article.cout_moyen_pondere,
                    inventaire_ligne_id=ligne.id,
                )

            inventaire.statut = StatutInventaire.VALIDE
            self._audit(session, "INVENTORY_VALIDATE", inventaire.id)
            summary = InventaireSummary.from_model(inventaire)

        logger.info("Inventaire validé : %s", summary.numero)
        return summary
