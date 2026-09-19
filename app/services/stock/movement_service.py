"""Service de consultation du journal des mouvements de stock, pour la page
dédiée « Mouvements » (§1 de la phase Amélioration fonctionnelle et UX).

Strictement en lecture seule : les mouvements ne sont jamais modifiables ni
supprimables (voir ``app.models.movement.MouvementStock``), donc ce service
n'expose que des méthodes de consultation, jamais d'écriture — seul
``StockService`` écrit dans le journal, au fil des validations d'Entrées/
Sorties/Ventes/Inventaires.

Distinct de ``ReportService.get_movements`` : ce dernier est gated par
``REPORT_VIEW`` (permission partagée par tous les rapports de la page
Rapports). La page Mouvements est un module de consultation à part entière
(§22 du cahier des charges initial), avec sa propre permission dédiée
``STOCK_MOVEMENT_VIEW`` (déjà seedée dans ``app.db.seed`` et déjà mappée à
``FEATURE_STOCK_MOVEMENTS`` dans ``app.services.licensing.permission_map``) :
un rôle disposant de STOCK_MOVEMENT_VIEW sans REPORT_VIEW (ex. Gestionnaire
de stock) doit pouvoir consulter cette page.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.enums import TypeMouvement
from app.repositories.mouvement_repository import MouvementRepository
from app.services.auth.permission_service import PermissionService
from app.services.stock.movement_summary import MouvementSummary


class MovementService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def list_movements(
        self,
        term: str = "",
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        article_id: Optional[int] = None,
        type_mouvement: Optional[TypeMouvement] = None,
        user_id: Optional[int] = None,
    ) -> list[MouvementSummary]:
        self._permissions.require_permission("STOCK_MOVEMENT_VIEW")
        with session_scope(self._settings) as session:
            repo = MouvementRepository(session)
            movements = repo.search(
                term=term,
                date_from=date_from,
                date_to=date_to,
                article_id=article_id,
                type_mouvement=type_mouvement,
                user_id=user_id,
            )
            return [MouvementSummary.from_model(m) for m in movements]
