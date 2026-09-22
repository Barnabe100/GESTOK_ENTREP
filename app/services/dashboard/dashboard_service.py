"""``DashboardService`` : synthèse et visualisation, strictement en lecture
seule (§9 du cahier des charges de cette phase).

Ce service n'écrit jamais en base, n'appelle jamais ``StockService`` ni
aucun service de document, et ne modifie ni ``stock_actuel`` ni le CMUP ni
aucun mouvement/document. Il ne fait qu'agréger des données déjà exposées
par :class:`ReportService` (elle-même déjà garantie lecture seule) et par
quelques méthodes de comptage/somme ciblées ajoutées aux repositories
existants (§8 : agrégations SQL plutôt que charger des lignes complètes
juste pour un total ou un compteur).

Permissions : ``DASHBOARD_VIEW`` donne accès à la page elle-même ; chaque
section respecte en plus la permission qui protège sa source de données
(``ARTICLE_VIEW``/``CATEGORY_VIEW``/``SUPPLIER_VIEW`` pour le catalogue,
``REPORT_VIEW`` pour les rapports agrégés stock/entrées/sorties/inventaires/
mouvements). Un rôle disposant de ``DASHBOARD_VIEW`` sans disposer de la
permission source ne voit simplement pas la section correspondante
(comportement déjà identique à la navigation filtrée de ``MainWindow``),
jamais une erreur qui casserait la page, et jamais une absence de
permission présentée comme une absence de données (voir ``DashboardPage``).
Licence : ``DASHBOARD_VIEW`` est mappée sur la fonctionnalité ``REPORTS``
déjà existante (voir ``permission_map.py``) — aucun nouveau code de licence
n'est introduit.

Indicateurs de ventes (§ lot dédié) : ``REPORT_VIEW`` n'est plus l'unique
porte d'entrée pour les indicateurs propres au domaine Ventes (nombre de
ventes, chiffre d'affaires, évolution des ventes) — un utilisateur disposant
de ``SALE_VIEW`` (ex. le rôle Vendeur, qui n'a pas ``REPORT_VIEW`` par
défaut) y accède également, via ``SaleService.list_sales`` plutôt que
``ReportService.get_sales`` (même filtre, même données, même règle de
consultation globale — voir ``_fetch_period_sales``). ``REPORT_VIEW`` reste
la SEULE voie d'accès aux sections hors du domaine Ventes (stock, entrées,
sorties, inventaires, mouvements, valorisation) : ce lot ne généralise rien
au-delà des indicateurs de ventes explicitement demandés.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.enums import StatutOperation, TypeMouvement
from app.repositories.article_repository import ArticleRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.mouvement_repository import MouvementRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.auth.permission_service import PermissionService
from app.services.reports.report_service import ReportService, StockStateRow
from app.services.sales.sale_service import SaleService, VenteSummary
from app.services.stock.movement_summary import MouvementSummary
from app.utils.exceptions import ValidationError

# Nombre de lignes affichées dans les widgets "top N" du Dashboard — bornes
# volontairement modestes (§10 : lisibilité, pas une liste exhaustive).
DEFAULT_LOW_STOCK_LIMIT = 10
DEFAULT_RECENT_ACTIVITY_LIMIT = 15

# Seuils de granularité pour le graphique d'évolution des ventes (§5.A) :
# période courte -> jour, période moyenne -> semaine, période longue -> mois.
_DAILY_MAX_DAYS = 31
_WEEKLY_MAX_DAYS = 120


def default_period() -> tuple[date, date]:
    """Période par défaut : le mois courant (§4), bornes inclusives, du
    premier jour du mois à aujourd'hui."""
    today = date.today()
    return today.replace(day=1), today


@dataclass(frozen=True)
class CatalogKpis:
    """Indicateurs instantanés du catalogue (§3). Un champ à ``None``
    signifie que l'utilisateur courant n'a pas la permission de consulter
    cette donnée (jamais une valeur à 0 trompeuse)."""

    active_articles: Optional[int]
    active_categories: Optional[int]
    active_suppliers: Optional[int]


@dataclass(frozen=True)
class StockKpis:
    """Indicateurs instantanés de stock (§3), tous dérivés des colonnes déjà
    stockées (``stock_actuel``, ``cout_moyen_pondere``) — aucun recalcul de
    CMUP (§3)."""

    total_value: Decimal
    total_quantity: Decimal
    low_stock_count: int
    out_of_stock_count: int


@dataclass(frozen=True)
class ActivityKpis:
    """Indicateurs sur période (§3-4) : entrées/sorties/ventes/inventaires
    validés sur ``[period_from, period_to]`` (bornes incluses).

    Chaque champ (hors bornes de période) est individuellement ``Optional`` —
    même convention que ``CatalogKpis`` : un champ à ``None`` signifie que
    l'utilisateur courant n'a pas la permission de consulter CETTE donnée
    précise, jamais une valeur à 0 trompeuse. Les indicateurs de ventes
    (``sales_validated``/``sales_amount``) et les autres (entrées, sorties,
    inventaires) ne dépendent pas forcément de la même permission — voir
    ``DashboardService.get_activity_kpis``."""

    period_from: date
    period_to: date
    entries_validated: Optional[int]
    exits_validated: Optional[int]
    sales_validated: Optional[int]
    sales_amount: Optional[Decimal]
    inventories_validated: Optional[int]


@dataclass(frozen=True)
class SalesPoint:
    """Un point du graphique d'évolution des ventes (§5.A)."""

    label: str
    bucket_start: date
    amount: Decimal


@dataclass(frozen=True)
class CategoryStockValue:
    """Une barre du graphique « Valeur du stock par catégorie » (§5.D)."""

    category_nom: str
    valeur_stock: Decimal


@dataclass(frozen=True)
class DashboardOverview:
    """Enveloppe unique retournée par ``get_overview`` : regroupe toutes les
    sections du Dashboard en un seul aller-retour service (§8 : éviter les
    allers-retours multiples pour une page consultée très fréquemment).
    Chaque champ optionnel est ``None`` si la permission source manque."""

    period_from: date
    period_to: date
    catalog: CatalogKpis
    stock: Optional[StockKpis]
    activity: ActivityKpis
    sales_evolution: Optional[list[SalesPoint]]
    movement_breakdown: Optional[dict[TypeMouvement, int]]
    low_stock_top: Optional[list[StockStateRow]]
    stock_value_by_category: Optional[list[CategoryStockValue]]
    recent_activity: Optional[list[MouvementSummary]]


class DashboardService:
    def __init__(
        self,
        permission_service: PermissionService,
        report_service: ReportService,
        sale_service: SaleService,
        settings: Optional[Settings] = None,
    ) -> None:
        self._permissions = permission_service
        self._reports = report_service
        self._sales = sale_service
        self._settings = settings

    def _require_dashboard(self) -> None:
        self._permissions.require_permission("DASHBOARD_VIEW")

    def _has_report_access(self) -> bool:
        return self._permissions.has_permission("REPORT_VIEW")

    def _has_sales_domain_access(self) -> bool:
        """Les indicateurs du domaine Ventes sont accessibles via ``SALE_VIEW``
        OU ``REPORT_VIEW`` (l'un ou l'autre suffit) — jamais une régression
        pour un rôle qui n'avait que ``REPORT_VIEW`` jusqu'ici (Gestionnaire
        de stock, qui n'a pas ``SALE_VIEW``)."""
        return self._permissions.has_permission("SALE_VIEW") or self._has_report_access()

    def _fetch_period_sales(self, period_from: date, period_to: date) -> list[VenteSummary]:
        """Ventes VALIDEE sur la période, quelle que soit la permission qui a
        ouvert l'accès (voir ``_has_sales_domain_access``) : source choisie
        selon la permission RÉELLEMENT détenue par l'utilisateur courant,
        jamais un appel qui échouerait silencieusement.

        ``SaleService.list_sales`` (``SALE_VIEW``) et ``ReportService.get_sales``
        (``REPORT_VIEW``) interrogent tous deux ``VenteRepository.search``
        avec le même filtre — mêmes données, jamais de divergence — et
        aucun des deux ne filtre par propriétaire (consultation globale des
        ventes, § lot propriété Vendeur, jamais remise en cause ici)."""
        if self._permissions.has_permission("SALE_VIEW"):
            return self._sales.list_sales(date_from=period_from, date_to=period_to, statut=StatutOperation.VALIDEE)
        return self._reports.get_sales(date_from=period_from, date_to=period_to, statut=StatutOperation.VALIDEE)

    def _validate_period(self, period_from: date, period_to: date) -> None:
        """``date_debut <= date_fin <= aujourd'hui`` (§ lot dates) — vérifié
        côté service indépendamment de l'UI (défense en profondeur, même
        principe que ``validate_not_future_date`` ailleurs dans
        l'application) : aucune requête n'est jamais lancée pour une période
        incohérente, quel que soit l'appelant."""
        today = date.today()
        if period_from > period_to:
            raise ValidationError("La date de début ne peut pas être postérieure à la date de fin.")
        if period_from > today:
            raise ValidationError("La date de début ne peut pas être postérieure à aujourd'hui.")
        if period_to > today:
            raise ValidationError("La date de fin ne peut pas être postérieure à aujourd'hui.")

    # -- catalogue (§3) -----------------------------------------------------------

    def get_catalog_kpis(self) -> CatalogKpis:
        self._require_dashboard()
        with session_scope(self._settings) as session:
            active_articles = (
                ArticleRepository(session).count_active() if self._permissions.has_permission("ARTICLE_VIEW") else None
            )
            active_categories = (
                CategoryRepository(session).count_active() if self._permissions.has_permission("CATEGORY_VIEW") else None
            )
            active_suppliers = (
                SupplierRepository(session).count_active() if self._permissions.has_permission("SUPPLIER_VIEW") else None
            )
        return CatalogKpis(active_articles, active_categories, active_suppliers)

    # -- stock (§3, instantané) ----------------------------------------------------

    def get_stock_kpis(self) -> Optional[StockKpis]:
        """``None`` si l'utilisateur n'a pas ``REPORT_VIEW`` — jamais une
        exception qui interromprait le chargement du reste du Dashboard."""
        self._require_dashboard()
        if not self._has_report_access():
            return None
        with session_scope(self._settings) as session:
            repo = ArticleRepository(session)
            return StockKpis(
                total_value=repo.sum_stock_value(include_inactive=False),
                total_quantity=repo.sum_stock_quantity(include_inactive=False),
                low_stock_count=repo.count_low_stock(),
                out_of_stock_count=repo.count_out_of_stock(),
            )

    def get_stock_value_by_category(self) -> Optional[list[CategoryStockValue]]:
        self._require_dashboard()
        if not self._has_report_access():
            return None
        with session_scope(self._settings) as session:
            rows = ArticleRepository(session).sum_stock_value_by_category(include_inactive=False)
        return [CategoryStockValue(category_nom=nom, valeur_stock=value) for nom, value in rows]

    def get_low_stock_top(self, limit: int = DEFAULT_LOW_STOCK_LIMIT) -> Optional[list[StockStateRow]]:
        """Réutilise ``ReportService.get_low_stock`` (déjà filtré en SQL) —
        le tri par sévérité (le plus grand déficit d'abord) et la limite se
        font en Python sur ce sous-ensemble déjà restreint, jamais sur le
        catalogue entier."""
        self._require_dashboard()
        if not self._has_report_access():
            return None
        rows = self._reports.get_low_stock()
        rows.sort(key=lambda r: (r.stock_actuel - r.stock_min, r.stock_actuel))
        return rows[:limit]

    # -- activité sur période (§3-4) ------------------------------------------------

    def get_activity_kpis(self, period_from: date, period_to: date) -> ActivityKpis:
        """Toujours retourné (jamais ``None`` dans son ensemble, ``DASHBOARD_VIEW``
        suffit à construire l'objet) — chaque champ est individuellement
        ``None`` si sa permission source manque, jamais une donnée à 0
        trompeuse (voir docstring de ``ActivityKpis``)."""
        self._require_dashboard()
        self._validate_period(period_from, period_to)

        entries_validated: Optional[int] = None
        exits_validated: Optional[int] = None
        inventories_validated: Optional[int] = None
        if self._has_report_access():
            entries = self._reports.get_entries(date_from=period_from, date_to=period_to, statut=StatutOperation.VALIDEE)
            exits = self._reports.get_exits(date_from=period_from, date_to=period_to, statut=StatutOperation.VALIDEE)
            entries_validated = len(entries)
            exits_validated = len(exits)
            inventories_validated = sum(
                1 for i in self._reports.get_inventories(date_from=period_from, date_to=period_to)
                if i.statut.value == "VALIDE"
            )

        sales_validated: Optional[int] = None
        sales_amount: Optional[Decimal] = None
        if self._has_sales_domain_access():
            sales = self._fetch_period_sales(period_from, period_to)
            sales_validated = len(sales)
            sales_amount = sum((v.total for v in sales), Decimal("0"))

        return ActivityKpis(
            period_from=period_from, period_to=period_to,
            entries_validated=entries_validated, exits_validated=exits_validated,
            sales_validated=sales_validated, sales_amount=sales_amount,
            inventories_validated=inventories_validated,
        )

    def get_sales_evolution(self, period_from: date, period_to: date) -> Optional[list[SalesPoint]]:
        """Montant des ventes validées, agrégé par jour/semaine/mois selon la
        durée de la période (§5.A) — granularité la plus fine restant
        lisible, jamais une centaine de points sur un graphique."""
        self._require_dashboard()
        self._validate_period(period_from, period_to)
        if not self._has_sales_domain_access():
            return None

        sales = self._fetch_period_sales(period_from, period_to)
        granularity = _pick_granularity(period_from, period_to)

        buckets: dict[date, Decimal] = {}
        for vente in sales:
            bucket_start = _bucket_start(vente.date, granularity)
            buckets[bucket_start] = buckets.get(bucket_start, Decimal("0")) + vente.total

        return [
            SalesPoint(label=_bucket_label(bucket_start, granularity), bucket_start=bucket_start, amount=amount)
            for bucket_start, amount in sorted(buckets.items())
        ]

    def get_movement_breakdown(self, period_from: date, period_to: date) -> Optional[dict[TypeMouvement, int]]:
        """Nombre de mouvements par type sur la période (§5.B) — inclut
        uniquement les types réellement présents dans les données (jamais de
        type inventé à zéro)."""
        self._require_dashboard()
        self._validate_period(period_from, period_to)
        if not self._has_report_access():
            return None

        movements = self._reports.get_movements(date_from=period_from, date_to=period_to)
        counts = Counter(m.type for m in movements)
        return dict(counts)

    def get_recent_activity(self, limit: int = DEFAULT_RECENT_ACTIVITY_LIMIT) -> Optional[list[MouvementSummary]]:
        """Les derniers mouvements de stock, tous types confondus (§6) — le
        journal des mouvements est déjà la trace unifiée de toute opération
        ayant affecté le stock (entrées/sorties/ventes/inventaires/
        annulations), réutilisée telle quelle plutôt que de fusionner cinq
        historiques de documents différents."""
        self._require_dashboard()
        if not self._has_report_access():
            return None
        with session_scope(self._settings) as session:
            movements = MouvementRepository(session).list_recent(limit)
            return [MouvementSummary.from_model(m) for m in movements]

    # -- vue d'ensemble -------------------------------------------------------------

    def get_overview(
        self, period_from: Optional[date] = None, period_to: Optional[date] = None,
        low_stock_limit: int = DEFAULT_LOW_STOCK_LIMIT, recent_activity_limit: int = DEFAULT_RECENT_ACTIVITY_LIMIT,
    ) -> DashboardOverview:
        self._require_dashboard()
        if period_from is None or period_to is None:
            period_from, period_to = default_period()
        else:
            self._validate_period(period_from, period_to)

        return DashboardOverview(
            period_from=period_from, period_to=period_to,
            catalog=self.get_catalog_kpis(),
            stock=self.get_stock_kpis(),
            activity=self.get_activity_kpis(period_from, period_to),
            sales_evolution=self.get_sales_evolution(period_from, period_to),
            movement_breakdown=self.get_movement_breakdown(period_from, period_to),
            low_stock_top=self.get_low_stock_top(low_stock_limit),
            stock_value_by_category=self.get_stock_value_by_category(),
            recent_activity=self.get_recent_activity(recent_activity_limit),
        )


def _pick_granularity(period_from: date, period_to: date) -> str:
    days = (period_to - period_from).days + 1
    if days <= _DAILY_MAX_DAYS:
        return "day"
    if days <= _WEEKLY_MAX_DAYS:
        return "week"
    return "month"


def _bucket_start(d: date, granularity: str) -> date:
    if granularity == "day":
        return d
    if granularity == "week":
        return d - timedelta(days=d.weekday())  # lundi de la semaine ISO
    return d.replace(day=1)


def _bucket_label(bucket_start: date, granularity: str) -> str:
    if granularity == "day":
        return bucket_start.isoformat()
    if granularity == "week":
        return f"Semaine du {bucket_start.isoformat()}"
    return bucket_start.strftime("%Y-%m")
