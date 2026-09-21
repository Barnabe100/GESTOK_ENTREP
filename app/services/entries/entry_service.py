"""Gestion des entrées de stock : consultation, recherche, création,
modification, validation, annulation.

Ce service orchestre :class:`StockService` (moteur de bas niveau) mais ne
contourne jamais ses règles : toute variation de stock provoquée par une
entrée passe exclusivement par ``StockService.apply_movement``, appelé ici
dans la même transaction (``session_scope``) que la mise à jour du statut de
l'entrée — soit tout réussit, soit tout est annulé par un rollback (cf. §4 du
cahier des charges de cette phase).

Cycle de vie d'une entrée : BROUILLON -> VALIDEE -> (ANNULEE).
- Une entrée en BROUILLON ne modifie jamais le stock et reste modifiable
  (remplacement complet des lignes).
- La validation (BROUILLON -> VALIDEE) est l'unique moment où le stock est
  modifié : un mouvement ENTREE est généré par ligne, le CMUP est recalculé,
  puis l'entrée devient non modifiable.
- L'annulation (VALIDEE -> ANNULEE) génère un mouvement ANNULATION par ligne
  (quantité inverse) ; elle est refusée dans son intégralité si elle ferait
  passer le stock d'un seul article en négatif (aucune compensation
  automatique, aucune reconstruction rétroactive du CMUP).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.documents import Entree, EntreeLigne
from app.models.enums import ResultatAudit, StatutActifInactif, StatutOperation, TypeMouvement
from app.models.movement import MouvementStock
from app.repositories.article_repository import ArticleRepository
from app.repositories.entree_repository import EntreeRepository
from app.repositories.mouvement_repository import MouvementRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.auth.permission_service import PermissionService
from app.services.stock.movement_summary import MouvementSummary
from app.services.stock.stock_service import StockService
from app.utils.dates import validate_not_future_date
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.logging_config import get_logger
from app.utils.money import round_money

logger = get_logger("services.entries")

MAX_REFERENCE_DOCUMENT_LENGTH = 100
MAX_COMMENTAIRE_LENGTH = 500
MIN_ANNULATION_MOTIF_LENGTH = 5
MAX_ANNULATION_MOTIF_LENGTH = 500

# Sentinel distinguant « champ non fourni » (conserver la valeur actuelle lors
# d'une modification) de ``None``/chaîne vide (effacer explicitement le champ).
_UNSET = object()


@dataclass(frozen=True)
class EntreeLigneInput:
    """Ligne saisie en entrée d'un ``create_entry``/``update_entry``."""

    article_id: int
    quantite: Decimal
    prix_unitaire: Decimal


@dataclass(frozen=True)
class EntreeLigneSummary:
    """Vue en lecture seule d'une ligne d'entrée."""

    id: int
    article_id: int
    article_reference: str
    article_designation: str
    quantite: Decimal
    prix_unitaire: Decimal
    montant: Decimal

    @classmethod
    def from_model(cls, ligne: EntreeLigne) -> "EntreeLigneSummary":
        return cls(
            id=ligne.id,
            article_id=ligne.article_id,
            article_reference=ligne.article.reference,
            article_designation=ligne.article.designation,
            quantite=ligne.quantite,
            prix_unitaire=ligne.prix_unitaire,
            montant=ligne.montant,
        )


@dataclass(frozen=True)
class EntreeSummary:
    """Vue en lecture seule d'une entrée, avec ses lignes."""

    id: int
    numero: str
    date: date
    fournisseur_id: int
    fournisseur_nom: str
    reference_document: Optional[str]
    user_id: int
    username: str
    commentaire: Optional[str]
    statut: StatutOperation
    lignes: list[EntreeLigneSummary]
    date_creation: datetime
    date_modification: datetime
    # None tant que l'entrée n'est pas annulée (voir Entree.annulation_motif) ;
    # également None pour une entrée annulée avant l'introduction de ce champ.
    annulation_motif: Optional[str] = None

    @property
    def total(self) -> Decimal:
        total = Decimal("0")
        for ligne in self.lignes:
            total += ligne.montant
        return total

    @classmethod
    def from_model(cls, entree: Entree) -> "EntreeSummary":
        return cls(
            id=entree.id,
            numero=entree.numero,
            date=entree.date,
            fournisseur_id=entree.fournisseur_id,
            fournisseur_nom=entree.fournisseur.nom,
            reference_document=entree.reference_document,
            user_id=entree.user_id,
            username=entree.user.username,
            commentaire=entree.commentaire,
            statut=entree.statut,
            lignes=[EntreeLigneSummary.from_model(l) for l in entree.lignes],
            date_creation=entree.date_creation,
            date_modification=entree.date_modification,
            annulation_motif=entree.annulation_motif,
        )


def _validate_positive_quantity(value: Decimal, field_label: str) -> Decimal:
    if value <= 0:
        raise ValidationError(f"Le champ « {field_label} » doit être strictement positif.")
    return value


def _validate_money(value: Decimal, field_label: str) -> Decimal:
    if value < 0:
        raise ValidationError(f"Le champ « {field_label} » ne peut pas être négatif.")
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


def _validate_annulation_motif(value: Optional[str]) -> str:
    """Motif d'annulation obligatoire (§26 du cahier des charges de ce
    lot) : jamais None/vide/uniquement des espaces, jamais un motif
    générique auto-généré — c'est toujours une vraie saisie utilisateur.
    Appliqué ici, côté service, pour rester incontournable même par un
    appel direct hors interface."""
    if value is None:
        raise ValidationError("Le motif d'annulation est obligatoire.")
    value = value.strip()
    if not value:
        raise ValidationError("Le motif d'annulation est obligatoire.")
    if len(value) < MIN_ANNULATION_MOTIF_LENGTH:
        raise ValidationError(
            f"Le motif d'annulation doit contenir au moins {MIN_ANNULATION_MOTIF_LENGTH} caractères."
        )
    if len(value) > MAX_ANNULATION_MOTIF_LENGTH:
        raise ValidationError(
            f"Le motif d'annulation ne doit pas dépasser {MAX_ANNULATION_MOTIF_LENGTH} caractères."
        )
    return value


class EntryService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings
        self._stock = StockService()

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, entree_id: Optional[int], details: Optional[str] = None) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="entrees",
                entite_id=entree_id,
                resultat=ResultatAudit.SUCCES,
                details=details,
            )
        )

    def _build_lignes(self, session, lines: Sequence[EntreeLigneInput]) -> list[EntreeLigne]:
        article_repo = ArticleRepository(session)
        lignes: list[EntreeLigne] = []
        for line in lines:
            quantite = _validate_positive_quantity(line.quantite, "quantité")
            prix_unitaire = _validate_money(line.prix_unitaire, "prix d'achat unitaire")

            article = article_repo.get_by_id(line.article_id)
            if article is None:
                raise NotFoundError(f"Article {line.article_id} introuvable.")
            if article.statut != StatutActifInactif.ACTIF:
                raise ValidationError(f"L'article « {article.reference} » est inactif.")

            lignes.append(
                EntreeLigne(
                    article_id=article.id,
                    quantite=quantite,
                    prix_unitaire=prix_unitaire,
                    montant=round_money(quantite * prix_unitaire),
                )
            )
        return lignes

    # -- consultation -----------------------------------------------------------

    def list_entries(
        self,
        search: str = "",
        fournisseur_id: Optional[int] = None,
        statut: Optional[StatutOperation] = None,
    ) -> list[EntreeSummary]:
        self._permissions.require_permission("STOCK_ENTRY_VIEW")
        with session_scope(self._settings) as session:
            repo = EntreeRepository(session)
            entrees = repo.search(search, fournisseur_id=fournisseur_id, statut=statut)
            return [EntreeSummary.from_model(e) for e in entrees]

    def get_entry(self, entree_id: int) -> EntreeSummary:
        self._permissions.require_permission("STOCK_ENTRY_VIEW")
        with session_scope(self._settings) as session:
            repo = EntreeRepository(session)
            entree = repo.get_by_id(entree_id)
            if entree is None:
                raise NotFoundError(f"Entrée {entree_id} introuvable.")
            return EntreeSummary.from_model(entree)

    def get_entry_movements(self, entree_id: int) -> list[MouvementSummary]:
        """Mouvements générés par une entrée (ENTREE à la validation,
        ANNULATION si l'entrée a été annulée) — traçabilité §9."""
        self._permissions.require_permission("STOCK_MOVEMENT_VIEW")
        with session_scope(self._settings) as session:
            entree_repo = EntreeRepository(session)
            mouvement_repo = MouvementRepository(session)

            entree = entree_repo.get_by_id(entree_id)
            if entree is None:
                raise NotFoundError(f"Entrée {entree_id} introuvable.")

            movements: list[MouvementStock] = []
            for ligne in entree.lignes:
                movements.extend(mouvement_repo.find_by_entree_ligne(ligne.id))
            movements.sort(key=lambda m: m.id)
            return [MouvementSummary.from_model(m) for m in movements]

    # -- création / modification -------------------------------------------------

    def create_entry(
        self,
        fournisseur_id: int,
        date_entree: date,
        lines: Sequence[EntreeLigneInput] = (),
        *,
        reference_document: Optional[str] = None,
        commentaire: Optional[str] = None,
    ) -> EntreeSummary:
        """Crée une entrée en BROUILLON : n'a aucun impact sur le stock
        (§7 du cahier des charges de cette phase). ``date_entree`` ne peut
        jamais être postérieure à la date du jour, y compris en brouillon
        (voir ``app.utils.dates``)."""
        self._permissions.require_permission("STOCK_ENTRY_CREATE")

        date_entree = validate_not_future_date(date_entree)
        reference_document = _validate_optional_text(
            reference_document, "référence document", MAX_REFERENCE_DOCUMENT_LENGTH
        )
        commentaire = _validate_optional_text(commentaire, "commentaire", MAX_COMMENTAIRE_LENGTH)
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            entree_repo = EntreeRepository(session)
            supplier_repo = SupplierRepository(session)

            supplier = supplier_repo.get_by_id(fournisseur_id)
            if supplier is None:
                raise NotFoundError(f"Fournisseur {fournisseur_id} introuvable.")
            if supplier.statut != StatutActifInactif.ACTIF:
                raise ValidationError("Le fournisseur sélectionné est inactif.")

            numero = f"ENT-{entree_repo.count_all() + 1:06d}"

            entree = Entree(
                numero=numero,
                date=date_entree,
                fournisseur_id=fournisseur_id,
                reference_document=reference_document,
                user_id=acting_user_id,
                commentaire=commentaire,
                statut=StatutOperation.BROUILLON,
            )
            entree.lignes = self._build_lignes(session, lines)
            session.add(entree)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError(f"Le numéro « {numero} » est déjà utilisé.") from exc

            self._audit(session, "STOCK_ENTRY_CREATE", entree.id)
            summary = EntreeSummary.from_model(entree)

        logger.info("Entrée créée : %s (brouillon)", numero)
        return summary

    def update_entry(
        self,
        entree_id: int,
        fournisseur_id: int,
        date_entree: date,
        lines: Sequence[EntreeLigneInput],
        *,
        reference_document=_UNSET,
        commentaire=_UNSET,
    ) -> EntreeSummary:
        """Modifie une entrée en BROUILLON (remplace intégralement les
        lignes). Refuse toute modification d'une entrée déjà validée ou
        annulée (§7 : une entrée validée devient non modifiable). Même règle
        de date que ``create_entry`` : jamais postérieure à aujourd'hui."""
        self._permissions.require_permission("STOCK_ENTRY_UPDATE")

        date_entree = validate_not_future_date(date_entree)
        if reference_document is not _UNSET:
            reference_document = _validate_optional_text(
                reference_document, "référence document", MAX_REFERENCE_DOCUMENT_LENGTH
            )
        if commentaire is not _UNSET:
            commentaire = _validate_optional_text(commentaire, "commentaire", MAX_COMMENTAIRE_LENGTH)

        with session_scope(self._settings) as session:
            entree_repo = EntreeRepository(session)
            supplier_repo = SupplierRepository(session)

            entree = entree_repo.get_by_id(entree_id)
            if entree is None:
                raise NotFoundError(f"Entrée {entree_id} introuvable.")
            if entree.statut != StatutOperation.BROUILLON:
                raise ConflictError("Seule une entrée en brouillon peut être modifiée.")

            if fournisseur_id != entree.fournisseur_id:
                supplier = supplier_repo.get_by_id(fournisseur_id)
                if supplier is None:
                    raise NotFoundError(f"Fournisseur {fournisseur_id} introuvable.")
                if supplier.statut != StatutActifInactif.ACTIF:
                    raise ValidationError("Le fournisseur sélectionné est inactif.")

            entree.fournisseur_id = fournisseur_id
            entree.date = date_entree
            if reference_document is not _UNSET:
                entree.reference_document = reference_document
            if commentaire is not _UNSET:
                entree.commentaire = commentaire

            entree.lignes = self._build_lignes(session, lines)
            session.flush()

            self._audit(session, "STOCK_ENTRY_UPDATE", entree.id)
            summary = EntreeSummary.from_model(entree)

        logger.info("Entrée modifiée : id=%s -> %s", entree_id, summary.numero)
        return summary

    # -- cycle de vie -------------------------------------------------------------

    def validate_entry(self, entree_id: int) -> EntreeSummary:
        """BROUILLON -> VALIDEE : seul point de la vie d'une entrée où le
        stock est modifié. Un mouvement ENTREE est appliqué par ligne, dans
        la même transaction que le changement de statut (§4, §7)."""
        self._permissions.require_permission("STOCK_ENTRY_VALIDATE")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            entree_repo = EntreeRepository(session)
            article_repo = ArticleRepository(session)

            entree = entree_repo.get_by_id(entree_id)
            if entree is None:
                raise NotFoundError(f"Entrée {entree_id} introuvable.")
            if entree.statut != StatutOperation.BROUILLON:
                raise ConflictError("Seule une entrée en brouillon peut être validée.")
            if not entree.lignes:
                raise ValidationError("Une entrée doit contenir au moins une ligne pour être validée.")

            for ligne in entree.lignes:
                article = article_repo.get_by_id(ligne.article_id)
                if article is None:
                    raise NotFoundError(f"Article {ligne.article_id} introuvable.")
                self._stock.apply_movement(
                    session,
                    article,
                    TypeMouvement.ENTREE,
                    ligne.quantite,
                    user_id=acting_user_id,
                    cout_unitaire=ligne.prix_unitaire,
                    entree_ligne_id=ligne.id,
                )

            entree.statut = StatutOperation.VALIDEE
            self._audit(session, "STOCK_ENTRY_VALIDATE", entree.id)
            summary = EntreeSummary.from_model(entree)

        logger.info("Entrée validée : %s", summary.numero)
        return summary

    def cancel_entry(self, entree_id: int, motif: str) -> EntreeSummary:
        """VALIDEE -> ANNULEE : génère un mouvement ANNULATION par ligne
        (quantité inverse). Refusée dans son intégralité — sans aucune
        modification, grâce au rollback de ``session_scope`` — si elle ferait
        passer le stock d'un seul article en négatif (§10 : aucune
        compensation automatique, aucun délai).

        ``motif`` est obligatoire (§26 du cahier des charges de ce lot) :
        non vide, non uniquement des espaces, au moins
        ``MIN_ANNULATION_MOTIF_LENGTH`` caractères après trim — vérifié ici,
        jamais uniquement côté interface, avant toute écriture. Conservé
        définitivement sur ``Entree.annulation_motif`` et jamais modifié
        ensuite."""
        self._permissions.require_permission("STOCK_ENTRY_CANCEL")
        motif = _validate_annulation_motif(motif)
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            entree_repo = EntreeRepository(session)
            article_repo = ArticleRepository(session)
            mouvement_repo = MouvementRepository(session)

            entree = entree_repo.get_by_id(entree_id)
            if entree is None:
                raise NotFoundError(f"Entrée {entree_id} introuvable.")
            if entree.statut != StatutOperation.VALIDEE:
                raise ConflictError("Seule une entrée validée peut être annulée.")

            for ligne in entree.lignes:
                article = article_repo.get_by_id(ligne.article_id)
                if article is None:
                    raise NotFoundError(f"Article {ligne.article_id} introuvable.")

                origines = mouvement_repo.find_by_entree_ligne(ligne.id, TypeMouvement.ENTREE)
                mouvement_origine_id = origines[-1].id if origines else None

                self._stock.apply_movement(
                    session,
                    article,
                    TypeMouvement.ANNULATION,
                    -ligne.quantite,
                    user_id=acting_user_id,
                    cout_unitaire=ligne.prix_unitaire,
                    entree_ligne_id=ligne.id,
                    mouvement_origine_id=mouvement_origine_id,
                )

            entree.statut = StatutOperation.ANNULEE
            entree.annulation_motif = motif
            self._audit(
                session, "STOCK_ENTRY_CANCEL", entree.id, details=json.dumps({"motif": motif})
            )
            summary = EntreeSummary.from_model(entree)

        logger.info("Entrée annulée : %s", summary.numero)
        return summary
