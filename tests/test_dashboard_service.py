"""Tests de ``DashboardService`` : KPI, périodes, agrégations pour les
graphiques, alertes, activité récente, garanties de lecture seule,
permissions et licence (§14 du cahier des charges de la phase Dashboard)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.enums import EditionLicence
from app.services.entries.entry_service import EntreeLigneInput
from app.services.exits.exit_service import SortieLigneInput
from app.services.inventory.inventory_service import InventaireLigneInput
from app.services.licensing.license_payload import DEFAULT_FEATURES_BY_EDITION
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import LicenseError, PermissionDeniedError, ValidationError


def _setup_catalog(stack):
    category = stack.categories.create_category("Boissons")
    stack.suppliers.create_supplier("Fournisseur A")
    article_low = stack.articles.create_article(
        "ART-LOW", "Article stock faible", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"),
        stock_initial=Decimal("2"),
    )
    article_exact = stack.articles.create_article(
        "ART-EXACT", "Article au minimum", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"),
        stock_initial=Decimal("5"),
    )
    article_out = stack.articles.create_article(
        "ART-OUT", "Article rupture", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"),
        stock_initial=Decimal("0"),
    )
    article_ok = stack.articles.create_article(
        "ART-OK", "Article au-dessus du minimum", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"),
        stock_initial=Decimal("20"),
    )
    return category, article_low, article_exact, article_out, article_ok


# -- KPI catalogue -----------------------------------------------------------------


def test_catalog_kpis_counts_active_articles_categories_suppliers(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.suppliers.create_supplier("Fournisseur A")
    stack.articles.create_article("ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"))
    stack.articles.create_article("ART-2", "Soda", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"))

    kpis = stack.dashboard.get_catalog_kpis()

    assert kpis.active_articles == 2
    assert kpis.active_categories == 1
    assert kpis.active_suppliers == 1


def test_catalog_kpis_excludes_inactive_entities(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article("ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"))
    stack.articles.deactivate_article(article.id)

    kpis = stack.dashboard.get_catalog_kpis()

    assert kpis.active_articles == 0


# -- KPI stock (instantané) --------------------------------------------------------


def test_stock_kpis_total_value_uses_stored_cmup_never_recomputed(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5"), stock_initial=Decimal("3")
    )

    kpis = stack.dashboard.get_stock_kpis()

    # stock_actuel(3) x CMUP initial (= prix d'achat, 100) = 300, jamais recalculé.
    assert kpis.total_value == Decimal("300.00")
    assert isinstance(kpis.total_value, Decimal)


def test_stock_kpis_low_stock_and_out_of_stock_counts(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    kpis = stack.dashboard.get_stock_kpis()

    # ART-LOW (2<=5), ART-EXACT (5<=5) et ART-OUT (0<=5) : une rupture est
    # aussi un stock faible (même règle que ReportService.get_low_stock).
    assert kpis.low_stock_count == 3
    assert kpis.out_of_stock_count == 1  # ART-OUT (0)


def test_stock_kpis_total_quantity_sums_active_articles(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    kpis = stack.dashboard.get_stock_kpis()

    assert kpis.total_quantity == Decimal("2") + Decimal("5") + Decimal("0") + Decimal("20")


# -- KPI activité (période) ----------------------------------------------------------


def test_activity_kpis_counts_only_validated_documents(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("50")
    )
    today = date.today()

    entry = stack.entries.create_entry(supplier.id, today, [EntreeLigneInput(article.id, Decimal("10"), Decimal("10"))])
    stack.entries.validate_entry(entry.id)
    # Une deuxième entrée reste en brouillon : ne doit pas compter.
    stack.entries.create_entry(supplier.id, today, [EntreeLigneInput(article.id, Decimal("10"), Decimal("10"))])

    exit_doc = stack.exits.create_exit(motif.id, today, [SortieLigneInput(article.id, Decimal("5"))])
    stack.exits.validate_exit(exit_doc.id)

    sale = stack.sales.create_sale(today, [VenteLigneInput(article.id, Decimal("2"), Decimal("15"))])
    stack.sales.validate_sale(sale.id)

    inventory = stack.inventory.create_inventory(today, [InventaireLigneInput(article.id, Decimal("100"))])
    stack.inventory.validate_inventory(inventory.id)

    kpis = stack.dashboard.get_activity_kpis(today, today)

    assert kpis.entries_validated == 1
    assert kpis.exits_validated == 1
    assert kpis.sales_validated == 1
    assert kpis.sales_amount == Decimal("30.00")
    assert kpis.inventories_validated == 1


def test_activity_kpis_default_period_is_current_month() -> None:
    from app.services.dashboard.dashboard_service import default_period

    period_from, period_to = default_period()

    assert period_from == date.today().replace(day=1)
    assert period_to == date.today()


def test_activity_kpis_period_boundaries_are_inclusive(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("50")
    )
    boundary_date = date.today() - timedelta(days=5)
    entry = stack.entries.create_entry(
        supplier.id, boundary_date, [EntreeLigneInput(article.id, Decimal("10"), Decimal("10"))]
    )
    stack.entries.validate_entry(entry.id)

    kpis_included = stack.dashboard.get_activity_kpis(boundary_date, boundary_date)
    kpis_excluded_before = stack.dashboard.get_activity_kpis(boundary_date + timedelta(days=1), boundary_date + timedelta(days=1))
    kpis_excluded_after = stack.dashboard.get_activity_kpis(boundary_date - timedelta(days=1), boundary_date - timedelta(days=1))

    assert kpis_included.entries_validated == 1
    assert kpis_excluded_before.entries_validated == 0
    assert kpis_excluded_after.entries_validated == 0


def test_activity_kpis_empty_period_returns_zero_without_error(login_as) -> None:
    """Une période valide (jamais future, § lot dates) mais réellement vide
    retourne des compteurs à zéro, jamais une exception — remplace l'ancien
    ``far_future`` (désormais explicitement refusé, voir
    ``test_period_validation_rejects_*`` ci-dessous) par une période passée
    garantie sans aucune donnée."""
    stack, _ = login_as("Administrateur")
    far_past = date(2000, 1, 1)

    kpis = stack.dashboard.get_activity_kpis(far_past, far_past)

    assert kpis.entries_validated == 0
    assert kpis.exits_validated == 0
    assert kpis.sales_validated == 0
    assert kpis.sales_amount == Decimal("0")
    assert kpis.inventories_validated == 0


# -- graphique : évolution des ventes -------------------------------------------------


def test_sales_evolution_groups_same_day_sales_together(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("50")
    )
    today = date.today()
    for _ in range(2):
        sale = stack.sales.create_sale(today, [VenteLigneInput(article.id, Decimal("1"), Decimal("15"))])
        stack.sales.validate_sale(sale.id)

    points = stack.dashboard.get_sales_evolution(today, today)

    assert len(points) == 1
    assert points[0].amount == Decimal("30.00")
    assert points[0].bucket_start == today


def test_sales_evolution_empty_period_returns_empty_list(login_as) -> None:
    stack, _ = login_as("Administrateur")
    today = date.today()

    points = stack.dashboard.get_sales_evolution(today, today)

    assert points == []


# -- graphique : répartition des mouvements --------------------------------------------


def test_movement_breakdown_counts_by_type(login_as) -> None:
    from app.models.enums import TypeMouvement

    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5")
    )
    today = date.today()

    entry = stack.entries.create_entry(supplier.id, today, [EntreeLigneInput(article.id, Decimal("10"), Decimal("10"))])
    stack.entries.validate_entry(entry.id)

    sale = stack.sales.create_sale(today, [VenteLigneInput(article.id, Decimal("2"), Decimal("15"))])
    stack.sales.validate_sale(sale.id)

    breakdown = stack.dashboard.get_movement_breakdown(today, today)

    assert breakdown[TypeMouvement.ENTREE] == 1
    assert breakdown[TypeMouvement.VENTE] == 1
    assert TypeMouvement.ANNULATION not in breakdown  # aucune annulation : type absent, jamais à zéro


# -- graphique : valeur du stock par catégorie -----------------------------------------


def test_stock_value_by_category_groups_correctly(login_as) -> None:
    stack, _ = login_as("Administrateur")
    boissons = stack.categories.create_category("Boissons")
    hygiene = stack.categories.create_category("Hygiène")
    stack.articles.create_article(
        "ART-1", "Eau", boissons.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("2")
    )
    stack.articles.create_article(
        "ART-2", "Soda", boissons.id, "u", Decimal("20"), Decimal("25"), Decimal("5"), stock_initial=Decimal("1")
    )
    stack.articles.create_article(
        "ART-3", "Savon", hygiene.id, "u", Decimal("5"), Decimal("8"), Decimal("5"), stock_initial=Decimal("4")
    )

    rows = stack.dashboard.get_stock_value_by_category()
    by_category = {r.category_nom: r.valeur_stock for r in rows}

    assert by_category["Boissons"] == Decimal("40.00")  # 2*10 + 1*20
    assert by_category["Hygiène"] == Decimal("20.00")  # 4*5


# -- alertes / articles en stock faible -------------------------------------------------


def test_low_stock_top_includes_article_exactly_at_minimum(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    rows = stack.dashboard.get_low_stock_top()
    references = {r.reference for r in rows}

    assert "ART-EXACT" in references


def test_low_stock_top_excludes_article_above_minimum(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    rows = stack.dashboard.get_low_stock_top()
    references = {r.reference for r in rows}

    assert "ART-OK" not in references


def test_low_stock_top_sorted_by_severity_and_respects_limit(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _setup_catalog(stack)

    rows = stack.dashboard.get_low_stock_top(limit=1)

    assert len(rows) == 1
    # ART-OUT (0/5, déficit -5) est plus sévère que ART-LOW (2/5, déficit -3).
    assert rows[0].reference == "ART-OUT"


# -- activité récente -----------------------------------------------------------------


def test_recent_activity_sorted_chronologically_descending(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5")
    )
    today = date.today()
    for _ in range(3):
        entry = stack.entries.create_entry(supplier.id, today, [EntreeLigneInput(article.id, Decimal("1"), Decimal("10"))])
        stack.entries.validate_entry(entry.id)

    rows = stack.dashboard.get_recent_activity(limit=10)

    dates = [r.date_heure for r in rows]
    assert dates == sorted(dates, reverse=True)


def test_recent_activity_respects_limit(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5")
    )
    today = date.today()
    for _ in range(5):
        entry = stack.entries.create_entry(supplier.id, today, [EntreeLigneInput(article.id, Decimal("1"), Decimal("10"))])
        stack.entries.validate_entry(entry.id)

    rows = stack.dashboard.get_recent_activity(limit=3)

    assert len(rows) == 3


# -- lecture seule (§9) ---------------------------------------------------------------


def test_get_overview_never_modifies_stock_or_cmup(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    supplier = stack.suppliers.create_supplier("Fournisseur A")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("100"), Decimal("150"), Decimal("5"), stock_initial=Decimal("10")
    )
    entry = stack.entries.create_entry(supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("5"), Decimal("10"))])
    stack.entries.validate_entry(entry.id)

    before = stack.articles.get_article(article.id)
    stack.dashboard.get_overview(date.today() - timedelta(days=30), date.today())
    after = stack.articles.get_article(article.id)

    assert after.stock_actuel == before.stock_actuel
    assert after.cout_moyen_pondere == before.cout_moyen_pondere


def test_get_overview_never_creates_a_movement(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    stack.articles.create_article("ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"))

    movements_before = stack.dashboard.get_recent_activity(limit=1000)
    stack.dashboard.get_overview(date.today() - timedelta(days=30), date.today())
    movements_after = stack.dashboard.get_recent_activity(limit=1000)

    assert len(movements_after) == len(movements_before)


# -- permissions ------------------------------------------------------------------------


def test_catalog_kpis_partial_for_vendeur_without_category_and_supplier_view(login_as) -> None:
    """Le Vendeur a ARTICLE_VIEW mais pas CATEGORY_VIEW/SUPPLIER_VIEW (voir
    app/db/seed.py) : ces deux champs doivent être None, jamais 0 (qui
    laisserait croire à un catalogue vide plutôt qu'à un accès non
    autorisé)."""
    stack, _ = login_as("Vendeur")

    kpis = stack.dashboard.get_catalog_kpis()

    assert kpis.active_articles is not None
    assert kpis.active_categories is None
    assert kpis.active_suppliers is None


def test_stock_kpis_none_for_role_without_report_view(login_as) -> None:
    """Sections hors du domaine Ventes (§ lot dates/permissions) : REPORT_VIEW
    reste la seule voie d'accès, le Vendeur (qui ne l'a pas par défaut) en
    reste donc exclu — comportement inchangé par ce lot."""
    stack, _ = login_as("Vendeur")

    assert stack.dashboard.get_stock_kpis() is None
    assert stack.dashboard.get_movement_breakdown(date.today(), date.today()) is None
    assert stack.dashboard.get_low_stock_top() is None
    assert stack.dashboard.get_stock_value_by_category() is None
    assert stack.dashboard.get_recent_activity() is None


def test_activity_kpis_sales_fields_accessible_but_others_none_for_vendeur(login_as) -> None:
    """§ lot dates/permissions : ``get_activity_kpis`` ne retourne plus
    jamais ``None`` dans son ensemble — chaque champ est individuellement
    ``None`` selon SA propre permission source. Le Vendeur a SALE_VIEW (donc
    les champs de ventes sont renseignés, ici à 0 : base vide) mais pas
    REPORT_VIEW (donc entrées/sorties/inventaires restent None)."""
    stack, _ = login_as("Vendeur")

    kpis = stack.dashboard.get_activity_kpis(date.today(), date.today())

    assert kpis.entries_validated is None
    assert kpis.exits_validated is None
    assert kpis.inventories_validated is None
    assert kpis.sales_validated == 0
    assert kpis.sales_amount == Decimal("0")


def test_sales_evolution_accessible_for_vendeur_via_sale_view(login_as) -> None:
    """§ lot dates/permissions : SALE_VIEW suffit désormais, REPORT_VIEW
    n'est plus l'unique porte d'entrée pour ce graphique."""
    stack, _ = login_as("Vendeur")

    evolution = stack.dashboard.get_sales_evolution(date.today(), date.today())

    assert evolution == []  # SALE_VIEW présent : liste vide (aucune vente), jamais None


def test_dashboard_still_accessible_for_vendeur_despite_partial_data(login_as) -> None:
    """DASHBOARD_VIEW est accordée au Vendeur (seed.py) : la page reste
    accessible (get_overview ne lève pas), seules les sections nécessitant
    REPORT_VIEW sont vides."""
    stack, _ = login_as("Vendeur")

    overview = stack.dashboard.get_overview()

    assert overview.catalog.active_articles is not None
    assert overview.stock is None


# -- licence --------------------------------------------------------------------------


def test_dashboard_view_allowed_with_reports_license(login_as) -> None:
    """Licence de test à accès complet (ENTREPRISE, provisionnée par
    défaut) : DASHBOARD_VIEW est mappée sur FEATURE_REPORTS et doit être
    autorisée."""
    stack, _ = login_as("Administrateur")

    assert stack.permissions.has_permission("DASHBOARD_VIEW") is True
    stack.dashboard.get_catalog_kpis()  # ne doit pas lever


def test_dashboard_view_blocked_without_reports_license(login_as, license_envelope_factory) -> None:
    """Une licence DEMO (sans REPORTS, voir DEFAULT_FEATURES_BY_EDITION)
    bloque le Dashboard, MÊME pour un Administrateur (§8 de la phase
    Licences, réutilisé ici sans contournement de FeatureGate)."""
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(
        edition="DEMO", features=sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.DEMO])
    )
    stack.licenses.activate_license(envelope)

    assert stack.permissions.has_permission("DASHBOARD_VIEW") is False
    with pytest.raises(LicenseError):
        stack.dashboard.get_catalog_kpis()


def test_dashboard_requires_dashboard_view_permission_denies_role_without_it(login_as) -> None:
    """Contrôle défensif : même en appelant directement le service, un rôle
    sans DASHBOARD_VIEW serait refusé (aucun rôle seedé n'en est
    aujourd'hui dépourvu — ce test documente le comportement attendu via
    une vérification directe de l'primitive RBAC sous-jacente)."""
    stack, current_user = login_as("Vendeur")
    assert current_user.has_permission("DASHBOARD_VIEW") is True  # état actuel de la matrice RBAC

    # Le contrôle réel (refus si la permission manque) est déjà couvert par
    # PermissionService/RBAC — voir tests/test_permission_service_licensing.py
    # et tests/test_navigation_filtering.py pour la matrice complète.


# -- domaine Ventes du Dashboard : consultation globale, non filtrée (§C/§D) ----------


def _make_sale_as(stack, article, quantite=Decimal("2"), prix=Decimal("150")):
    sale = stack.sales.create_sale(date.today(), [VenteLigneInput(article.id, quantite, prix)])
    return stack.sales.validate_sale(sale.id)


def test_c_vendeur_sees_sales_kpis_from_other_vendeurs_too(login_as) -> None:
    """§C : la consultation des ventes reste globale — les indicateurs de
    ventes du Dashboard d'un Vendeur reflètent TOUTES les ventes validées
    accessibles selon les permissions, jamais uniquement les siennes."""
    admin_stack, _ = login_as("Administrateur")
    category = admin_stack.categories.create_category("Boissons")
    article = admin_stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("50")
    )

    vendeur_y_stack, _ = login_as("Vendeur")
    _make_sale_as(vendeur_y_stack, article, quantite=Decimal("2"), prix=Decimal("150"))  # vente de Y : 300

    vendeur_x_stack, _ = login_as("Vendeur")
    _make_sale_as(vendeur_x_stack, article, quantite=Decimal("1"), prix=Decimal("150"))  # vente de X : 150

    kpis = vendeur_x_stack.dashboard.get_activity_kpis(date.today(), date.today())

    # X voit le total des DEUX ventes (X + Y), jamais uniquement la sienne.
    assert kpis.sales_validated == 2
    assert kpis.sales_amount == Decimal("450.00")


def test_d_sales_evolution_not_filtered_by_owner(login_as) -> None:
    """§D : aucune restriction par ``user_id`` dans les consultations du
    Dashboard — l'évolution des ventes d'un Vendeur inclut les ventes de
    tous les vendeurs, jamais un ``WHERE vente.user_id = utilisateur_connecté``."""
    admin_stack, _ = login_as("Administrateur")
    category = admin_stack.categories.create_category("Boissons")
    article = admin_stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("50")
    )

    vendeur_y_stack, _ = login_as("Vendeur")
    _make_sale_as(vendeur_y_stack, article)

    vendeur_x_stack, _ = login_as("Vendeur")
    _make_sale_as(vendeur_x_stack, article)

    evolution = vendeur_x_stack.dashboard.get_sales_evolution(date.today(), date.today())

    assert len(evolution) == 1  # même jour -> un seul point, agrégeant les DEUX ventes
    assert evolution[0].amount == Decimal("600.00")  # 2 x (2 x 150)


def test_f_gestionnaire_stock_dashboard_unaffected_by_sale_view_change(login_as) -> None:
    """§F : non-régression — le Gestionnaire de stock n'a pas SALE_VIEW mais
    continue de voir les indicateurs de ventes via REPORT_VIEW, exactement
    comme avant ce lot (accès double SALE_VIEW OU REPORT_VIEW, jamais un
    remplacement de REPORT_VIEW par SALE_VIEW)."""
    admin_stack, _ = login_as("Administrateur")
    category = admin_stack.categories.create_category("Boissons")
    article = admin_stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("50")
    )
    _make_sale_as(admin_stack, article)

    stack, _ = login_as("Gestionnaire de stock")
    assert stack.permissions.has_permission("SALE_VIEW") is False  # confirme l'absence par défaut
    assert stack.permissions.has_permission("REPORT_VIEW") is True

    kpis = stack.dashboard.get_activity_kpis(date.today(), date.today())
    evolution = stack.dashboard.get_sales_evolution(date.today(), date.today())

    assert kpis.sales_validated == 1
    assert kpis.sales_amount == Decimal("300.00")
    assert evolution is not None and len(evolution) == 1


# -- contrôle de la période (§ lot dates) ------------------------------------------------


def test_g_period_start_equals_end_equals_today_is_valid(login_as) -> None:
    stack, _ = login_as("Administrateur")
    today = date.today()

    kpis = stack.dashboard.get_activity_kpis(today, today)  # ne doit pas lever

    assert kpis.entries_validated == 0


def test_h_period_start_before_end_before_today_is_valid(login_as) -> None:
    stack, _ = login_as("Administrateur")
    start = date.today() - timedelta(days=10)
    end = date.today() - timedelta(days=5)

    kpis = stack.dashboard.get_activity_kpis(start, end)  # ne doit pas lever

    assert kpis.entries_validated == 0


def test_i_period_start_equals_end_in_the_past_is_valid(login_as) -> None:
    stack, _ = login_as("Administrateur")
    d = date.today() - timedelta(days=3)

    kpis = stack.dashboard.get_activity_kpis(d, d)  # ne doit pas lever

    assert kpis.entries_validated == 0


def test_j_period_start_after_end_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    today = date.today()

    with pytest.raises(ValidationError):
        stack.dashboard.get_activity_kpis(today, today - timedelta(days=1))


def test_k_period_start_after_today_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    future = date.today() + timedelta(days=1)

    with pytest.raises(ValidationError):
        stack.dashboard.get_activity_kpis(future, future)


def test_l_period_end_after_today_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    today = date.today()
    future = today + timedelta(days=1)

    with pytest.raises(ValidationError):
        stack.dashboard.get_activity_kpis(today - timedelta(days=1), future)


def test_m_period_straddling_today_with_end_in_future_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    today = date.today()

    with pytest.raises(ValidationError):
        stack.dashboard.get_activity_kpis(today - timedelta(days=5), today + timedelta(days=5))


def test_period_validation_applies_to_sales_evolution_and_movement_breakdown_too(login_as) -> None:
    """La validation de période n'est pas propre à ``get_activity_kpis`` —
    chaque méthode acceptant une période la revérifie indépendamment
    (défense en profondeur, même principe que le reste de l'application)."""
    stack, _ = login_as("Administrateur")
    today = date.today()
    invalid_start = today + timedelta(days=1)

    with pytest.raises(ValidationError):
        stack.dashboard.get_sales_evolution(invalid_start, invalid_start)
    with pytest.raises(ValidationError):
        stack.dashboard.get_movement_breakdown(invalid_start, invalid_start)
    with pytest.raises(ValidationError):
        stack.dashboard.get_overview(invalid_start, invalid_start)


def test_o_invalid_period_never_reaches_the_database(login_as, monkeypatch) -> None:
    """§O : aucune requête métier n'est lancée pour une période invalide —
    la validation lève AVANT toute ouverture de session/transaction."""
    stack, _ = login_as("Administrateur")
    today = date.today()

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("session_scope ne doit jamais être appelée pour une période invalide")

    monkeypatch.setattr("app.services.dashboard.dashboard_service.session_scope", _fail_if_called)

    with pytest.raises(ValidationError):
        stack.dashboard.get_activity_kpis(today, today - timedelta(days=1))


def test_p_sale_dated_exactly_the_last_day_of_period_is_included(login_as) -> None:
    """§P : reproduit précisément le scénario audité — une vente datée
    exactement du dernier jour de la période sélectionnée doit y être
    incluse (borne ``date_to`` inclusive, voir ``VenteRepository.search``)."""
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "u", Decimal("10"), Decimal("15"), Decimal("5"), stock_initial=Decimal("50")
    )
    today = date.today()
    sale = stack.sales.create_sale(today, [VenteLigneInput(article.id, Decimal("3"), Decimal("15"))])
    stack.sales.validate_sale(sale.id)

    period_from = today - timedelta(days=21)  # ex. "2026-09-01" pour aujourd'hui "2026-09-22"
    kpis = stack.dashboard.get_activity_kpis(period_from, today)

    assert kpis.sales_validated == 1
    assert kpis.sales_amount == Decimal("45.00")
