"""Gestion des articles : consultation, recherche, filtres, création,
modification, activation/désactivation.

Point critique (cahier des charges de cette phase, §7-9) : ni le stock
actuel ni le CMUP ne sont modifiables via ce service en dehors de leur
initialisation contrôlée à la création. ``update_article`` n'expose
délibérément aucun paramètre ``stock_actuel``/``cout_moyen_pondere`` — toute
variation ultérieure de ces deux valeurs ne pourra provenir que d'une
opération de stock tracée (StockService, phases ultérieures : entrées,
sorties, ventes, ajustements d'inventaire).

Mêmes principes que Catégories/Fournisseurs/Motifs de sortie : aucune
suppression physique, un article désactivé reste consultable (historique
préservé) mais ne doit plus être proposé pour une nouvelle opération — voir
``list_articles(..., include_inactive=False)``.

Une catégorie ou un fournisseur ne peuvent être choisis pour un article que
s'ils sont actifs au moment de la sélection ; un article déjà associé à une
catégorie ou un fournisseur devenu inactif conserve cette association tant
qu'elle n'est pas explicitement changée (voir ``update_article``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.catalog import Article
from app.models.enums import ResultatAudit, StatutActifInactif, TypeMouvement
from app.models.movement import MouvementStock
from app.repositories.article_repository import ArticleRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.articles")

MAX_REFERENCE_LENGTH = 50
MAX_DESIGNATION_LENGTH = 255
MAX_UNITE_LENGTH = 20
MAX_EMPLACEMENT_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 1000
MAX_BARCODE_LENGTH = 50

# Sentinel distinguant « champ non fourni » (conserver la valeur actuelle lors
# d'une modification) de ``None``/chaîne vide (effacer explicitement le
# champ) — voir SupplierService pour le même principe.
_UNSET = object()


@dataclass(frozen=True)
class ArticleSummary:
    """Vue en lecture seule d'un article."""

    id: int
    reference: str
    designation: str
    category_id: int
    category_nom: str
    fournisseur_principal_id: Optional[int]
    fournisseur_principal_nom: Optional[str]
    unite: str
    prix_achat: Decimal
    prix_vente: Decimal
    cout_moyen_pondere: Decimal
    stock_actuel: Decimal
    stock_min: Decimal
    stock_max: Optional[Decimal]
    emplacement: Optional[str]
    description: Optional[str]
    code_barres: Optional[str]
    actif: bool
    date_creation: datetime
    date_modification: datetime

    @property
    def en_rupture(self) -> bool:
        return self.stock_actuel <= Decimal("0")

    @property
    def stock_faible(self) -> bool:
        """Vrai si le stock est au niveau ou en-dessous du seuil minimum
        (mais pas en rupture, déjà signalée séparément)."""
        return not self.en_rupture and self.stock_actuel <= self.stock_min

    @classmethod
    def from_model(cls, article: Article) -> "ArticleSummary":
        return cls(
            id=article.id,
            reference=article.reference,
            designation=article.designation,
            category_id=article.category_id,
            category_nom=article.category.nom,
            fournisseur_principal_id=article.fournisseur_principal_id,
            fournisseur_principal_nom=(
                article.fournisseur_principal.nom if article.fournisseur_principal else None
            ),
            unite=article.unite,
            prix_achat=article.prix_achat_defaut,
            prix_vente=article.prix_vente,
            cout_moyen_pondere=article.cout_moyen_pondere,
            stock_actuel=article.stock_actuel,
            stock_min=article.stock_min,
            stock_max=article.stock_max,
            emplacement=article.emplacement,
            description=article.description,
            code_barres=article.code_barres,
            actif=article.statut == StatutActifInactif.ACTIF,
            date_creation=article.date_creation,
            date_modification=article.date_modification,
        )


def _validate_text(value: str, field_label: str, max_length: int) -> str:
    value = (value or "").strip()
    if not value:
        raise ValidationError(f"Le champ « {field_label} » est obligatoire.")
    if len(value) > max_length:
        raise ValidationError(f"Le champ « {field_label} » ne doit pas dépasser {max_length} caractères.")
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


def _validate_money(value: Decimal, field_label: str) -> Decimal:
    if value < 0:
        raise ValidationError(f"Le champ « {field_label} » ne peut pas être négatif.")
    return value


def _validate_quantity(value: Decimal, field_label: str) -> Decimal:
    if value < 0:
        raise ValidationError(f"Le champ « {field_label} » ne peut pas être négatif.")
    return value


def _validate_optional_quantity(value: Optional[Decimal], field_label: str) -> Optional[Decimal]:
    if value is None:
        return None
    return _validate_quantity(value, field_label)


class ArticleService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, session, action: str, article_id: Optional[int]) -> None:
        session.add(
            AuditLog(
                user_id=self._acting_user_id(),
                action=action,
                entite="articles",
                entite_id=article_id,
                resultat=ResultatAudit.SUCCES,
            )
        )

    def list_articles(
        self,
        search: str = "",
        category_id: Optional[int] = None,
        include_inactive: bool = True,
        low_stock_only: bool = False,
    ) -> list[ArticleSummary]:
        self._permissions.require_permission("ARTICLE_VIEW")
        with session_scope(self._settings) as session:
            repo = ArticleRepository(session)
            articles = repo.search(
                search, category_id=category_id, include_inactive=include_inactive, low_stock_only=low_stock_only
            )
            return [ArticleSummary.from_model(a) for a in articles]

    def get_article(self, article_id: int) -> ArticleSummary:
        self._permissions.require_permission("ARTICLE_VIEW")
        with session_scope(self._settings) as session:
            repo = ArticleRepository(session)
            article = repo.get_by_id(article_id)
            if article is None:
                raise NotFoundError(f"Article {article_id} introuvable.")
            return ArticleSummary.from_model(article)

    def create_article(
        self,
        reference: str,
        designation: str,
        category_id: int,
        unite: str,
        prix_achat: Decimal,
        prix_vente: Decimal,
        stock_min: Decimal,
        *,
        fournisseur_principal_id: Optional[int] = None,
        stock_max: Optional[Decimal] = None,
        emplacement: Optional[str] = None,
        description: Optional[str] = None,
        code_barres: Optional[str] = None,
        stock_initial: Decimal = Decimal("0"),
    ) -> ArticleSummary:
        """Crée un article. ``stock_initial`` n'est pas une écriture directe du
        stock : s'il est positif, un mouvement d'ajustement traçable est créé
        dans la même transaction (voir §9 du cahier des charges de cette
        phase) et le CMUP initial est fixé au prix d'achat renseigné, en
        l'absence de tout historique."""
        self._permissions.require_permission("ARTICLE_CREATE")

        reference = _validate_text(reference, "référence", MAX_REFERENCE_LENGTH)
        designation = _validate_text(designation, "désignation", MAX_DESIGNATION_LENGTH)
        unite = _validate_text(unite, "unité", MAX_UNITE_LENGTH)
        prix_achat = _validate_money(prix_achat, "prix d'achat")
        prix_vente = _validate_money(prix_vente, "prix de vente")
        stock_min = _validate_quantity(stock_min, "stock minimum")
        stock_max = _validate_optional_quantity(stock_max, "stock maximum")
        if stock_max is not None and stock_max < stock_min:
            raise ValidationError("Le stock maximum doit être supérieur ou égal au stock minimum.")
        emplacement = _validate_optional_text(emplacement, "emplacement", MAX_EMPLACEMENT_LENGTH)
        description = _validate_optional_text(description, "description", MAX_DESCRIPTION_LENGTH)
        code_barres = _validate_optional_text(code_barres, "code-barres", MAX_BARCODE_LENGTH)
        stock_initial = _validate_quantity(stock_initial, "stock initial")

        acting_user_id = self._acting_user_id()

        with session_scope(self._settings) as session:
            article_repo = ArticleRepository(session)
            category_repo = CategoryRepository(session)
            supplier_repo = SupplierRepository(session)

            if article_repo.find_by_reference(reference) is not None:
                raise ConflictError(f"La référence « {reference} » est déjà utilisée.")
            if code_barres is not None and article_repo.find_by_barcode(code_barres) is not None:
                raise ConflictError(f"Le code-barres « {code_barres} » est déjà utilisé.")

            category = category_repo.get_by_id(category_id)
            if category is None:
                raise NotFoundError(f"Catégorie {category_id} introuvable.")
            if category.statut != StatutActifInactif.ACTIF:
                raise ValidationError("La catégorie sélectionnée est inactive.")

            if fournisseur_principal_id is not None:
                supplier = supplier_repo.get_by_id(fournisseur_principal_id)
                if supplier is None:
                    raise NotFoundError(f"Fournisseur {fournisseur_principal_id} introuvable.")
                if supplier.statut != StatutActifInactif.ACTIF:
                    raise ValidationError("Le fournisseur sélectionné est inactif.")

            article = Article(
                reference=reference,
                designation=designation,
                category_id=category_id,
                unite=unite,
                fournisseur_principal_id=fournisseur_principal_id,
                prix_achat_defaut=prix_achat,
                prix_vente=prix_vente,
                # Règle métier retenue : en l'absence de tout historique d'entrée,
                # le CMUP initial est égal au prix d'achat renseigné à la création.
                cout_moyen_pondere=prix_achat,
                stock_actuel=stock_initial,
                stock_min=stock_min,
                stock_max=stock_max,
                emplacement=emplacement,
                description=description,
                code_barres=code_barres,
                statut=StatutActifInactif.ACTIF,
            )
            session.add(article)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError(
                    f"La référence « {reference} » ou le code-barres est déjà utilisé."
                ) from exc

            if stock_initial > 0:
                session.add(
                    MouvementStock(
                        article_id=article.id,
                        type=TypeMouvement.AJUSTEMENT,
                        quantite=stock_initial,
                        stock_avant=Decimal("0"),
                        stock_apres=stock_initial,
                        cout_unitaire=prix_achat,
                        user_id=acting_user_id,
                        commentaire="Stock initial à la création de l'article.",
                    )
                )
                session.flush()

            self._audit(session, "ARTICLE_CREATE", article.id)
            summary = ArticleSummary.from_model(article)

        logger.info("Article créé : %s (%s)", reference, designation)
        return summary

    def update_article(
        self,
        article_id: int,
        reference: str,
        designation: str,
        category_id: int,
        unite: str,
        prix_achat: Decimal,
        prix_vente: Decimal,
        stock_min: Decimal,
        *,
        fournisseur_principal_id=_UNSET,
        stock_max=_UNSET,
        emplacement=_UNSET,
        description=_UNSET,
        code_barres=_UNSET,
    ) -> ArticleSummary:
        """Modifie un article. N'accepte volontairement aucun paramètre
        ``stock_actuel`` ni ``cout_moyen_pondere`` : ces valeurs restent
        pilotées exclusivement par les opérations de stock. Les champs
        optionnels non fournis conservent leur valeur actuelle."""
        self._permissions.require_permission("ARTICLE_UPDATE")

        reference = _validate_text(reference, "référence", MAX_REFERENCE_LENGTH)
        designation = _validate_text(designation, "désignation", MAX_DESIGNATION_LENGTH)
        unite = _validate_text(unite, "unité", MAX_UNITE_LENGTH)
        prix_achat = _validate_money(prix_achat, "prix d'achat")
        prix_vente = _validate_money(prix_vente, "prix de vente")
        stock_min = _validate_quantity(stock_min, "stock minimum")
        if stock_max is not _UNSET:
            stock_max = _validate_optional_quantity(stock_max, "stock maximum")
        if emplacement is not _UNSET:
            emplacement = _validate_optional_text(emplacement, "emplacement", MAX_EMPLACEMENT_LENGTH)
        if description is not _UNSET:
            description = _validate_optional_text(description, "description", MAX_DESCRIPTION_LENGTH)
        if code_barres is not _UNSET:
            code_barres = _validate_optional_text(code_barres, "code-barres", MAX_BARCODE_LENGTH)

        with session_scope(self._settings) as session:
            article_repo = ArticleRepository(session)
            category_repo = CategoryRepository(session)
            supplier_repo = SupplierRepository(session)

            article = article_repo.get_by_id(article_id)
            if article is None:
                raise NotFoundError(f"Article {article_id} introuvable.")

            if article_repo.find_by_reference(reference, exclude_id=article_id) is not None:
                raise ConflictError(f"La référence « {reference} » est déjà utilisée.")
            if (
                code_barres is not _UNSET
                and code_barres is not None
                and article_repo.find_by_barcode(code_barres, exclude_id=article_id) is not None
            ):
                raise ConflictError(f"Le code-barres « {code_barres} » est déjà utilisé.")

            # Une catégorie/un fournisseur inactif reste autorisé s'il s'agit de
            # l'association déjà en place (préserve l'historique) ; toute
            # NOUVELLE sélection doit en revanche être active.
            if category_id != article.category_id:
                category = category_repo.get_by_id(category_id)
                if category is None:
                    raise NotFoundError(f"Catégorie {category_id} introuvable.")
                if category.statut != StatutActifInactif.ACTIF:
                    raise ValidationError("La catégorie sélectionnée est inactive.")

            if (
                fournisseur_principal_id is not _UNSET
                and fournisseur_principal_id != article.fournisseur_principal_id
                and fournisseur_principal_id is not None
            ):
                supplier = supplier_repo.get_by_id(fournisseur_principal_id)
                if supplier is None:
                    raise NotFoundError(f"Fournisseur {fournisseur_principal_id} introuvable.")
                if supplier.statut != StatutActifInactif.ACTIF:
                    raise ValidationError("Le fournisseur sélectionné est inactif.")

            effective_stock_max = stock_max if stock_max is not _UNSET else article.stock_max
            if effective_stock_max is not None and effective_stock_max < stock_min:
                raise ValidationError("Le stock maximum doit être supérieur ou égal au stock minimum.")

            article.reference = reference
            article.designation = designation
            article.category_id = category_id
            article.unite = unite
            article.prix_achat_defaut = prix_achat
            article.prix_vente = prix_vente
            article.stock_min = stock_min
            if stock_max is not _UNSET:
                article.stock_max = stock_max
            if fournisseur_principal_id is not _UNSET:
                article.fournisseur_principal_id = fournisseur_principal_id
            if emplacement is not _UNSET:
                article.emplacement = emplacement
            if description is not _UNSET:
                article.description = description
            if code_barres is not _UNSET:
                article.code_barres = code_barres

            try:
                session.flush()
            except IntegrityError as exc:
                raise ConflictError("La référence ou le code-barres est déjà utilisé.") from exc

            self._audit(session, "ARTICLE_UPDATE", article.id)
            summary = ArticleSummary.from_model(article)

        logger.info("Article modifié : id=%s -> %s", article_id, reference)
        return summary

    def activate_article(self, article_id: int) -> ArticleSummary:
        self._permissions.require_permission("ARTICLE_ACTIVATE")
        return self._set_status(article_id, StatutActifInactif.ACTIF, "ARTICLE_ACTIVATE")

    def deactivate_article(self, article_id: int) -> ArticleSummary:
        """Désactivation (jamais de suppression physique)."""
        self._permissions.require_permission("ARTICLE_DEACTIVATE")
        return self._set_status(article_id, StatutActifInactif.INACTIF, "ARTICLE_DEACTIVATE")

    def _set_status(self, article_id: int, statut: StatutActifInactif, action: str) -> ArticleSummary:
        with session_scope(self._settings) as session:
            repo = ArticleRepository(session)
            article = repo.get_by_id(article_id)
            if article is None:
                raise NotFoundError(f"Article {article_id} introuvable.")

            article.statut = statut
            self._audit(session, action, article.id)
            session.flush()
            summary = ArticleSummary.from_model(article)

        logger.info("Article id=%s : %s", article_id, action)
        return summary
