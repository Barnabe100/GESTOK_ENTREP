"""Accès aux données pour les articles.

Seule cette classe construit des requêtes SQLAlchemy sur ``articles`` ;
:class:`ArticleService` n'y accède jamais directement (architecture
View -> Service -> Repository -> Model), à l'identique des modules
Catégories, Fournisseurs et Motifs de sortie.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import Article, Category
from app.models.enums import StatutActifInactif
from app.repositories.base import SQLAlchemyRepository
from app.utils.money import round_money


class ArticleRepository(SQLAlchemyRepository[Article]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Article)

    def find_by_reference(self, reference: str, exclude_id: Optional[int] = None) -> Optional[Article]:
        query = self.session.query(Article).filter(Article.reference == reference)
        if exclude_id is not None:
            query = query.filter(Article.id != exclude_id)
        return query.one_or_none()

    def find_by_barcode(
        self, code_barres: str, exclude_id: Optional[int] = None, active_only: bool = False
    ) -> Optional[Article]:
        """``active_only`` restreint la recherche aux articles actifs — seule
        la contrainte d'unicité porte sur ce périmètre (voir migration 0008 :
        un article désactivé peut conserver un code-barres repris par un
        nouvel article actif, sans jamais entrer en conflit)."""
        query = self.session.query(Article).filter(Article.code_barres == code_barres)
        if exclude_id is not None:
            query = query.filter(Article.id != exclude_id)
        if active_only:
            query = query.filter(Article.statut == StatutActifInactif.ACTIF)
        return query.one_or_none()

    def search(
        self,
        term: str = "",
        category_id: Optional[int] = None,
        include_inactive: bool = True,
        low_stock_only: bool = False,
        out_of_stock_only: bool = False,
    ) -> list[Article]:
        # eager-load category/fournisseur_principal : évite le N+1 lorsque
        # l'appelant (ex. les rapports État du stock/Valorisation) parcourt
        # potentiellement des centaines d'articles pour construire ses lignes.
        query = (
            self.session.query(Article)
            .join(Article.category)
            .options(joinedload(Article.category), joinedload(Article.fournisseur_principal))
        )
        if term:
            like_term = f"%{term}%"
            query = query.filter(
                or_(
                    Article.reference.ilike(like_term),
                    Article.designation.ilike(like_term),
                    Category.nom.ilike(like_term),
                    Article.code_barres.ilike(like_term),
                )
            )
        if category_id is not None:
            query = query.filter(Article.category_id == category_id)
        if not include_inactive:
            query = query.filter(Article.statut == StatutActifInactif.ACTIF)
        if low_stock_only:
            query = query.filter(Article.stock_actuel <= Article.stock_min)
        if out_of_stock_only:
            query = query.filter(Article.stock_actuel == Decimal("0"))
        return query.order_by(Article.reference).all()

    # -- agrégations ciblées pour le Dashboard (§8 : COUNT/SUM en SQL plutôt
    #    que charger des objets complets juste pour un total ou un compteur) --

    def count_active(self) -> int:
        return (
            self.session.query(func.count(Article.id))
            .filter(Article.statut == StatutActifInactif.ACTIF)
            .scalar() or 0
        )

    def count_low_stock(self) -> int:
        return (
            self.session.query(func.count(Article.id))
            .filter(Article.statut == StatutActifInactif.ACTIF, Article.stock_actuel <= Article.stock_min)
            .scalar() or 0
        )

    def count_out_of_stock(self) -> int:
        return (
            self.session.query(func.count(Article.id))
            .filter(Article.statut == StatutActifInactif.ACTIF, Article.stock_actuel == Decimal("0"))
            .scalar() or 0
        )

    def sum_stock_value(self, include_inactive: bool = False) -> Decimal:
        """``somme(stock_actuel × CMUP)`` sur les colonnes déjà stockées —
        strictement la même formule que ``ReportService.StockStateRow``,
        jamais un nouveau calcul de CMUP. Ne charge que les deux colonnes
        nécessaires (pas les entités ``Article`` complètes avec leurs
        relations) ; la somme est faite en Python avec ``Decimal`` plutôt
        qu'en SQL (SQLite n'a pas d'arithmétique décimale exacte — un
        ``SUM`` SQL sur ces colonnes utiliserait une arithmétique flottante,
        inacceptable pour un montant financier)."""
        query = self.session.query(Article.stock_actuel, Article.cout_moyen_pondere)
        if not include_inactive:
            query = query.filter(Article.statut == StatutActifInactif.ACTIF)
        total = sum((stock * cmup for stock, cmup in query), Decimal("0"))
        return round_money(total)

    def sum_stock_quantity(self, include_inactive: bool = False) -> Decimal:
        query = self.session.query(Article.stock_actuel)
        if not include_inactive:
            query = query.filter(Article.statut == StatutActifInactif.ACTIF)
        return sum((row[0] for row in query), Decimal("0"))

    def sum_stock_value_by_category(self, include_inactive: bool = False) -> list[tuple[str, Decimal]]:
        """Valeur du stock groupée par catégorie (§5.D), triée par valeur
        décroissante. Requête ciblée (3 colonnes, jointure catégorie
        uniquement) plutôt que la construction complète des lignes de
        valorisation ; somme en Python en ``Decimal`` pour la même raison
        que ``sum_stock_value``."""
        query = self.session.query(Category.nom, Article.stock_actuel, Article.cout_moyen_pondere).join(
            Article.category
        )
        if not include_inactive:
            query = query.filter(Article.statut == StatutActifInactif.ACTIF)

        totals: dict[str, Decimal] = {}
        for category_nom, stock, cmup in query:
            totals[category_nom] = totals.get(category_nom, Decimal("0")) + stock * cmup

        rows = [(nom, round_money(value)) for nom, value in totals.items()]
        rows.sort(key=lambda row: row[1], reverse=True)
        return rows
