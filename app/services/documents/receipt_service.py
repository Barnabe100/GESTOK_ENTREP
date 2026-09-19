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
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import time as time_type
from decimal import Decimal
from pathlib import Path
from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.enums import StatutOperation, TypeMouvement
from app.models.movement import MouvementStock
from app.repositories.mouvement_repository import MouvementRepository
from app.repositories.vente_repository import VenteRepository
from app.services.auth.permission_service import PermissionService
from app.services.settings.company_settings_service import get_company_profile, get_effective_currency
from app.utils.exceptions import NotFoundError, ValidationError


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
        )
