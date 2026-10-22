"""Assemblage des données nécessaires au reçu d'une vente validée.

Strictement en lecture seule : accède directement à ``VenteRepository`` et
``MouvementRepository`` plutôt que de composer via les méthodes déjà
publiques de :class:`SaleService`, pour ne dépendre que de la permission
``SALE_VIEW`` — même principe déjà établi par ``ReportService`` (voir son
docstring de module) : un rôle disposant de ``SALE_VIEW`` sans disposer de
``STOCK_MOVEMENT_VIEW`` (ex. Vendeur) doit tout de même pouvoir imprimer le
reçu de sa propre vente, l'heure de vente étant dérivée des mouvements
uniquement pour l'affichage du document, jamais exposée comme une
consultation du module Mouvements.

Le format du document (A4, ticket 80 mm, ...) n'est jamais une
préoccupation de ce service : il produit toujours le même
:class:`SaleReceiptData`, seul ``ReceiptDocumentBuilder`` (autre module)
choisit le gabarit de rendu.

Le client associé à la vente (``Vente.client``, optionnel) est lu de la
même façon que l'utilisateur/les articles ci-dessus — par relation ORM,
jamais via ``ClientService`` — pour ne dépendre, là aussi, que de
``SALE_VIEW`` (voir ``build_sale_receipt``).

Harmonisation reçu de vente / reçu de paiement (lot dédié) : deux documents
volontairement distincts (jamais fusionnés) — le reçu de vente représente
la transaction complète (articles, total, état de paiement courant), le
reçu de paiement représente un règlement précis et renvoie à la vente par
son numéro (référence croisée déjà existante, jamais recalculée). Le reçu
d'un paiement reprend désormais aussi son mode de paiement et sa référence
tels qu'enregistrés sur ``Paiement`` (voir ``build_payment_receipt``) —
déjà affichés dans l'historique à l'écran, il n'y a aucune raison qu'ils
manquent sur le document imprimé/exporté de ce même paiement.

Lot 22 (§F — harmonisation des reçus de location) : deux documents
volontairement distincts, jamais fusionnés, pour la même raison déjà
établie ci-dessus entre reçu de vente et reçu de paiement — un seul
document ne peut pas représenter à la fois « ce qui est réservé » et « ce
qui a réellement été facturé » :

- ``build_location_reservation_voucher`` — justificatif de réservation,
  disponible uniquement avant le départ (BROUILLON/CONFIRMEE) : aucun
  montant total n'y figure jamais, la facturation d'une location se fait à
  la journée et le nombre de jours n'est connu qu'au retour — l'inventer
  ici serait un engagement chiffré fictif, jamais acceptable sur un
  document remis à un client.
- ``build_location_receipt`` — reçu de location, disponible uniquement
  après le départ (EN_COURS/RETOURNEE) : reprend les montants réellement
  facturés (``LocationRetour.montant_facture``, jamais recalculés), les
  paiements enregistrés et le solde restant. La caution y est toujours
  affichée séparément (jamais incluse dans le total facturé, qui ne
  concerne que la location des articles eux-mêmes — voir
  ``LocationService.set_caution_montant``/``record_caution_return``).

Comme ``build_sale_receipt`` ci-dessus, ces deux méthodes accèdent
directement à ``LocationRepository`` (jamais via ``LocationService``) pour
ne dépendre que de la permission ``LOCATION_VIEW`` — en particulier pour
les coordonnées complètes du client (téléphone/adresse/email), que
``LocationSummary.client_nom`` seul n'expose pas et qu'une lecture via
``ClientService`` exigerait en plus ``CLIENT_VIEW``, une permission
distincte qu'un rôle autorisé à consulter ses propres locations ne
possède pas nécessairement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import time as time_type
from decimal import Decimal
from pathlib import Path
from typing import Optional

from datetime import datetime

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.enums import StatutLocation, StatutOperation, StatutPaiement, TypeMouvement
from app.models.movement import MouvementStock
from app.repositories.location_repository import LocationRepository
from app.repositories.mouvement_repository import MouvementRepository
from app.repositories.vente_repository import VenteRepository
from app.services.auth.permission_service import PermissionService
from app.services.settings.company_settings_service import get_company_profile, get_effective_currency
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.money import round_money


@dataclass(frozen=True)
class SaleReceiptLine:
    """Ligne d'un reçu — mêmes valeurs déjà historisées sur la vente,
    jamais recalculées (prix réellement facturé au moment de la vente)."""

    article_reference: str
    article_designation: str
    quantite: Decimal
    prix_unitaire: Decimal
    sous_total: Decimal


@dataclass(frozen=True)
class SaleReceiptPaymentLine:
    """Une entrée de l'historique des paiements affiché sur le reçu unifié
    (Lot 21) — mêmes champs que :class:`PaiementSummary`/``Paiement``,
    jamais inventés : ``mode_paiement``/``reference``/``commentaire``
    restent ``None`` s'ils n'ont pas été renseignés au moment du paiement,
    jamais remplacés par une valeur par défaut fictive."""

    date_heure: datetime
    montant: Decimal
    mode_paiement: Optional[str]
    reference: Optional[str]
    commentaire: Optional[str]
    username: str


@dataclass(frozen=True)
class SaleReceiptData:
    """Données complètes d'un reçu de vente : vente + profil entreprise +
    devise effective, indépendant de tout format de rendu."""

    numero: str
    date: date_type
    heure: Optional[time_type]
    username: str
    lignes: list[SaleReceiptLine]
    total: Decimal
    devise: str
    entreprise_nom: Optional[str]
    entreprise_adresse: Optional[str]
    entreprise_telephone: Optional[str]
    entreprise_email: Optional[str]
    entreprise_logo_path: Optional[Path]
    # Optionnels avec valeur par défaut : champs ajoutés après la première
    # version de ce DTO (vente comptant = tous à None), ne cassent aucun
    # appelant existant. Pas de client_id : ce DTO sert à afficher un
    # document, jamais à agir sur le client.
    client_nom: Optional[str] = None
    client_telephone: Optional[str] = None
    client_adresse: Optional[str] = None
    client_email: Optional[str] = None
    # Ventes à crédit / paiements partiels (§5.8) : toujours renseignés
    # (comptant = montant_paye == total, statut PAYEE), jamais absents —
    # affichés sur tout reçu, comptant ou partiel, pour la même transparence.
    montant_paye: Decimal = Decimal("0")
    statut_paiement: StatutPaiement = StatutPaiement.PAYEE
    # Lot 21 — reçu unifié : historique complet des paiements de la vente
    # (jamais une simple liste d'ids), toujours en plus de ``montant_paye``/
    # ``statut_paiement`` ci-dessus — le total de la vente, le total payé et
    # chaque règlement individuel restent trois informations distinctes,
    # jamais confondues sur le document (voir ``receipt_document.py``).
    paiements: tuple[SaleReceiptPaymentLine, ...] = ()
    # Phrase de pied de reçu configurable (Lot 21) — chaîne vide si
    # explicitement désactivée dans les paramètres (voir
    # ``CompanySettingsConfig.recu_pied_de_page``), jamais ``None``.
    pied_de_page: str = ""

    @property
    def reste_a_payer(self) -> Decimal:
        return max(self.total - self.montant_paye, Decimal("0"))


@dataclass(frozen=True)
class PaymentReceiptData:
    """Données du reçu d'un paiement ultérieur (§5.8) — document distinct du
    reçu de vente : ne reprend jamais les lignes d'articles, seulement la
    trace du règlement (référence de la vente, montant, total payé et reste
    après ce paiement, date, utilisateur)."""

    vente_numero: str
    client_nom: Optional[str]
    montant: Decimal
    total_vente: Decimal
    total_paye_apres: Decimal
    date_heure: datetime
    username: str
    devise: str
    entreprise_nom: Optional[str]
    entreprise_adresse: Optional[str]
    entreprise_telephone: Optional[str]
    entreprise_email: Optional[str]
    # Ajoutés après la première version de ce DTO (valeur par défaut, ne
    # cassent aucun appelant existant — même principe que SaleReceiptData
    # ci-dessus) : repris tels qu'enregistrés sur ``Paiement`` (voir
    # SaleService.record_payment) — déjà affichés dans l'historique à
    # l'écran (SaleDetailDialog.payments_table), le reçu PDF de ce même
    # paiement doit montrer la même information.
    mode_paiement: Optional[str] = None
    reference: Optional[str] = None

    @property
    def reste_a_payer(self) -> Decimal:
        return max(self.total_vente - self.total_paye_apres, Decimal("0"))


@dataclass(frozen=True)
class LocationReservationLigne:
    """Ligne d'un justificatif de réservation — quantité et tarif journalier
    réservés, jamais de montant (voir docstring de module : aucun total
    n'est calculable avant le retour)."""

    article_reference: str
    article_designation: str
    quantite_reservee: Decimal
    tarif_jour: Decimal


@dataclass(frozen=True)
class LocationReservationVoucherData:
    """Données complètes du justificatif de réservation (avant départ) —
    jamais un reçu financier (voir docstring de module)."""

    numero: str
    date: date_type
    username: str
    lignes: list[LocationReservationLigne]
    caution_montant: Decimal
    devise: str
    entreprise_nom: Optional[str]
    entreprise_adresse: Optional[str]
    entreprise_telephone: Optional[str]
    entreprise_email: Optional[str]
    entreprise_logo_path: Optional[Path]
    client_nom: Optional[str] = None
    client_telephone: Optional[str] = None
    client_adresse: Optional[str] = None
    client_email: Optional[str] = None
    pied_de_page: str = ""


@dataclass(frozen=True)
class LocationReceiptRetour:
    """Un événement de retour facturé — reprend tel quel le montant déjà
    historisé par ``LocationService.return_location_line`` (jamais
    recalculé) ; ``jours`` n'est, lui, recalculé qu'à l'affichage à partir
    des deux dates déjà connues (départ, retour), pour rester transparent
    sur l'origine du montant sans dupliquer la règle de facturation."""

    date_retour: date_type
    quantite: Decimal
    jours: int
    montant_facture: Decimal


@dataclass(frozen=True)
class LocationReceiptLigne:
    """Ligne facturée du reçu de location — un ou plusieurs retours
    (restitution totale ou partielle, voir ``LocationLigneSummary``)."""

    article_reference: str
    article_designation: str
    tarif_jour: Decimal
    retours: tuple[LocationReceiptRetour, ...]

    @property
    def montant_facture_total(self) -> Decimal:
        return round_money(sum((r.montant_facture for r in self.retours), Decimal("0")))


@dataclass(frozen=True)
class LocationReceiptPaymentLine:
    """Même structure que :class:`SaleReceiptPaymentLine`, pour la même
    raison (historique affiché tel qu'enregistré, jamais complété)."""

    date_heure: datetime
    montant: Decimal
    mode_paiement: Optional[str]
    reference: Optional[str]
    commentaire: Optional[str]
    username: str


@dataclass(frozen=True)
class LocationReceiptData:
    """Données complètes du reçu de location (après départ) — montants
    réellement facturés, jamais ceux réservés à la création."""

    numero: str
    date: date_type
    date_depart: Optional[date_type]
    username: str
    statut: StatutLocation
    lignes: list[LocationReceiptLigne]
    total_facture: Decimal
    montant_paye: Decimal
    paiements: tuple[LocationReceiptPaymentLine, ...]
    caution_montant: Decimal
    caution_rendue: Decimal
    devise: str
    entreprise_nom: Optional[str]
    entreprise_adresse: Optional[str]
    entreprise_telephone: Optional[str]
    entreprise_email: Optional[str]
    entreprise_logo_path: Optional[Path]
    client_nom: Optional[str] = None
    client_telephone: Optional[str] = None
    client_adresse: Optional[str] = None
    client_email: Optional[str] = None
    pied_de_page: str = ""

    @property
    def reste_a_payer(self) -> Decimal:
        return max(self.total_facture - self.montant_paye, Decimal("0"))


class ReceiptService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def build_sale_receipt(self, sale_id: int) -> SaleReceiptData:
        """Construit le reçu d'une vente **validée** uniquement (§4 de ce
        lot) : une vente en brouillon n'est pas une transaction réelle, une
        vente annulée n'est pas prise en charge dans cette V1."""
        self._permissions.require_permission("SALE_VIEW")

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            mouvement_repo = MouvementRepository(session)

            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")
            if vente.statut != StatutOperation.VALIDEE:
                raise ValidationError(
                    "Le reçu n'est disponible que pour une vente validée."
                )

            lignes = [
                SaleReceiptLine(
                    article_reference=ligne.article.reference,
                    article_designation=ligne.article.designation,
                    quantite=ligne.quantite,
                    prix_unitaire=ligne.prix_unitaire,
                    sous_total=ligne.sous_total,
                )
                for ligne in vente.lignes
            ]

            vente_movements: list[MouvementStock] = []
            for ligne in vente.lignes:
                vente_movements.extend(mouvement_repo.find_by_vente_ligne(ligne.id, TypeMouvement.VENTE))
            heure = min((m.date_heure for m in vente_movements), default=None)

            numero = vente.numero
            sale_date = vente.date
            username = vente.user.username
            total = vente.total
            montant_paye = vente.montant_paye
            statut_paiement = vente.statut_paiement

            # Lecture directe de la relation ORM (déjà chargée dans cette
            # session, comme vente.user/ligne.article ci-dessus) : jamais via
            # ClientService, pour ne dépendre que de SALE_VIEW (§ règle
            # permissions de ce lot). Ne filtre jamais par statut ACTIF/
            # INACTIF : un client désactivé associé à une vente historique
            # reste normalement affiché. Si la ligne référencée n'existe
            # plus (anomalie hors du fonctionnement normal de l'application
            # — la FK ventes.client_id empêche ce cas en temps normal),
            # SQLAlchemy résout simplement la relation à None : aucun crash,
            # aucune invention de client, le reçu se comporte comme une
            # vente sans client.
            client = vente.client
            client_nom = client.nom if client is not None else None
            client_telephone = client.telephone if client is not None else None
            client_adresse = client.adresse if client is not None else None
            client_email = client.email if client is not None else None

            # Historique des paiements (Lot 21) — même relation ORM déjà
            # chargée dans cette session que ``SaleService.list_payments``,
            # jamais réordonnée : l'ordre affiché sur le reçu est le même
            # que celui déjà utilisé à l'écran (SaleDetailDialog.payments_table).
            paiements = tuple(
                SaleReceiptPaymentLine(
                    date_heure=p.date_heure,
                    montant=p.montant,
                    mode_paiement=p.mode_paiement,
                    reference=p.reference,
                    commentaire=p.commentaire,
                    username=p.user.username,
                )
                for p in vente.paiements
            )

        profile = get_company_profile(self._settings)
        devise = get_effective_currency(self._settings)

        return SaleReceiptData(
            numero=numero,
            date=sale_date,
            heure=heure.time() if heure is not None else None,
            username=username,
            lignes=lignes,
            total=total,
            devise=devise,
            entreprise_nom=profile.nom,
            entreprise_adresse=profile.adresse,
            entreprise_telephone=profile.telephone,
            entreprise_email=profile.email,
            entreprise_logo_path=profile.logo_path,
            client_nom=client_nom,
            client_telephone=client_telephone,
            client_adresse=client_adresse,
            client_email=client_email,
            montant_paye=montant_paye,
            statut_paiement=statut_paiement,
            paiements=paiements,
            pied_de_page=profile.recu_pied_de_page,
        )

    def build_payment_receipt(self, sale_id: int, paiement_id: int) -> PaymentReceiptData:
        """Reçu d'un paiement ultérieur (§5.8), disponible dès qu'une vente
        est validée (jamais pour un brouillon, qui ne peut avoir aucun
        paiement — voir ``SaleService``)."""
        self._permissions.require_permission("SALE_VIEW")

        with session_scope(self._settings) as session:
            vente_repo = VenteRepository(session)
            vente = vente_repo.get_by_id(sale_id)
            if vente is None:
                raise NotFoundError(f"Vente {sale_id} introuvable.")

            paiement = next((p for p in vente.paiements if p.id == paiement_id), None)
            if paiement is None:
                raise NotFoundError(f"Paiement {paiement_id} introuvable pour la vente {sale_id}.")

            # Total payé « après ce paiement » reconstruit depuis l'historique
            # jusqu'à ce paiement inclus (jamais depuis le total courant de la
            # vente, qui peut avoir évolué depuis via des paiements
            # ultérieurs) — le reçu d'un paiement passé reste toujours exact.
            paiements_jusque_la = [p for p in vente.paiements if p.id <= paiement_id]
            total_paye_apres = round_money(sum((p.montant for p in paiements_jusque_la), Decimal("0")))

            vente_numero = vente.numero
            total_vente = vente.total
            client_nom = vente.client.nom if vente.client is not None else None
            montant = paiement.montant
            date_heure = paiement.date_heure
            username = paiement.user.username
            mode_paiement = paiement.mode_paiement
            reference = paiement.reference

        profile = get_company_profile(self._settings)
        devise = get_effective_currency(self._settings)

        return PaymentReceiptData(
            vente_numero=vente_numero,
            client_nom=client_nom,
            montant=montant,
            total_vente=total_vente,
            total_paye_apres=total_paye_apres,
            date_heure=date_heure,
            username=username,
            devise=devise,
            entreprise_nom=profile.nom,
            entreprise_adresse=profile.adresse,
            entreprise_telephone=profile.telephone,
            entreprise_email=profile.email,
            mode_paiement=mode_paiement,
            reference=reference,
        )

    def build_location_reservation_voucher(self, location_id: int) -> LocationReservationVoucherData:
        """Justificatif de réservation (§F), disponible uniquement avant le
        départ — voir docstring de module pour la raison de cette
        restriction et de l'absence de tout montant total."""
        self._permissions.require_permission("LOCATION_VIEW")

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut not in (StatutLocation.BROUILLON, StatutLocation.CONFIRMEE):
                raise ValidationError(
                    "Le justificatif de réservation n'est disponible qu'avant le départ de la location."
                )

            numero = location.numero
            location_date = location.date
            username = location.user.username
            caution_montant = location.caution_montant

            lignes = [
                LocationReservationLigne(
                    article_reference=ligne.article.reference,
                    article_designation=ligne.article.designation,
                    quantite_reservee=ligne.qte_reservee,
                    tarif_jour=ligne.tarif_jour,
                )
                for ligne in location.lignes
            ]

            client = location.client
            client_nom = client.nom if client is not None else None
            client_telephone = client.telephone if client is not None else None
            client_adresse = client.adresse if client is not None else None
            client_email = client.email if client is not None else None

        profile = get_company_profile(self._settings)
        devise = get_effective_currency(self._settings)

        return LocationReservationVoucherData(
            numero=numero,
            date=location_date,
            username=username,
            lignes=lignes,
            caution_montant=caution_montant,
            devise=devise,
            entreprise_nom=profile.nom,
            entreprise_adresse=profile.adresse,
            entreprise_telephone=profile.telephone,
            entreprise_email=profile.email,
            entreprise_logo_path=profile.logo_path,
            client_nom=client_nom,
            client_telephone=client_telephone,
            client_adresse=client_adresse,
            client_email=client_email,
            pied_de_page=profile.recu_pied_de_page,
        )

    def build_location_receipt(self, location_id: int) -> LocationReceiptData:
        """Reçu de location (§F), disponible uniquement après le départ —
        voir docstring de module. Les montants proviennent exclusivement de
        ``LocationRetour.montant_facture``, déjà historisés par
        ``LocationService.return_location_line``, jamais recalculés ici."""
        self._permissions.require_permission("LOCATION_VIEW")

        with session_scope(self._settings) as session:
            location = LocationRepository(session).get_by_id(location_id)
            if location is None:
                raise NotFoundError(f"Location {location_id} introuvable.")
            if location.statut not in (StatutLocation.EN_COURS, StatutLocation.RETOURNEE):
                raise ValidationError(
                    "Le reçu de location n'est disponible qu'après le départ de la location."
                )

            numero = location.numero
            location_date = location.date
            date_depart = location.date_depart
            username = location.user.username
            statut = location.statut
            caution_montant = location.caution_montant
            caution_rendue = location.caution_rendue

            lignes = []
            for ligne in location.lignes:
                retours = tuple(
                    LocationReceiptRetour(
                        date_retour=retour.date_retour,
                        quantite=retour.quantite_bon_etat + retour.quantite_immobilisee,
                        jours=max((retour.date_retour - date_depart).days, 1) if date_depart else 1,
                        montant_facture=retour.montant_facture,
                    )
                    for retour in ligne.retours
                )
                lignes.append(
                    LocationReceiptLigne(
                        article_reference=ligne.article.reference,
                        article_designation=ligne.article.designation,
                        tarif_jour=ligne.tarif_jour,
                        retours=retours,
                    )
                )
            total_facture = round_money(sum((l.montant_facture_total for l in lignes), Decimal("0")))

            paiements = tuple(
                LocationReceiptPaymentLine(
                    date_heure=p.date_heure,
                    montant=p.montant,
                    mode_paiement=p.mode_paiement,
                    reference=p.reference,
                    commentaire=p.commentaire,
                    username=p.user.username,
                )
                for p in location.paiements
            )
            montant_paye = round_money(sum((p.montant for p in paiements), Decimal("0")))

            client = location.client
            client_nom = client.nom if client is not None else None
            client_telephone = client.telephone if client is not None else None
            client_adresse = client.adresse if client is not None else None
            client_email = client.email if client is not None else None

        profile = get_company_profile(self._settings)
        devise = get_effective_currency(self._settings)

        return LocationReceiptData(
            numero=numero,
            date=location_date,
            date_depart=date_depart,
            username=username,
            statut=statut,
            lignes=lignes,
            total_facture=total_facture,
            montant_paye=montant_paye,
            paiements=paiements,
            caution_montant=caution_montant,
            caution_rendue=caution_rendue,
            devise=devise,
            entreprise_nom=profile.nom,
            entreprise_adresse=profile.adresse,
            entreprise_telephone=profile.telephone,
            entreprise_email=profile.email,
            entreprise_logo_path=profile.logo_path,
            client_nom=client_nom,
            client_telephone=client_telephone,
            client_adresse=client_adresse,
            client_email=client_email,
            pied_de_page=profile.recu_pied_de_page,
        )
