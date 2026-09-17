"""Rapports de consultation : état du stock, stock faible, ruptures,
mouvements, entrées, sorties, ventes, inventaires, valorisation.

Principe fondamental (§2 du cahier des charges de cette phase) : ce service
est **strictement en lecture seule**. Il n'appelle jamais ``StockService``,
n'ouvre jamais une session en écriture au sens métier, et ne modifie jamais
``article.stock_actuel``, le CMUP, ni aucun document (Entrée/Sortie/Vente/
Inventaire). Chaque méthode se contente d'assembler, via les repositories
déjà existants, des vues de consultation à partir des données déjà produites
par les moteurs métier (StockService pour les mouvements/CMUP, chaque
service de document pour son propre historique).

Aucune règle de calcul du moteur de stock n'est dupliquée ici :
- le CMUP affiché est celui déjà enregistré sur l'article
  (``Article.cout_moyen_pondere``, calculé par ``StockService``) ;
- le prix facturé d'une vente est celui déjà historisé sur
  ``VenteLigne.prix_unitaire`` (jamais recalculé à partir du prix catalogue
  actuel de l'article — réutilise directement ``VenteSummary``, qui porte
  déjà cette garantie depuis la phase Ventes) ;
- le coût unitaire d'un mouvement est celui déjà enregistré sur
  ``MouvementStock.cout_unitaire``.
Ce service ne fait qu'un seul calcul complémentaire, en lecture seule et
documenté : ``valeur_stock = stock_actuel × CMUP`` (voir
:class:`StockStateRow` et :class:`ValorisationReport`).

Contrairement aux autres services métier, ce service n'appelle jamais les
services de document (``EntryService``, ``ExitService``, ``SaleService``,
``InventoryService``) : il accède directement à leurs repositories, pour ne
dépendre que de la permission ``REPORT_VIEW`` — un rôle disposant de
``REPORT_VIEW`` sans disposer de ``STOCK_ENTRY_VIEW``/``SALE_VIEW``/etc.
(ex. Consultation) doit tout de même pouvoir consulter les rapports
correspondants. Réutilise néanmoins telles quelles les DTO déjà définies par
ces modules (``EntreeSummary``, ``SortieSummary``, ``VenteSummary``,
``InventaireSummary``, ``MouvementSummary``) pour ne dupliquer aucune
logique de projection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence, Union

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import Article
from app.models.enums import StatutInventaire, StatutOperation, TypeMouvement
from app.repositories.article_repository import ArticleRepository
from app.repositories.entree_repository import EntreeRepository
from app.repositories.inventaire_repository import InventaireRepository
from app.repositories.mouvement_repository import MouvementRepository
from app.repositories.sortie_repository import SortieRepository
from app.repositories.vente_repository import VenteRepository
from app.services.auth.permission_service import PermissionService
from app.services.entries.entry_service import EntreeSummary
from app.services.exits.exit_service import SortieSummary
from app.services.inventory.inventory_service import InventaireSummary
from app.services.sales.sale_service import VenteSummary
from app.services.stock.movement_summary import MouvementSummary
from app.utils.csv_export import export_rows_to_csv
from app.utils.money import round_money


@dataclass(frozen=True)
class StockStateRow:
    """Ligne du rapport État du stock (réutilisée aussi par Stock faible,
    Ruptures et Valorisation, qui n'en sont que des filtres/agrégats)."""

    article_id: int
    reference: str
    designation: str
    category_nom: str
    fournisseur_nom: Optional[str]
    unite: str
    stock_actuel: Decimal
    stock_min: Decimal
    stock_max: Optional[Decimal]
    cout_moyen_pondere: Decimal
    valeur_stock: Decimal
    actif: bool

    @classmethod
    def from_model(cls, article: Article) -> "StockStateRow":
        return cls(
            article_id=article.id,
            reference=article.reference,
            designation=article.designation,
            category_nom=article.category.nom,
            fournisseur_nom=article.fournisseur_principal.nom if article.fournisseur_principal else None,
            unite=article.unite,
            stock_actuel=article.stock_actuel,
            stock_min=article.stock_min,
            stock_max=article.stock_max,
            cout_moyen_pondere=article.cout_moyen_pondere,
            # Seul calcul complémentaire de ce module (§3.I) : le CMUP utilisé
            # est celui déjà calculé par StockService, jamais recalculé ici.
            valeur_stock=round_money(article.stock_actuel * article.cout_moyen_pondere),
            actif=article.statut.value == "ACTIF",
        )


@dataclass(frozen=True)
class ValorisationReport:
    """Rapport de valorisation du stock : lignes + total général."""

    rows: list[StockStateRow]
    total: Decimal


@dataclass(frozen=True)
class InventoryReportRow:
    """Ligne du rapport Inventaires : résumé agrégé d'un inventaire (le
    détail ligne-à-ligne reste consultable via ``InventoryService``/
    ``InventoryDetailDialog``, déjà construits en phase précédente)."""

    id: int
    numero: str
    date: date
    username: str
    statut: StatutInventaire
    nombre_lignes: int
    nombre_ecarts_positifs: int
    nombre_ecarts_negatifs: int
    quantite_totale_ajustee: Decimal

    @classmethod
    def from_summary(cls, inventaire: InventaireSummary) -> "InventoryReportRow":
        positifs = sum(1 for l in inventaire.lignes if l.ecart > 0)
        negatifs = sum(1 for l in inventaire.lignes if l.ecart < 0)
        # Volume total corrigé, en valeur absolue (une hausse de 5 et une
        # baisse de 3 comptent pour 8, pas pour un solde net de 2) : reflète
        # l'ampleur réelle du travail de comptage, pas seulement son solde.
        quantite_totale = sum((abs(l.ecart) for l in inventaire.lignes), Decimal("0"))
        return cls(
            id=inventaire.id,
            numero=inventaire.numero,
            date=inventaire.date,
            username=inventaire.username,
            statut=inventaire.statut,
            nombre_lignes=len(inventaire.lignes),
            nombre_ecarts_positifs=positifs,
            nombre_ecarts_negatifs=negatifs,
            quantite_totale_ajustee=quantite_totale,
        )


class ReportService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _require_view(self) -> None:
        self._permissions.require_permission("REPORT_VIEW")

    # -- A. État du stock / B. Stock faible / C. Rupture -------------------------

    def get_stock_state(
        self, search: str = "", category_id: Optional[int] = None, include_inactive: bool = False
    ) -> list[StockStateRow]:
        self._require_view()
        with session_scope(self._settings) as session:
            repo = ArticleRepository(session)
            articles = repo.search(search, category_id=category_id, include_inactive=include_inactive)
            return [StockStateRow.from_model(a) for a in articles]

    def get_low_stock(self, search: str = "", category_id: Optional[int] = None) -> list[StockStateRow]:
        """Articles dont ``stock_actuel <= stock_min`` (§3.B) — un article en
        rupture avec ``stock_min > 0`` y apparaît donc également, sans que ce
        soit une confusion : c'est le comportement attendu (§3.C)."""
        self._require_view()
        with session_scope(self._settings) as session:
            repo = ArticleRepository(session)
            articles = repo.search(search, category_id=category_id, include_inactive=False, low_stock_only=True)
            return [StockStateRow.from_model(a) for a in articles]

    def get_out_of_stock(self, search: str = "", category_id: Optional[int] = None) -> list[StockStateRow]:
        """Articles dont ``stock_actuel == 0`` (§3.C), distinct du rapport
        Stock faible (``stock_actuel <= stock_min``, qui peut être > 0)."""
        self._require_view()
        with session_scope(self._settings) as session:
            repo = ArticleRepository(session)
            articles = repo.search(search, category_id=category_id, include_inactive=False, out_of_stock_only=True)
            return [StockStateRow.from_model(a) for a in articles]

    # -- I. Valorisation -----------------------------------------------------------

    def get_valorisation(
        self, search: str = "", category_id: Optional[int] = None, include_inactive: bool = False
    ) -> ValorisationReport:
        """``valeur_stock = stock_actuel × CMUP`` par article, et
        ``total = somme(valeur_stock)`` sur l'ensemble filtré (§3.I)."""
        self._require_view()
        with session_scope(self._settings) as session:
            repo = ArticleRepository(session)
            articles = repo.search(search, category_id=category_id, include_inactive=include_inactive)
            rows = [StockStateRow.from_model(a) for a in articles]
            total = round_money(sum((row.valeur_stock for row in rows), Decimal("0")))
            return ValorisationReport(rows=rows, total=total)

    # -- D. Mouvements de stock ------------------------------------------------------

    def get_movements(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        article_id: Optional[int] = None,
        type_mouvement: Optional[TypeMouvement] = None,
        user_id: Optional[int] = None,
    ) -> list[MouvementSummary]:
        self._require_view()
        with session_scope(self._settings) as session:
            repo = MouvementRepository(session)
            movements = repo.search(
                date_from=date_from, date_to=date_to, article_id=article_id,
                type_mouvement=type_mouvement, user_id=user_id,
            )
            return [MouvementSummary.from_model(m) for m in movements]

    # -- E. Entrées ------------------------------------------------------------------

    def get_entries(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        statut: Optional[StatutOperation] = None,
    ) -> list[EntreeSummary]:
        self._require_view()
        with session_scope(self._settings) as session:
            repo = EntreeRepository(session)
            entrees = repo.search(date_from=date_from, date_to=date_to, statut=statut)
            return [EntreeSummary.from_model(e) for e in entrees]

    # -- F. Sorties ------------------------------------------------------------------

    def get_exits(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        motif_id: Optional[int] = None,
        statut: Optional[StatutOperation] = None,
    ) -> list[SortieSummary]:
        self._require_view()
        with session_scope(self._settings) as session:
            repo = SortieRepository(session)
            sorties = repo.search(motif_id=motif_id, statut=statut, date_from=date_from, date_to=date_to)
            return [SortieSummary.from_model(s) for s in sorties]

    # -- G. Ventes -------------------------------------------------------------------

    def get_sales(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        statut: Optional[StatutOperation] = None,
    ) -> list[VenteSummary]:
        """Le montant de chaque vente (``VenteSummary.total``) est calculé à
        partir de ``VenteLigne.prix_unitaire`` historisé — jamais du prix
        catalogue actuel de l'article (garantie déjà portée par
        ``VenteSummary``/``SaleService`` depuis la phase Ventes, réutilisée
        ici telle quelle, §3.G du cahier des charges de cette phase)."""
        self._require_view()
        with session_scope(self._settings) as session:
            repo = VenteRepository(session)
            ventes = repo.search(date_from=date_from, date_to=date_to, statut=statut)
            return [VenteSummary.from_model(v) for v in ventes]

    # -- H. Inventaires --------------------------------------------------------------

    def get_inventories(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        statut: Optional[StatutInventaire] = None,
    ) -> list[InventoryReportRow]:
        self._require_view()
        with session_scope(self._settings) as session:
            repo = InventaireRepository(session)
            inventaires = repo.search(date_from=date_from, date_to=date_to, statut=statut)
            return [InventoryReportRow.from_summary(InventaireSummary.from_model(i)) for i in inventaires]

    # -- export ------------------------------------------------------------------------

    def export_to_csv(
        self, file_path: Union[str, Path], headers: Sequence[str], rows: Sequence[Sequence[str]]
    ) -> None:
        """Export CSV d'un rapport déjà construit (en-têtes/lignes fournies
        par l'appelant, déjà formatées pour l'affichage). Permission dédiée
        ``REPORT_EXPORT`` (§9), distincte de ``REPORT_VIEW`` : un rôle peut
        consulter les rapports sans pouvoir les exporter (ex. Consultation)."""
        self._permissions.require_permission("REPORT_EXPORT")
        export_rows_to_csv(file_path, headers, rows)
