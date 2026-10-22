"""Gestion des locations : création, modification, suppression de brouillon,
confirmation, départ, retour (total ou partiel), annulation, caution et
paiements.

Réutilise strictement :class:`StockService` (aucune deuxième logique de
décrémentation du stock ici ni dans la vue) : toute variation de stock
provoquée par une location passe par ``StockService.apply_movement``,
appelé dans la même transaction (``session_scope``) que la mise à jour du
statut de la location — soit tout réussit, soit tout est annulé par un
rollback.

Cycle de vie (``StatutLocation``) : BROUILLON -> CONFIRMEE -> EN_COURS ->
RETOURNEE, ou BROUILLON/CONFIRMEE -> ANNULEE.
- BROUILLON/CONFIRMEE ne modifient jamais le stock : ``qte_reservee`` est
  purement informative (à l'identique d'une vente en brouillon qui ne
  réserve rien non plus) — seule une location en BROUILLON peut être
  modifiée ou physiquement supprimée.
- Le départ (CONFIRMEE -> EN_COURS) est l'unique moment où le stock est
  décrémenté : un mouvement LOCATION_SORTIE est généré par ligne (quantité
  négative égale à ``qte_reservee``), qui devient alors ``qte_en_location``.
- Un retour (partiel ou total, ``return_location_line``) décrémente
  ``qte_en_location`` de la ligne concernée : la quantité remise en bon état
  génère un mouvement LOCATION_RETOUR (restaure le stock) ; la quantité
  immobilisée n'est jamais remise en stock (aucun écran de remise en
  état/mise au rebut dans ce lot — limitation connue et acceptée). La
  location passe automatiquement à RETOURNEE dès que toutes ses lignes ont
  ``qte_en_location == 0`` — pas de statut intermédiaire pour un retour
  partiel.
- L'annulation (BROUILLON/CONFIRMEE -> ANNULEE) ne génère jamais de
  mouvement de stock (rien n'a encore été décrémenté) et est refusée après
  le départ (décision métier explicite de ce lot : seule une suite de
  retours peut alors clore la location).

Facturation : à chaque retour, le montant dû est calculé une seule fois et
historisé sur ``LocationRetour.montant_facture`` (jamais recalculé ensuite)
= ``LocationLigne.tarif_jour`` × nombre de jours entre le départ et ce
retour (minimum 1 jour) × quantité traitée par cet événement (bon état +
immobilisée confondues). Les paiements sont un journal immuable séparé
(``LocationPaiement``), jamais un champ écrasé, et totalement indépendant du
journal des paiements des ventes.

Caution : montant fixe (``Location.caution_montant``), modifiable tant que
la location n'est pas partie ; restitution/retenue enregistrée manuellement
(``Location.caution_rendue``), jamais calculée automatiquement.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import exists, select, update
from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ModeGestionArticle, ResultatAudit, StatutActifInactif, StatutLocation, TypeMouvement
from app.models.rental import Location, LocationLigne, LocationPaiement, LocationRetour
from app.repositories.article_repository import ArticleRepository
from app.repositories.client_repository import ClientRepository
from app.repositories.location_repository import LocationRepository
from app.services.auth.permission_service import PermissionService
from app.services.stock.stock_service import StockService
from app.utils.atomic_transition import apply_atomic_status_transition
from app.utils.dates import validate_not_future_date
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.utils.logging_config import get_logger
from app.utils.money import round_money

logger = get_logger("services.rentals")

MAX_COMMENTAIRE_LENGTH = 500
MAX_MODE_PAIEMENT_LENGTH = 50
MAX_PAIEMENT_REFERENCE_LENGTH = 100
MIN_ANNULATION_MOTIF_LENGTH = 5
MAX_ANNULATION_MOTIF_LENGTH = 500


@dataclass(frozen=True)
class LocationLigneInput:
    """Ligne saisie en entrée d'un ``create_location``/``update_location``.

    ``tarif_jour`` est optionnel : s'il n'est pas fourni, le tarif
    catalogue de l'article (``Article.tarif_location_jour``) est utilisé —
    l'un des deux doit être renseigné, sinon la ligne est refusée. Une fois
    la ligne créée, le tarif retenu est historisé et jamais recalculé si le
    tarif catalogue change ensuite (même principe que
    ``VenteLigneInput.prix_unitaire``)."""

    article_id: int
    quantite: Decimal
    tarif_jour: Optional[Decimal] = None


@dataclass(frozen=True)
class LocationRetourSummary:
    id: int
    location_ligne_id: int
    date_retour: date
    quantite_bon_etat: Decimal
    quantite_immobilisee: Decimal
    montant_facture: Decimal
    user_id: int
    username: str
    date_heure: datetime
    commentaire: Optional[str]

    @classmethod
    def from_model(cls, retour: LocationRetour) -> "LocationRetourSummary":
        return cls(
            id=retour.id,
            location_ligne_id=retour.location_ligne_id,
            date_retour=retour.date_retour,
            quantite_bon_etat=retour.quantite_bon_etat,
            quantite_immobilisee=retour.quantite_immobilisee,
            montant_facture=retour.montant_facture,
            user_id=retour.user_id,
            username=retour.user.username,
            date_heure=retour.date_heure,
            commentaire=retour.commentaire,
        )


@dataclass(frozen=True)
class LocationLigneSummary:
    id: int
    article_id: int
    article_reference: str
    article_designation: str
    qte_prevue: Decimal
    qte_reservee: Decimal
    qte_en_location: Decimal
    qte_immobilisee: Decimal
    tarif_jour: Decimal
    retours: list[LocationRetourSummary] = field(default_factory=list)

    @property
    def montant_facture_total(self) -> Decimal:
        total = Decimal("0")
        for retour in self.retours:
            total += retour.montant_facture
        return total

    @property
    def entierement_retournee(self) -> bool:
        return self.qte_en_location <= 0

    @classmethod
    def from_model(cls, ligne: LocationLigne) -> "LocationLigneSummary":
        return cls(
            id=ligne.id,
            article_id=ligne.article_id,
            article_reference=ligne.article.reference,
            article_designation=ligne.article.designation,
            qte_prevue=ligne.qte_prevue,
            qte_reservee=ligne.qte_reservee,
            qte_en_location=ligne.qte_en_location,
            qte_immobilisee=ligne.qte_immobilisee,
            tarif_jour=ligne.tarif_jour,
            retours=[LocationRetourSummary.from_model(r) for r in ligne.retours],
        )


@dataclass(frozen=True)
class LocationPaiementSummary:
    id: int
    location_id: int
    montant: Decimal
    date_heure: datetime
    mode_paiement: Optional[str]
    reference: Optional[str]
    user_id: int
    username: str
    commentaire: Optional[str]

    @classmethod
    def from_model(cls, paiement: LocationPaiement) -> "LocationPaiementSummary":
        return cls(
            id=paiement.id,
            location_id=paiement.location_id,
            montant=paiement.montant,
            date_heure=paiement.date_heure,
            mode_paiement=paiement.mode_paiement,
            reference=paiement.reference,
            user_id=paiement.user_id,
            username=paiement.user.username,
            commentaire=paiement.commentaire,
        )


@dataclass(frozen=True)
class LocationSummary:
    """Vue en lecture seule d'une location, avec ses lignes et paiements."""

    id: int
    numero: str
    date: date
    # Facultatif (lot « Client facultatif... ») : None = aucun client
    # identifié, à l'identique de VenteSummary.client_id/client_nom.
    client_id: Optional[int]
    client_nom: Optional[str]
    user_id: int
    username: str
    statut: StatutLocation
    date_depart: Optional[date]
    caution_montant: Decimal
    caution_rendue: Decimal
    commentaire: Optional[str]
    annulation_motif: Optional[str]
    lignes: list[LocationLigneSummary]
    paiements: list[LocationPaiementSummary]
    date_creation: datetime
    date_modification: datetime

    @property
    def montant_total_facture(self) -> Decimal:
        total = Decimal("0")
        for ligne in self.lignes:
            total += ligne.montant_facture_total
        return total

    @property
    def montant_paye(self) -> Decimal:
        total = Decimal("0")
        for paiement in self.paiements:
            total += paiement.montant
        return total

    @property
    def reste_a_payer(self) -> Decimal:
        return max(self.montant_total_facture - self.montant_paye, Decimal("0"))

    @classmethod
    def from_model(cls, location: Location) -> "LocationSummary":
        return cls(
            id=location.id,
            numero=location.numero,
            date=location.date,
            client_id=location.client_id,
            client_nom=location.client.nom if location.client is not None else None,
            user_id=location.user_id,
            username=location.user.username,
            statut=location.statut,
            date_depart=location.date_depart,
            caution_montant=location.caution_montant,
            caution_rendue=location.caution_rendue,
            commentaire=location.commentaire,
            annulation_motif=location.annulation_motif,
            lignes=[LocationLigneSummary.from_model(l) for l in location.lignes],
            paiements=[LocationPaiementSummary.from_model(p) for p in location.paiements],
            date_creation=location.date_creation,
            date_modification=location.date_modification,
        )


def _validate_positive_quantity(value: Decimal, field_label: str) -> Decimal:
    if value <= 0:
        raise ValidationError(f"Le champ « {field_label} » doit être strictement positif.")
    return value


def _validate_non_negative_quantity(value: Decimal, field_label: str) -> Decimal:
    if value < 0:
        raise ValidationError(f"Le champ « {field_label} » ne peut pas être négatif.")
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
    """Motif d'annulation obligatoire — même convention que
    ``SaleService``/``EntryService``/``ExitService`` : jamais None/vide,
    toujours une vraie saisie utilisateur, vérifié ici pour rester
    incontournable même par un appel direct hors interface."""
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


class LocationService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings
        self._stock = StockService()

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, location_id: Optional[int], details: Optional[str] = None) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="locations",
                entite_id=location_id,
                resultat=ResultatAudit.SUCCES,
                details=details,
            )
        )

    def _validate_client(self, session, client_id: Optional[int]) -> Optional[int]:
        """Vérifie qu'un client optionnel existe et est actif avant de
        l'associer à une location — même contrat que
        ``SaleService._validate_client`` (vente comptant) : ``client_id=None``
        reste parfaitement valide et ne fait que transiter jusqu'à
        ``Location.client_id``, sans aucun effet sur le cycle de vie, les
        calculs de frais, la caution ou les paiements."""
        if client_id is None:
            return None
        client = ClientRepository(session).get_by_id(client_id)
        if client is None:
            raise NotFoundError(f"Client {client_id} introuvable.")
        if client.statut != StatutActifInactif.ACTIF:
            raise ValidationError("Le client sélectionné est inactif.")
        return client_id

    def _build_lignes(self, session, lines: Sequence[LocationLigneInput]) -> list[LocationLigne]:
        article_repo = ArticleRepository(session)
        lignes: list[LocationLigne] = []
        for line in lines:
            quantite = _validate_positive_quantity(line.quantite, "quantité")

            article = article_repo.get_by_id(line.article_id)
            if article is None:
                raise NotFoundError(f"Article {line.article_id} introuvable.")
            if article.statut != StatutActifInactif.ACTIF:
                raise ValidationError(f"L'article « {article.reference} » est inactif.")
            if article.mode_gestion != ModeGestionArticle.LOCATION:
                raise ValidationError(
                    f"L'article « {article.reference} » n'est pas en mode Location : "
                    "il ne peut pas figurer sur une location."
                )

            tarif_jour = line.tarif_jour if line.tarif_jour is not None else article.tarif_location_jour
            if tarif_jour is None:
                raise ValidationError(
                    f"Aucun tarif de location journalier n'est défini pour « {article.reference} »."
                )
            tarif_jour = _validate_money(tarif_jour, "tarif de location journalier")

            lignes.append(
                LocationLigne(
                    article_id=article.id,
                    qte_prevue=quantite,
                    qte_reservee=quantite,
                    tarif_jour=tarif_jour,
                )
            )
        return lignes

    # -- consultation -------------------------------------------------------------

    def list_locations(
        self,
        search: str = "",
        statut: Optional[StatutLocation] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        client_id: Optional[int] = None,
    ) -> list[LocationSummary]:
        self._permissions.require_permission("LOCATION_VIEW")
        with session_scope(self._settings) as session:
            repo = LocationRepository(session)
            locations = repo.search(
                term=search, statut=statut, date_from=date_from, date_to=date_to, client_id=client_id
            )
            return [LocationSummary.from_model(l) for l in locations]

    def get_location(self, location_id: int) -> LocationSummary:
        self._permissions.require_permission("LOCATION_VIEW")
        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            return LocationSummary.from_model(location)

    # -- création / modification / suppression -------------------------------------

    def create_location(
        self,
        date_location: date,
        client_id: Optional[int],
        lines: Sequence[LocationLigneInput] = (),
        *,
        commentaire: Optional[str] = None,
    ) -> LocationSummary:
        """Crée une location en BROUILLON : n'a aucun impact sur le stock.
        ``qte_reservee`` est fixée à la quantité demandée dès la création
        (purement informative, voir docstring de module) — jamais
        decrémentée d'``Article.stock_actuel`` avant le départ.

        ``client_id`` est optionnel (``None`` = aucun client identifié, lot
        « Client facultatif... ») : une location sans client suit ensuite un
        cycle de vie en tout point identique (confirmation, départ, retour,
        frais, caution, paiements)."""
        self._permissions.require_permission("LOCATION_CREATE")
        date_location = validate_not_future_date(date_location)
        commentaire = _validate_optional_text(commentaire, "commentaire", MAX_COMMENTAIRE_LENGTH)
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            repo = LocationRepository(session)
            client_id = self._validate_client(session, client_id)

            numero = f"LOC-{repo.count_all() + 1:06d}"

            location = Location(
                numero=numero,
                date=date_location,
                client_id=client_id,
                user_id=acting_user_id,
                statut=StatutLocation.BROUILLON,
                caution_montant=Decimal("0"),
                caution_rendue=Decimal("0"),
                commentaire=commentaire,
            )
            location.lignes = self._build_lignes(session, lines)
            session.add(location)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError(f"Le numéro « {numero} » est déjà utilisé.") from exc

            self._audit(session, "LOCATION_CREATE", location.id)
            summary = LocationSummary.from_model(location)

        logger.info("Location créée : %s (brouillon)", numero)
        return summary

    def update_location(
        self,
        location_id: int,
        date_location: date,
        client_id: Optional[int],
        lines: Sequence[LocationLigneInput],
        *,
        commentaire: Optional[str] = None,
    ) -> LocationSummary:
        """Modifie une location en BROUILLON (remplace intégralement les
        lignes). Refuse toute modification d'une location déjà confirmée,
        partie, retournée ou annulée. ``client_id=None`` efface
        l'association existante (lot « Client facultatif... »), comme
        ``SaleService.update_sale``."""
        self._permissions.require_permission("LOCATION_UPDATE")
        date_location = validate_not_future_date(date_location)
        commentaire = _validate_optional_text(commentaire, "commentaire", MAX_COMMENTAIRE_LENGTH)

        with session_scope(self._settings) as session:
            repo = LocationRepository(session)
            client_id = self._validate_client(session, client_id)

            location = repo.get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut != StatutLocation.BROUILLON:
                raise ConflictError("Seule une location en brouillon peut être modifiée.")

            location.date = date_location
            location.client_id = client_id
            location.commentaire = commentaire
            location.lignes = self._build_lignes(session, lines)
            session.flush()

            self._audit(session, "LOCATION_UPDATE", location.id)
            summary = LocationSummary.from_model(location)

        logger.info("Location modifiée : id=%s -> %s", location_id, summary.numero)
        return summary

    def delete_location(self, location_id: int) -> None:
        """Supprime physiquement une location en BROUILLON — aucun mouvement
        de stock n'a encore été généré, à l'identique de
        ``SaleService.delete_sale``."""
        self._permissions.require_permission("LOCATION_UPDATE")

        with session_scope(self._settings) as session:
            repo = LocationRepository(session)
            location = repo.get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut != StatutLocation.BROUILLON:
                raise ConflictError("Seule une location en brouillon peut être supprimée.")

            numero = location.numero
            repo.delete(location)
            self._audit(session, "LOCATION_DELETE", location_id)

        logger.info("Location supprimée (brouillon) : %s", numero)

    # -- caution --------------------------------------------------------------------

    def set_caution_montant(self, location_id: int, montant: Decimal) -> LocationSummary:
        """Définit/modifie le montant de la caution — uniquement tant que la
        location n'est pas partie (BROUILLON/CONFIRMEE) : une fois le
        départ effectué, le montant convenu est figé et seules des
        restitutions/retenues peuvent être enregistrées (voir
        ``record_caution_return``)."""
        self._permissions.require_permission("LOCATION_CAUTION_MANAGE")
        montant = _validate_money(montant, "montant de la caution")

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut not in (StatutLocation.BROUILLON, StatutLocation.CONFIRMEE):
                raise ConflictError(
                    "Le montant de la caution ne peut plus être modifié après le départ de la location."
                )
            if montant < location.caution_rendue:
                raise ValidationError(
                    "Le montant de la caution ne peut pas être inférieur à ce qui a déjà été restitué."
                )

            location.caution_montant = montant
            self._audit(session, "LOCATION_CAUTION_SET", location.id)
            summary = LocationSummary.from_model(location)

        logger.info("Caution définie : location id=%s -> %s", location_id, montant)
        return summary

    def record_caution_return(self, location_id: int, montant: Decimal) -> LocationSummary:
        """Enregistre une restitution/retenue de caution — un simple
        enregistrement manuel cumulatif (``Location.caution_rendue``),
        jamais calculé automatiquement (décision métier explicite de ce
        lot)."""
        self._permissions.require_permission("LOCATION_CAUTION_MANAGE")
        montant = _validate_positive_quantity(montant, "montant restitué")

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")

            nouveau_rendu = round_money(location.caution_rendue + montant)
            if nouveau_rendu > location.caution_montant:
                raise ValidationError(
                    "Le montant restitué dépasserait la caution versée "
                    f"({nouveau_rendu} > {location.caution_montant})."
                )

            location.caution_rendue = nouveau_rendu
            self._audit(session, "LOCATION_CAUTION_RETURN", location.id, details=json.dumps({"montant": str(montant)}))
            summary = LocationSummary.from_model(location)

        logger.info("Caution restituée : location id=%s, montant=%s", location_id, montant)
        return summary

    # -- cycle de vie -----------------------------------------------------------------

    def confirm_location(self, location_id: int) -> LocationSummary:
        """BROUILLON -> CONFIRMEE : ne modifie jamais le stock (voir
        docstring de module). Revérifie que chaque article est toujours
        actif et en mode Location (l'état a pu changer depuis la création
        du brouillon)."""
        self._permissions.require_permission("LOCATION_CONFIRM")

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut != StatutLocation.BROUILLON:
                raise ConflictError("Seule une location en brouillon peut être confirmée.")
            if not location.lignes:
                raise ValidationError("Une location doit contenir au moins une ligne pour être confirmée.")

            for ligne in location.lignes:
                article = ligne.article
                if article.statut != StatutActifInactif.ACTIF:
                    raise ValidationError(f"L'article « {article.reference} » est inactif.")
                if article.mode_gestion != ModeGestionArticle.LOCATION:
                    raise ValidationError(
                        f"L'article « {article.reference} » n'est plus en mode Location."
                    )

            location.statut = StatutLocation.CONFIRMEE
            self._audit(session, "LOCATION_CONFIRM", location.id)
            summary = LocationSummary.from_model(location)

        logger.info("Location confirmée : %s", summary.numero)
        return summary

    def depart_location(self, location_id: int, date_depart: date) -> LocationSummary:
        """CONFIRMEE -> EN_COURS : unique moment où le stock est décrémenté
        (un mouvement LOCATION_SORTIE par ligne, quantité négative égale à
        ``qte_reservee``, qui devient ``qte_en_location``)."""
        self._permissions.require_permission("LOCATION_DEPART")
        date_depart = validate_not_future_date(date_depart)
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            # Transition atomique (audit de concurrence, Lot C) : une simple
            # lecture-puis-test Python laisserait passer deux départs
            # concurrents de la même location — voir app.utils.atomic_transition.
            apply_atomic_status_transition(
                session, Location, location.id,
                expected_status=StatutLocation.CONFIRMEE, new_status=StatutLocation.EN_COURS,
                error_message="Seule une location confirmée peut partir.",
            )
            session.refresh(location)
            if date_depart < location.date:
                raise ValidationError("La date de départ ne peut pas être antérieure à la date de la location.")

            article_repo = ArticleRepository(session)
            for ligne in location.lignes:
                article = article_repo.get_by_id(ligne.article_id)
                if article is None:
                    raise NotFoundError(f"Article {ligne.article_id} introuvable.")
                if article.statut != StatutActifInactif.ACTIF:
                    raise ValidationError(f"L'article « {article.reference} » est inactif.")

                self._stock.apply_movement(
                    session,
                    article,
                    TypeMouvement.LOCATION_SORTIE,
                    -ligne.qte_reservee,
                    user_id=acting_user_id,
                    cout_unitaire=article.cout_moyen_pondere,
                    location_ligne_id=ligne.id,
                )
                ligne.qte_en_location = ligne.qte_reservee
                ligne.qte_reservee = Decimal("0")

            location.date_depart = date_depart
            self._audit(session, "LOCATION_DEPART", location.id)
            summary = LocationSummary.from_model(location)

        logger.info("Location partie : %s", summary.numero)
        return summary

    def return_location_line(
        self,
        location_id: int,
        location_ligne_id: int,
        date_retour: date,
        quantite_bon_etat: Decimal = Decimal("0"),
        quantite_immobilisee: Decimal = Decimal("0"),
        *,
        commentaire: Optional[str] = None,
    ) -> LocationSummary:
        """Enregistre un événement de retour (total ou partiel) sur une
        ligne de location EN_COURS. Décrémente ``qte_en_location`` de la
        quantité totale traitée (bon état + immobilisée) ; la quantité en
        bon état génère un mouvement LOCATION_RETOUR qui restaure le stock,
        la quantité immobilisée n'est jamais remise en stock. Facture ce
        retour : ``tarif_jour`` × nombre de jours depuis le départ (minimum
        1 jour) × quantité totale traitée — montant historisé une seule
        fois sur ``LocationRetour.montant_facture``, jamais recalculé
        ensuite. Fait automatiquement passer la location à RETOURNEE dès
        que toutes ses lignes ont ``qte_en_location == 0`` — pas de statut
        intermédiaire pour un retour partiel."""
        self._permissions.require_permission("LOCATION_RETURN")
        date_retour = validate_not_future_date(date_retour)
        quantite_bon_etat = _validate_non_negative_quantity(quantite_bon_etat, "quantité en bon état")
        quantite_immobilisee = _validate_non_negative_quantity(quantite_immobilisee, "quantité immobilisée")
        commentaire = _validate_optional_text(commentaire, "commentaire", MAX_COMMENTAIRE_LENGTH)
        total_retour = quantite_bon_etat + quantite_immobilisee
        if total_retour <= 0:
            raise ValidationError("Un retour doit porter sur une quantité strictement positive.")
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut != StatutLocation.EN_COURS:
                raise ConflictError("Seule une location en cours peut faire l'objet d'un retour.")
            if date_retour < location.date_depart:
                raise ValidationError("La date de retour ne peut pas être antérieure à la date de départ.")

            ligne = next((l for l in location.lignes if l.id == location_ligne_id), None)
            if ligne is None:
                raise NotFoundError(f"Ligne de location {location_ligne_id} introuvable pour cette location.")
            if total_retour > ligne.qte_en_location:
                raise ValidationError(
                    "La quantité retournée "
                    f"({total_retour}) dépasse la quantité encore en location ({ligne.qte_en_location})."
                )

            jours = max((date_retour - location.date_depart).days, 1)
            montant_facture = round_money(ligne.tarif_jour * jours * total_retour)

            session.add(
                LocationRetour(
                    location_ligne_id=ligne.id,
                    date_retour=date_retour,
                    quantite_bon_etat=quantite_bon_etat,
                    quantite_immobilisee=quantite_immobilisee,
                    montant_facture=montant_facture,
                    user_id=acting_user_id,
                    commentaire=commentaire,
                )
            )

            if quantite_bon_etat > 0:
                self._stock.apply_movement(
                    session,
                    ligne.article,
                    TypeMouvement.LOCATION_RETOUR,
                    quantite_bon_etat,
                    user_id=acting_user_id,
                    cout_unitaire=ligne.article.cout_moyen_pondere,
                    location_ligne_id=ligne.id,
                )

            # Mise à jour atomique au niveau SQL (pas d'affectation Python
            # sur ligne.qte_en_location/qte_immobilisee) : sous accès
            # concurrent sur des lignes différentes d'une même location, une
            # lecture Python déjà en mémoire au moment de ce calcul serait
            # obsolète (même défaut que le compteur de tentatives du lot
            # Récupération administrateur, voir account_recovery_service.py)
            # — la soustraction/addition doit être évaluée par le moteur au
            # moment de l'écriture, sur la valeur réellement en base.
            #
            # Audit de concurrence (Lot C) : la clause WHERE ci-dessous
            # (qte_en_location >= total_retour) est ajoutée ici — sans elle,
            # deux retours concurrents sur cette même ligne pouvaient tous
            # les deux réussir le contrôle Python ci-dessus (lecture
            # commune, avant écriture) et faire passer qte_en_location en
            # négatif, exactement le défaut déjà corrigé pour
            # Article.stock_actuel par StockService.apply_movement — repris
            # ici selon le même principe (jamais une emphase sur la lecture
            # Python, toujours une condition évaluée par le moteur au
            # moment de l'écriture), pas une copie de son code.
            result = session.execute(
                update(LocationLigne)
                .where(LocationLigne.id == ligne.id, LocationLigne.qte_en_location >= total_retour)
                .values(
                    qte_en_location=LocationLigne.qte_en_location - total_retour,
                    qte_immobilisee=LocationLigne.qte_immobilisee + quantite_immobilisee,
                )
            )
            if result.rowcount == 0:
                qte_en_location_reelle = session.scalar(
                    select(LocationLigne.qte_en_location).where(LocationLigne.id == ligne.id)
                )
                raise ValidationError(
                    "La quantité retournée "
                    f"({total_retour}) dépasse la quantité encore en location ({qte_en_location_reelle})."
                )
            session.refresh(ligne)

            # Transition RETOURNEE elle aussi décidée de façon atomique :
            # la sous-requête NOT EXISTS est évaluée par SQLite au moment de
            # cette unique instruction UPDATE, sur l'état réellement en base
            # de TOUTES les lignes (y compris celles modifiées par un autre
            # retour concurrent sur une ligne différente de cette même
            # location) — jamais sur la collection ``location.lignes`` déjà
            # chargée en mémoire Python, potentiellement obsolète.
            still_out = exists().where(
                LocationLigne.location_id == location.id, LocationLigne.qte_en_location > 0
            )
            session.execute(
                update(Location)
                .where(Location.id == location.id, ~still_out)
                .values(statut=StatutLocation.RETOURNEE)
            )
            session.refresh(location)

            self._audit(
                session,
                "LOCATION_RETURN",
                location.id,
                details=json.dumps(
                    {"location_ligne_id": location_ligne_id, "montant_facture": str(montant_facture)}
                ),
            )
            summary = LocationSummary.from_model(location)

        logger.info(
            "Retour enregistré : location=%s, ligne=%s, montant facturé=%s",
            summary.numero, location_ligne_id, montant_facture,
        )
        return summary

    def cancel_location(self, location_id: int, motif: str) -> LocationSummary:
        """BROUILLON/CONFIRMEE -> ANNULEE : jamais après le départ (décision
        métier explicite de ce lot) — aucun mouvement de stock n'a encore
        été généré à ce stade, donc aucun mouvement compensatoire n'est
        nécessaire. ``motif`` obligatoire, même convention que
        ``SaleService.cancel_sale``."""
        self._permissions.require_permission("LOCATION_CANCEL")

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut not in (StatutLocation.BROUILLON, StatutLocation.CONFIRMEE):
                raise ConflictError(
                    "Seule une location en brouillon ou confirmée (avant départ) peut être annulée."
                )
            motif = _validate_annulation_motif(motif)

            location.statut = StatutLocation.ANNULEE
            location.annulation_motif = motif
            self._audit(session, "LOCATION_CANCEL", location.id, details=json.dumps({"motif": motif}))
            summary = LocationSummary.from_model(location)

        logger.info("Location annulée : %s", summary.numero)
        return summary

    # -- paiements ------------------------------------------------------------------

    def record_payment(
        self,
        location_id: int,
        montant: Decimal,
        *,
        mode_paiement: Optional[str] = None,
        reference: Optional[str] = None,
        commentaire: Optional[str] = None,
    ) -> LocationSummary:
        """Enregistre un paiement sur une location déjà partie (EN_COURS ou
        RETOURNEE) — jamais sur un brouillon ou avant départ, puisque rien
        n'est encore facturé avant le premier retour. Refuse un paiement qui
        dépasserait le montant total déjà facturé (somme des
        ``LocationRetour.montant_facture``), à l'identique de
        ``SaleService.record_payment``."""
        self._permissions.require_permission("LOCATION_PAYMENT_CREATE")
        montant = _validate_positive_quantity(montant, "montant du paiement")
        mode_paiement = _validate_optional_text(mode_paiement, "mode de paiement", MAX_MODE_PAIEMENT_LENGTH)
        reference = _validate_optional_text(reference, "référence", MAX_PAIEMENT_REFERENCE_LENGTH)
        commentaire = _validate_optional_text(commentaire, "commentaire", MAX_COMMENTAIRE_LENGTH)
        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut not in (StatutLocation.EN_COURS, StatutLocation.RETOURNEE):
                raise ConflictError("Un paiement ne peut être enregistré que sur une location partie.")

            summary_before = LocationSummary.from_model(location)
            nouveau_total_paye = round_money(summary_before.montant_paye + montant)
            if nouveau_total_paye > summary_before.montant_total_facture:
                raise ValidationError(
                    "Le paiement dépasserait le montant total facturé "
                    f"({nouveau_total_paye} > {summary_before.montant_total_facture})."
                )

            # Ajouté via la relation (jamais seulement session.add) : la
            # collection location.paiements vient d'être chargée ci-dessus
            # par summary_before, et session.add seul ne la mettrait pas à
            # jour en mémoire — LocationSummary.from_model construit plus
            # bas verrait alors encore l'ancienne liste (sans ce paiement).
            location.paiements.append(
                LocationPaiement(
                    montant=montant,
                    mode_paiement=mode_paiement,
                    reference=reference,
                    user_id=acting_user_id,
                    commentaire=commentaire,
                )
            )
            session.flush()
            self._audit(session, "LOCATION_PAYMENT_CREATE", location.id)
            summary = LocationSummary.from_model(location)

        logger.info("Paiement enregistré : location=%s, montant=%s", summary.numero, montant)
        return summary
