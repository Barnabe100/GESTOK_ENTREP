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

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.documents import Vente, VenteLigne
from app.models.enums import (
    ResultatAudit,
    StatutActifInactif,
    StatutOperation,
    StatutPaiement,
    TypeMouvement,
)
from app.models.movement import MouvementStock
from app.models.payment import Paiement
from app.repositories.article_repository import ArticleRepository
from app.repositories.client_repository import ClientRepository
from app.repositories.mouvement_repository import MouvementRepository
from app.repositories.vente_repository import VenteRepository
from app.services.auth.permission_service import PermissionService
from app.services.stock.movement_summary import MouvementSummary
from app.services.stock.stock_service import StockService
from app.utils.dates import validate_not_future_date
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.logging_config import get_logger
from app.utils.money import round_money

logger = get_logger("services.sales")

# Alignées sur les colonnes de ``Paiement`` (app/models/payment.py) : au-delà
# de ces longueurs, une insertion échouerait avec une erreur SQL brute plutôt
# qu'un message métier — voir ``_validate_optional_text``.
MAX_MODE_PAIEMENT_LENGTH = 50
MAX_PAIEMENT_REFERENCE_LENGTH = 100
MAX_PAIEMENT_COMMENTAIRE_LENGTH = 500
MIN_ANNULATION_MOTIF_LENGTH = 5
MAX_ANNULATION_MOTIF_LENGTH = 500


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
class PaiementSummary:
    """Vue en lecture seule d'un paiement enregistré sur une vente."""

    id: int
    vente_id: int
    montant: Decimal
    date_heure: datetime
    mode_paiement: Optional[str]
    reference: Optional[str]
    user_id: int
    username: str
    commentaire: Optional[str]

    @classmethod
    def from_model(cls, paiement: Paiement) -> "PaiementSummary":
        return cls(
            id=paiement.id,
            vente_id=paiement.vente_id,
            montant=paiement.montant,
            date_heure=paiement.date_heure,
            mode_paiement=paiement.mode_paiement,
            reference=paiement.reference,
            user_id=paiement.user_id,
            username=paiement.user.username,
            commentaire=paiement.commentaire,
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
    # Optionnels avec valeur par défaut : champs ajoutés après la première
    # version de ce DTO (vente comptant = client_id/client_nom à None), ne
    # cassent aucun appelant existant.
    client_id: Optional[int] = None
    client_nom: Optional[str] = None
    # Ventes à crédit / paiements partiels : montant_paye est le total
    # courant dénormalisé (voir Vente.montant_paye), reste_a_payer est
    # calculé ici (jamais stocké), jamais négatif par construction.
    montant_paye: Decimal = Decimal("0")
    statut_paiement: StatutPaiement = StatutPaiement.NON_PAYEE
    # None tant que la vente n'est pas annulée (voir Vente.annulation_motif) ;
    # également None pour une vente annulée avant l'introduction de ce champ.
    annulation_motif: Optional[str] = None

    @property
    def reste_a_payer(self) -> Decimal:
        return max(self.total - self.montant_paye, Decimal("0"))

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
            client_id=vente.client_id,
            client_nom=vente.client.nom if vente.client is not None else None,
            montant_paye=vente.montant_paye,
            statut_paiement=vente.statut_paiement,
            annulation_motif=vente.annulation_motif,
        )


@dataclass(frozen=True)
class ClientReceivableSummary:
    """Agrégat des créances d'un client (§5.6) : total facturé/payé/restant
    sur ses ventes VALIDEE (une vente ANNULEE ne représente plus une
    créance active). Ne prétend pas à un tableau de bord financier complet
    — seulement les trois totaux demandés."""

    client_id: int
    total_ventes: Decimal
    total_paye: Decimal

    @property
    def total_reste_a_payer(self) -> Decimal:
        return max(self.total_ventes - self.total_paye, Decimal("0"))


def _validate_positive_quantity(value: Decimal, field_label: str) -> Decimal:
    if value <= 0:
        raise ValidationError(f"Le champ « {field_label} » doit être strictement positif.")
    return value


def _validate_money(value: Decimal, field_label: str) -> Decimal:
    if value < 0:
        raise ValidationError(f"Le champ « {field_label} » ne peut pas être négatif.")
    return value


def _validate_optional_text(value: Optional[str], field_label: str, max_length: int) -> Optional[str]:
    """Même principe que dans ``ClientService``/``SupplierService`` : une
    chaîne vide ou uniquement des espaces devient ``None`` (champ facultatif
    réellement non renseigné), sinon la longueur est bornée pour rester
    cohérente avec la colonne SQL correspondante — jamais laissé remonter
    comme une erreur SQL brute."""
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


def _compute_statut_paiement(total: Decimal, montant_paye: Decimal) -> StatutPaiement:
    """Règle unique de dérivation du statut de paiement (§5.3) : PAYEE dès
    que le reste à payer atteint zéro (y compris une vente au total nul,
    payée par construction sans qu'aucun paiement n'ait été nécessaire),
    PARTIELLEMENT_PAYEE tant qu'un montant a été réglé sans solder le
    reste, NON_PAYEE sinon."""
    reste = total - montant_paye
    if reste <= 0:
        return StatutPaiement.PAYEE
    if montant_paye > 0:
        return StatutPaiement.PARTIELLEMENT_PAYEE
    return StatutPaiement.NON_PAYEE


class SaleService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings
        self._stock = StockService()

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, sale_id: Optional[int], details: Optional[str] = None) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="ventes",
                entite_id=sale_id,
                resultat=ResultatAudit.SUCCES,
                details=details,
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

    def _validate_client(self, session, client_id: Optional[int]) -> Optional[int]:
        """Vérifie qu'un client optionnel existe et est actif avant de
        l'associer à une vente — défense en profondeur, le sélecteur de
        l'interface exclut déjà les clients inactifs (§8 du lot Clients).
        Une vente sans client (``client_id=None``) reste parfaitement valide
        (vente comptant) ; le client n'a aucun impact sur le stock, le CMUP,
        les mouvements, les prix ou les quantités — il ne fait que
        transiter jusqu'à ``Vente.client_id``."""
        if client_id is None:
            return None
        client = ClientRepository(session).get_by_id(client_id)
        if client is None:
            raise NotFoundError(f"Client {client_id} introuvable.")
        if client.statut != StatutActifInactif.ACTIF:
            raise ValidationError(
                f"Le client « {client.nom} » est inactif et ne peut pas être sélectionné pour une nouvelle vente."
            )
        return client_id

    # -- consultation -----------------------------------------------------------

    def list_sales(
        self,
        search: str = "",
        statut: Optional[StatutOperation] = None,
        client_id: Optional[int] = None,
        statut_paiement: Optional[StatutPaiement] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> list[VenteSummary]:
        """Liste générale des ventes, également réutilisée pour l'écran
        Créances clients (§5.7) via les filtres ``statut_paiement``/période —
        pas d'architecture parallèle, la même méthode sert les deux écrans."""
        self._permissions.require_permission("SALE_VIEW")
        with session_scope(self._settings) as session:
            repo = VenteRepository(session)
            ventes = repo.search(
                search, statut=statut, client_id=client_id, statut_paiement=statut_paiement,
                date_from=date_from, date_to=date_to,
            )
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
        client_id: Optional[int] = None,
    ) -> VenteSummary:
        """Crée une vente en BROUILLON : n'a aucun impact sur le stock.
        ``client_id`` est optionnel (``None`` = vente comptant).
        ``date_vente`` ne peut jamais être postérieure à la date du jour, y
        compris en brouillon (voir ``app.utils.dates``)."""
        self._permissions.require_permission("SALE_CREATE")
        date_vente = validate_not_future_date(date_vente)
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            client_id = self._validate_client(session, client_id)

            numero = f"VNT-{vente_repo.count_all() + 1:06d}"

            vente = Vente(
                numero=numero,
                date=date_vente,
                user_id=acting_user_id,
                client_id=client_id,
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
        client_id: Optional[int] = None,
    ) -> VenteSummary:
        """Modifie une vente en BROUILLON (remplace intégralement les
        lignes, et le client — ``client_id=None`` efface l'association
        existante, exactement comme pour toute autre modification de
        brouillon). Refuse toute modification d'une vente déjà validée ou
        annulée. Même règle de date que ``create_sale`` : jamais postérieure
        à aujourd'hui."""
        self._permissions.require_permission("SALE_UPDATE")
        date_vente = validate_not_future_date(date_vente)

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            client_id = self._validate_client(session, client_id)

            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            if vente.statut != StatutOperation.BROUILLON:
                raise ConflictError("Seule une vente en brouillon peut être modifiée.")

            vente.date = date_vente
            vente.client_id = client_id
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

    def validate_sale(
        self,
        sale_id: int,
        paiement_initial: Decimal = Decimal("0"),
        *,
        mode_paiement: Optional[str] = None,
        reference: Optional[str] = None,
        commentaire: Optional[str] = None,
    ) -> VenteSummary:
        """BROUILLON -> VALIDEE : seul point de la vie d'une vente où le
        stock est modifié. Revérifie que chaque article est actif (l'état a
        pu changer depuis la création du brouillon) et que le stock
        disponible est suffisant, puis applique un mouvement VENTE par ligne
        dans la même transaction que le changement de statut. Le prix de
        vente facturé (``ligne.prix_unitaire``) n'est jamais recalculé ici :
        c'est la valeur historisée à la création/modification du brouillon
        qui fait foi.

        ``paiement_initial`` (§5.4) : une vente comptant passe le total
        (statut PAYEE dès la validation) ; une vente à crédit passe 0 (par
        défaut) ou un acompte partiel — dans tous les cas un véritable
        ``Paiement`` est créé dans la même transaction, jamais un simple
        champ écrasé. Un paiement ne peut jamais être enregistré sur un
        brouillon (voir docstring de module et de ``Paiement``) : c'est
        pourquoi cette possibilité n'existe qu'ici et dans
        ``record_payment`` (ventes déjà validées), jamais dans
        ``create_sale``/``update_sale``."""
        self._permissions.require_permission("SALE_VALIDATE")
        acting_user_id = self._acting_user_id()
        paiement_initial = _validate_money(paiement_initial, "paiement initial")

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
            if paiement_initial > vente.total:
                raise ValidationError(
                    "Le paiement initial ne peut pas dépasser le total de la vente "
                    f"({paiement_initial} > {vente.total})."
                )
            if paiement_initial > 0:
                self._permissions.require_permission("SALE_PAYMENT_CREATE")

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
            if paiement_initial > 0:
                session.add(
                    Paiement(
                        vente_id=vente.id, montant=paiement_initial, mode_paiement=mode_paiement,
                        reference=reference, user_id=acting_user_id, commentaire=commentaire,
                    )
                )
                vente.montant_paye = round_money(vente.montant_paye + paiement_initial)
            vente.statut_paiement = _compute_statut_paiement(vente.total, vente.montant_paye)

            self._audit(session, "SALE_VALIDATE", vente.id)
            summary = VenteSummary.from_model(vente)

        logger.info("Vente validée : %s", summary.numero)
        return summary

    def cancel_sale(self, sale_id: int, motif: str) -> VenteSummary:
        """VALIDEE -> ANNULEE : génère un mouvement ANNULATION par ligne
        (quantité inverse, positive) restaurant le stock. Conserve
        l'opération originale (jamais de suppression), refuse toute
        double annulation, et refuse l'opération dans son intégralité —
        sans aucune modification, grâce au rollback de ``session_scope`` —
        si elle s'avérait incohérente.

        ``motif`` est obligatoire (§26 du cahier des charges de ce lot) :
        non vide, non uniquement des espaces, au moins
        ``MIN_ANNULATION_MOTIF_LENGTH`` caractères après trim — vérifié ici,
        jamais uniquement côté interface. Conservé définitivement sur
        ``Vente.annulation_motif`` et jamais modifié ensuite.

        Choix retenu pour une vente déjà partiellement/totalement payée
        (§5.9, point volontairement laissé à l'appréciation de
        l'implémentation par le cahier des charges de ce lot) : l'annulation
        reste possible dans les mêmes conditions qu'avant l'introduction des
        paiements, et les ``Paiement`` déjà enregistrés ne sont **jamais**
        modifiés, supprimés, ni compensés par un remboursement automatique —
        ``montant_paye``/``statut_paiement`` restent figés à leur valeur au
        moment de l'annulation, comme trace historique de ce qui a
        réellement été perçu. Aucune écriture de remboursement n'est créée
        (aucune logique comptable de remboursement n'est demandée par ce
        lot) : un remboursement éventuel reste un processus métier externe à
        gérer manuellement par le client de l'application. Voir le rapport
        de ce lot pour la justification complète de ce choix."""
        self._permissions.require_permission("SALE_CANCEL")
        motif = _validate_annulation_motif(motif)
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
            vente.annulation_motif = motif
            self._audit(
                session, "SALE_CANCEL", vente.id, details=json.dumps({"motif": motif})
            )
            summary = VenteSummary.from_model(vente)

        logger.info("Vente annulée : %s", summary.numero)
        return summary

    # -- paiements (ventes à crédit et paiements partiels, §5) -----------------------

    def record_payment(
        self,
        sale_id: int,
        montant: Decimal,
        *,
        mode_paiement: Optional[str] = None,
        reference: Optional[str] = None,
        commentaire: Optional[str] = None,
    ) -> VenteSummary:
        """Enregistre un paiement ultérieur (§5.5) sur une vente déjà
        validée. Jamais de modification du stock (une opération purement
        financière) ; refuse tout montant qui dépasserait le reste à payer,
        toute vente déjà intégralement payée, et toute vente non validée
        (brouillon jamais payé, vente annulée qui n'est plus une créance
        active)."""
        self._permissions.require_permission("SALE_PAYMENT_CREATE")
        acting_user_id = self._acting_user_id()
        montant = _validate_money(montant, "montant du paiement")
        if montant <= 0:
            raise ValidationError("Le montant du paiement doit être strictement positif.")
        mode_paiement = _validate_optional_text(mode_paiement, "mode de paiement", MAX_MODE_PAIEMENT_LENGTH)
        reference = _validate_optional_text(reference, "référence", MAX_PAIEMENT_REFERENCE_LENGTH)
        commentaire = _validate_optional_text(commentaire, "commentaire", MAX_PAIEMENT_COMMENTAIRE_LENGTH)

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            if vente.statut != StatutOperation.VALIDEE:
                raise ConflictError("Seule une vente validée peut recevoir un paiement.")

            reste = vente.total - vente.montant_paye
            if vente.statut_paiement == StatutPaiement.PAYEE or reste <= 0:
                raise ConflictError("Cette vente est déjà intégralement payée.")
            if montant > reste:
                raise ValidationError(
                    f"Le paiement ({montant}) dépasse le reste à payer ({reste})."
                )

            session.add(
                Paiement(
                    vente_id=vente.id, montant=montant, mode_paiement=mode_paiement,
                    reference=reference, user_id=acting_user_id, commentaire=commentaire,
                )
            )
            vente.montant_paye = round_money(vente.montant_paye + montant)
            vente.statut_paiement = _compute_statut_paiement(vente.total, vente.montant_paye)

            self._audit(session, "SALE_PAYMENT_CREATE", vente.id)
            summary = VenteSummary.from_model(vente)

        logger.info(
            "Paiement enregistré sur la vente %s : %s (reste désormais %s)",
            summary.numero, montant, summary.reste_a_payer,
        )
        return summary

    def list_payments(self, sale_id: int) -> list[PaiementSummary]:
        """Historique des paiements d'une vente (§5.2/§5.6), du plus ancien
        au plus récent."""
        self._permissions.require_permission("SALE_VIEW")
        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            return [PaiementSummary.from_model(p) for p in vente.paiements]

    def get_client_receivable_summary(self, client_id: int) -> ClientReceivableSummary:
        """Créance d'un client (§5.6) : total facturé/payé sur ses ventes
        VALIDEE uniquement — une vente ANNULEE ne compte plus dans les
        totaux (voir ``cancel_sale``)."""
        self._permissions.require_permission("SALE_VIEW")
        with session_scope(self._settings) as session:
            repo = VenteRepository(session)
            ventes = repo.search(client_id=client_id, statut=StatutOperation.VALIDEE)
            total_ventes = round_money(sum((v.total for v in ventes), Decimal("0")))
            total_paye = round_money(sum((v.montant_paye for v in ventes), Decimal("0")))
            return ClientReceivableSummary(
                client_id=client_id, total_ventes=total_ventes, total_paye=total_paye
            )
