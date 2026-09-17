"""Gestion des sorties de stock : consultation, recherche, création,
modification, validation, annulation.

Réutilise strictement :class:`StockService` (aucune deuxième logique de
décrémentation du stock ici ni dans la vue) : toute variation de stock
provoquée par une sortie passe par ``StockService.apply_movement``, appelé
dans la même transaction (``session_scope``) que la mise à jour du statut de
la sortie — soit tout réussit, soit tout est annulé par un rollback.

Cycle de vie d'une sortie : BROUILLON -> VALIDEE -> (ANNULEE).
- Une sortie en BROUILLON ne modifie jamais le stock et reste modifiable
  (remplacement complet des lignes).
- La validation (BROUILLON -> VALIDEE) est l'unique moment où le stock est
  modifié : un mouvement SORTIE est généré par ligne (quantité négative),
  puis la sortie devient non modifiable. Le stock disponible est vérifié par
  ``StockService`` lui-même (refus avant toute écriture si le résultat serait
  négatif) — aucune vérification redondante ici.
- Une sortie ne recalcule jamais le CMUP (règle StockService n°4) : le coût
  de valorisation d'une ligne est le CMUP courant de l'article, capté à
  nouveau (rafraîchi) au moment de la validation — et non figé à la création
  du brouillon, qui n'est qu'un aperçu — puisque c'est la validation qui
  matérialise réellement le mouvement de stock.
- L'annulation (VALIDEE -> ANNULEE) génère un mouvement ANNULATION par ligne
  (quantité inverse, positive : restaure le stock) ; comme pour les Entrées,
  refusée dans son intégralité (rollback) si un cas la rendait incohérente.
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
from app.models.documents import Sortie, SortieLigne
from app.models.enums import ResultatAudit, StatutActifInactif, StatutOperation, TypeMouvement
from app.models.movement import MouvementStock
from app.repositories.article_repository import ArticleRepository
from app.repositories.exit_reason_repository import ExitReasonRepository
from app.repositories.mouvement_repository import MouvementRepository
from app.repositories.sortie_repository import SortieRepository
from app.services.auth.permission_service import PermissionService
from app.services.stock.movement_summary import MouvementSummary
from app.services.stock.stock_service import StockService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.logging_config import get_logger
from app.utils.money import round_money

logger = get_logger("services.exits")

MAX_BENEFICIAIRE_LENGTH = 150
MAX_REFERENCE_LENGTH = 100
MAX_COMMENTAIRE_LENGTH = 500

# Sentinel distinguant « champ non fourni » (conserver la valeur actuelle lors
# d'une modification) de ``None``/chaîne vide (effacer explicitement le champ).
_UNSET = object()


@dataclass(frozen=True)
class SortieLigneInput:
    """Ligne saisie en entrée d'un ``create_exit``/``update_exit``.

    Ne comporte volontairement aucun ``cout_unitaire`` : contrairement au
    prix d'achat d'une Entrée (une vraie saisie utilisateur), le coût d'une
    Sortie est toujours le CMUP courant de l'article — jamais une valeur
    saisie (§6 du cahier des charges de cette phase)."""

    article_id: int
    quantite: Decimal


@dataclass(frozen=True)
class SortieLigneSummary:
    """Vue en lecture seule d'une ligne de sortie."""

    id: int
    article_id: int
    article_reference: str
    article_designation: str
    quantite: Decimal
    cout_unitaire: Decimal
    montant: Decimal

    @classmethod
    def from_model(cls, ligne: SortieLigne) -> "SortieLigneSummary":
        return cls(
            id=ligne.id,
            article_id=ligne.article_id,
            article_reference=ligne.article.reference,
            article_designation=ligne.article.designation,
            quantite=ligne.quantite,
            cout_unitaire=ligne.cout_unitaire,
            montant=ligne.montant,
        )


@dataclass(frozen=True)
class SortieSummary:
    """Vue en lecture seule d'une sortie, avec ses lignes."""

    id: int
    numero: str
    date: date
    motif_id: int
    motif_libelle: str
    beneficiaire: Optional[str]
    reference: Optional[str]
    user_id: int
    username: str
    commentaire: Optional[str]
    statut: StatutOperation
    lignes: list[SortieLigneSummary]
    date_creation: datetime
    date_modification: datetime

    @property
    def total(self) -> Decimal:
        total = Decimal("0")
        for ligne in self.lignes:
            total += ligne.montant
        return total

    @classmethod
    def from_model(cls, sortie: Sortie) -> "SortieSummary":
        return cls(
            id=sortie.id,
            numero=sortie.numero,
            date=sortie.date,
            motif_id=sortie.motif_id,
            motif_libelle=sortie.motif.libelle,
            beneficiaire=sortie.beneficiaire,
            reference=sortie.reference,
            user_id=sortie.user_id,
            username=sortie.user.username,
            commentaire=sortie.commentaire,
            statut=sortie.statut,
            lignes=[SortieLigneSummary.from_model(l) for l in sortie.lignes],
            date_creation=sortie.date_creation,
            date_modification=sortie.date_modification,
        )


def _validate_positive_quantity(value: Decimal, field_label: str) -> Decimal:
    if value <= 0:
        raise ValidationError(f"Le champ « {field_label} » doit être strictement positif.")
    return value


def _validate_optional_text(value: Optional[str], field_label: str, max_length: int) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > max_length:
        raise ValidationError(f"Le champ « {field_label} » ne doit pas dépasser {max_length} caractères.")
    return value


class ExitService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings
        self._stock = StockService()

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, sortie_id: Optional[int]) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="sorties",
                entite_id=sortie_id,
                resultat=ResultatAudit.SUCCES,
            )
        )

    def _build_lignes(self, session, lines: Sequence[SortieLigneInput]) -> list[SortieLigne]:
        article_repo = ArticleRepository(session)
        lignes: list[SortieLigne] = []
        for line in lines:
            quantite = _validate_positive_quantity(line.quantite, "quantité")

            article = article_repo.get_by_id(line.article_id)
            if article is None:
                raise NotFoundError(f"Article {line.article_id} introuvable.")
            if article.statut != StatutActifInactif.ACTIF:
                raise ValidationError(f"L'article « {article.reference} » est inactif.")

            # Coût de valorisation = CMUP courant, simple aperçu à ce stade
            # (brouillon) : rafraîchi à nouveau lors de la validation, seul
            # moment où le mouvement est réellement matérialisé (voir
            # ``validate_exit``).
            cout_unitaire = article.cout_moyen_pondere
            lignes.append(
                SortieLigne(
                    article_id=article.id,
                    quantite=quantite,
                    cout_unitaire=cout_unitaire,
                    montant=round_money(quantite * cout_unitaire),
                )
            )
        return lignes

    # -- consultation -----------------------------------------------------------

    def list_exits(
        self,
        search: str = "",
        motif_id: Optional[int] = None,
        statut: Optional[StatutOperation] = None,
    ) -> list[SortieSummary]:
        self._permissions.require_permission("STOCK_EXIT_VIEW")
        with session_scope(self._settings) as session:
            repo = SortieRepository(session)
            sorties = repo.search(search, motif_id=motif_id, statut=statut)
            return [SortieSummary.from_model(s) for s in sorties]

    def get_exit(self, sortie_id: int) -> SortieSummary:
        self._permissions.require_permission("STOCK_EXIT_VIEW")
        with session_scope(self._settings) as session:
            repo = SortieRepository(session)
            sortie = repo.get_by_id(sortie_id)
            if sortie is None:
                raise NotFoundError(f"Sortie {sortie_id} introuvable.")
            return SortieSummary.from_model(sortie)

    def get_exit_movements(self, sortie_id: int) -> list[MouvementSummary]:
        """Mouvements générés par une sortie (SORTIE à la validation,
        ANNULATION si la sortie a été annulée) — traçabilité complète."""
        self._permissions.require_permission("STOCK_MOVEMENT_VIEW")
        with session_scope(self._settings) as session:
            sortie_repo = SortieRepository(session)
            mouvement_repo = MouvementRepository(session)

            sortie = sortie_repo.get_by_id(sortie_id)
            if sortie is None:
                raise NotFoundError(f"Sortie {sortie_id} introuvable.")

            movements: list[MouvementStock] = []
            for ligne in sortie.lignes:
                movements.extend(mouvement_repo.find_by_sortie_ligne(ligne.id))
            movements.sort(key=lambda m: m.id)
            return [MouvementSummary.from_model(m) for m in movements]

    # -- création / modification -------------------------------------------------

    def create_exit(
        self,
        motif_id: int,
        date_sortie: date,
        lines: Sequence[SortieLigneInput] = (),
        *,
        beneficiaire: Optional[str] = None,
        reference: Optional[str] = None,
        commentaire: Optional[str] = None,
    ) -> SortieSummary:
        """Crée une sortie en BROUILLON : n'a aucun impact sur le stock."""
        self._permissions.require_permission("STOCK_EXIT_CREATE")

        beneficiaire = _validate_optional_text(beneficiaire, "bénéficiaire/service", MAX_BENEFICIAIRE_LENGTH)
        reference = _validate_optional_text(reference, "référence document", MAX_REFERENCE_LENGTH)
        commentaire = _validate_optional_text(commentaire, "commentaire", MAX_COMMENTAIRE_LENGTH)
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            sortie_repo = SortieRepository(session)
            reason_repo = ExitReasonRepository(session)

            motif = reason_repo.get_by_id(motif_id)
            if motif is None:
                raise NotFoundError(f"Motif de sortie {motif_id} introuvable.")
            if motif.statut != StatutActifInactif.ACTIF:
                raise ValidationError("Le motif sélectionné est inactif.")

            numero = f"SOR-{sortie_repo.count_all() + 1:06d}"

            sortie = Sortie(
                numero=numero,
                date=date_sortie,
                motif_id=motif_id,
                beneficiaire=beneficiaire,
                reference=reference,
                user_id=acting_user_id,
                commentaire=commentaire,
                statut=StatutOperation.BROUILLON,
            )
            sortie.lignes = self._build_lignes(session, lines)
            session.add(sortie)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError(f"Le numéro « {numero} » est déjà utilisé.") from exc

            self._audit(session, "STOCK_EXIT_CREATE", sortie.id)
            summary = SortieSummary.from_model(sortie)

        logger.info("Sortie créée : %s (brouillon)", numero)
        return summary

    def update_exit(
        self,
        sortie_id: int,
        motif_id: int,
        date_sortie: date,
        lines: Sequence[SortieLigneInput],
        *,
        beneficiaire=_UNSET,
        reference=_UNSET,
        commentaire=_UNSET,
    ) -> SortieSummary:
        """Modifie une sortie en BROUILLON (remplace intégralement les
        lignes). Refuse toute modification d'une sortie déjà validée ou
        annulée."""
        self._permissions.require_permission("STOCK_EXIT_UPDATE")

        if beneficiaire is not _UNSET:
            beneficiaire = _validate_optional_text(beneficiaire, "bénéficiaire/service", MAX_BENEFICIAIRE_LENGTH)
        if reference is not _UNSET:
            reference = _validate_optional_text(reference, "référence document", MAX_REFERENCE_LENGTH)
        if commentaire is not _UNSET:
            commentaire = _validate_optional_text(commentaire, "commentaire", MAX_COMMENTAIRE_LENGTH)

        with session_scope(self._settings) as session:
            sortie_repo = SortieRepository(session)
            reason_repo = ExitReasonRepository(session)

            sortie = sortie_repo.get_by_id(sortie_id)
            if sortie is None:
                raise NotFoundError(f"Sortie {sortie_id} introuvable.")
            if sortie.statut != StatutOperation.BROUILLON:
                raise ConflictError("Seule une sortie en brouillon peut être modifiée.")

            if motif_id != sortie.motif_id:
                motif = reason_repo.get_by_id(motif_id)
                if motif is None:
                    raise NotFoundError(f"Motif de sortie {motif_id} introuvable.")
                if motif.statut != StatutActifInactif.ACTIF:
                    raise ValidationError("Le motif sélectionné est inactif.")

            sortie.motif_id = motif_id
            sortie.date = date_sortie
            if beneficiaire is not _UNSET:
                sortie.beneficiaire = beneficiaire
            if reference is not _UNSET:
                sortie.reference = reference
            if commentaire is not _UNSET:
                sortie.commentaire = commentaire

            sortie.lignes = self._build_lignes(session, lines)
            session.flush()

            self._audit(session, "STOCK_EXIT_UPDATE", sortie.id)
            summary = SortieSummary.from_model(sortie)

        logger.info("Sortie modifiée : id=%s -> %s", sortie_id, summary.numero)
        return summary

    # -- cycle de vie -------------------------------------------------------------

    def validate_exit(self, sortie_id: int) -> SortieSummary:
        """BROUILLON -> VALIDEE : seul point de la vie d'une sortie où le
        stock est modifié. Revérifie que chaque article est actif (l'état a
        pu changer depuis la création du brouillon), rafraîchit le coût de
        valorisation sur le CMUP courant, puis applique un mouvement SORTIE
        par ligne dans la même transaction que le changement de statut. La
        disponibilité du stock est garantie par ``StockService`` lui-même
        (refus avant écriture si le résultat serait négatif)."""
        self._permissions.require_permission("STOCK_EXIT_VALIDATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            sortie_repo = SortieRepository(session)
            article_repo = ArticleRepository(session)

            sortie = sortie_repo.get_by_id(sortie_id)
            if sortie is None:
                raise NotFoundError(f"Sortie {sortie_id} introuvable.")
            if sortie.statut != StatutOperation.BROUILLON:
                raise ConflictError("Seule une sortie en brouillon peut être validée.")
            if not sortie.lignes:
                raise ValidationError("Une sortie doit contenir au moins une ligne pour être validée.")

            for ligne in sortie.lignes:
                article = article_repo.get_by_id(ligne.article_id)
                if article is None:
                    raise NotFoundError(f"Article {ligne.article_id} introuvable.")
                if article.statut != StatutActifInactif.ACTIF:
                    raise ValidationError(f"L'article « {article.reference} » est inactif.")

                ligne.cout_unitaire = article.cout_moyen_pondere
                ligne.montant = round_money(ligne.quantite * ligne.cout_unitaire)

                self._stock.apply_movement(
                    session,
                    article,
                    TypeMouvement.SORTIE,
                    -ligne.quantite,
                    user_id=acting_user_id,
                    cout_unitaire=ligne.cout_unitaire,
                    sortie_ligne_id=ligne.id,
                )

            sortie.statut = StatutOperation.VALIDEE
            self._audit(session, "STOCK_EXIT_VALIDATE", sortie.id)
            summary = SortieSummary.from_model(sortie)

        logger.info("Sortie validée : %s", summary.numero)
        return summary

    def cancel_exit(self, sortie_id: int) -> SortieSummary:
        """VALIDEE -> ANNULEE : génère un mouvement ANNULATION par ligne
        (quantité inverse, positive) restaurant le stock. Conserve
        l'opération originale (jamais de suppression), refusée dans son
        intégralité — sans aucune modification, grâce au rollback de
        ``session_scope`` — si l'opération s'avérait incohérente."""
        self._permissions.require_permission("STOCK_EXIT_CANCEL")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            sortie_repo = SortieRepository(session)
            article_repo = ArticleRepository(session)
            mouvement_repo = MouvementRepository(session)

            sortie = sortie_repo.get_by_id(sortie_id)
            if sortie is None:
                raise NotFoundError(f"Sortie {sortie_id} introuvable.")
            if sortie.statut != StatutOperation.VALIDEE:
                raise ConflictError("Seule une sortie validée peut être annulée.")

            for ligne in sortie.lignes:
                article = article_repo.get_by_id(ligne.article_id)
                if article is None:
                    raise NotFoundError(f"Article {ligne.article_id} introuvable.")

                origines = mouvement_repo.find_by_sortie_ligne(ligne.id, TypeMouvement.SORTIE)
                mouvement_origine_id = origines[-1].id if origines else None

                self._stock.apply_movement(
                    session,
                    article,
                    TypeMouvement.ANNULATION,
                    ligne.quantite,
                    user_id=acting_user_id,
                    cout_unitaire=ligne.cout_unitaire,
                    sortie_ligne_id=ligne.id,
                    mouvement_origine_id=mouvement_origine_id,
                )

            sortie.statut = StatutOperation.ANNULEE
            self._audit(session, "STOCK_EXIT_CANCEL", sortie.id)
            summary = SortieSummary.from_model(sortie)

        logger.info("Sortie annulée : %s", summary.numero)
        return summary
