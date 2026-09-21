from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.enums import StatutInventaire, StatutOperation, TypeMouvement
from app.services.entries.entry_service import EntreeLigneInput
from app.services.exits.exit_service import SortieLigneInput
from app.services.inventory.inventory_service import InventaireLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import PermissionDeniedError


def _make_category(stack, nom="Boissons"):
    return stack.categories.create_category(nom)


def _make_article(stack, reference="ART-0001", stock_initial=Decimal("0"), category_id=None,
                   cmup=None, stock_min=Decimal("0"), prix_vente=Decimal("150")):
    if category_id is None:
        category_id = _make_category(stack).id
    return stack.articles.create_article(
        reference, "Article de test", category_id, "unité",
        cmup if cmup is not None else Decimal("100"), prix_vente,
        stock_min, stock_initial=stock_initial,
    )


# -- A. État du stock -------------------------------------------------------------


def test_stock_state_reports_correct_stock_and_cmup(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"), cmup=Decimal("200"))

    rows = stack.reports.get_stock_state()

    row = next(r for r in rows if r.reference == article.reference)
    assert row.stock_actuel == Decimal("50")
    assert row.cout_moyen_pondere == Decimal("200.00")


def test_stock_state_computes_valeur_stock(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"), cmup=Decimal("200"))

    rows = stack.reports.get_stock_state()

    row = next(r for r in rows if r.reference == article.reference)
    assert row.valeur_stock == Decimal("10000.00")
    assert isinstance(row.valeur_stock, Decimal)


def test_stock_state_uses_cmup_after_entry_validation_not_purchase_price(login_as) -> None:
    """Le CMUP affiché doit être celui déjà recalculé par StockService, pas
    un nouveau calcul indépendant dans le rapport."""
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur")
    article = _make_article(stack, stock_initial=Decimal("100"), cmup=Decimal("1000"))

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("50"), Decimal("1200"))]
    )
    stack.entries.validate_entry(entry.id)

    rows = stack.reports.get_stock_state()
    row = next(r for r in rows if r.reference == article.reference)
    assert row.cout_moyen_pondere == Decimal("1066.67")  # (100*1000+50*1200)/150
    assert row.valeur_stock == round(Decimal("150") * Decimal("1066.67"), 2)


def test_stock_state_excludes_inactive_articles_by_default(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    active = _make_article(stack, reference="ART-ON", category_id=category.id)
    inactive = _make_article(stack, reference="ART-OFF", category_id=category.id)
    stack.articles.deactivate_article(inactive.id)

    rows = stack.reports.get_stock_state()

    references = {r.reference for r in rows}
    assert "ART-ON" in references
    assert "ART-OFF" not in references


def test_stock_state_includes_inactive_articles_when_requested(login_as) -> None:
    stack, _ = login_as("Administrateur")
    inactive = _make_article(stack, reference="ART-OFF2")
    stack.articles.deactivate_article(inactive.id)

    rows = stack.reports.get_stock_state(include_inactive=True)

    references = {r.reference for r in rows}
    assert "ART-OFF2" in references
    row = next(r for r in rows if r.reference == "ART-OFF2")
    assert row.actif is False


# -- B. Stock faible ----------------------------------------------------------------


def test_low_stock_includes_article_below_minimum(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, reference="ART-BELOW", stock_initial=Decimal("2"), stock_min=Decimal("10"))

    rows = stack.reports.get_low_stock()

    assert "ART-BELOW" in {r.reference for r in rows}


def test_low_stock_includes_article_exactly_at_minimum(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, reference="ART-EXACT", stock_initial=Decimal("10"), stock_min=Decimal("10"))

    rows = stack.reports.get_low_stock()

    assert "ART-EXACT" in {r.reference for r in rows}


def test_low_stock_excludes_article_above_minimum(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, reference="ART-ABOVE", stock_initial=Decimal("50"), stock_min=Decimal("10"))

    rows = stack.reports.get_low_stock()

    assert "ART-ABOVE" not in {r.reference for r in rows}


# -- C. Rupture de stock --------------------------------------------------------------


def test_out_of_stock_includes_zero_stock_article(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, reference="ART-ZERO", stock_initial=Decimal("0"))

    rows = stack.reports.get_out_of_stock()

    assert "ART-ZERO" in {r.reference for r in rows}


def test_out_of_stock_excludes_positive_stock_article(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, reference="ART-POS", stock_initial=Decimal("1"))

    rows = stack.reports.get_out_of_stock()

    assert "ART-POS" not in {r.reference for r in rows}


def test_out_of_stock_is_distinct_from_low_stock(login_as) -> None:
    """Un article à stock faible mais non nul n'apparaît pas dans les
    ruptures ; l'inverse (rupture apparaissant aussi en stock faible) est
    normal dès lors que stock_min >= 0 (§3.C)."""
    stack, _ = login_as("Administrateur")
    low_not_out = _make_article(stack, reference="ART-LOWONLY", stock_initial=Decimal("3"), stock_min=Decimal("10"))

    out_of_stock = {r.reference for r in stack.reports.get_out_of_stock()}
    low_stock = {r.reference for r in stack.reports.get_low_stock()}

    assert "ART-LOWONLY" in low_stock
    assert "ART-LOWONLY" not in out_of_stock


# -- I. Valorisation -----------------------------------------------------------------


def test_valorisation_per_article_value(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"), cmup=Decimal("300"))

    report = stack.reports.get_valorisation()

    row = next(r for r in report.rows if r.reference == article.reference)
    assert row.valeur_stock == Decimal("3000.00")


def test_valorisation_total_general(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    _make_article(stack, reference="ART-A", stock_initial=Decimal("10"), cmup=Decimal("100"), category_id=category.id)
    _make_article(stack, reference="ART-B", stock_initial=Decimal("5"), cmup=Decimal("200"), category_id=category.id)

    report = stack.reports.get_valorisation()

    assert report.total == Decimal("1000.00") + Decimal("1000.00")
    assert isinstance(report.total, Decimal)


def test_valorisation_uses_decimal_throughout(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, stock_initial=Decimal("3"), cmup=Decimal("33.33"))

    report = stack.reports.get_valorisation()

    for row in report.rows:
        assert isinstance(row.valeur_stock, Decimal)
    assert isinstance(report.total, Decimal)


# -- D. Mouvements de stock -----------------------------------------------------------


def test_movements_retrieved_correctly(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack, stock_initial=Decimal("0"))
    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))])
    stack.entries.validate_entry(entry.id)

    movements = stack.reports.get_movements(article_id=article.id)

    assert len(movements) == 1
    assert movements[0].type == TypeMouvement.ENTREE
    assert movements[0].quantite == Decimal("10")


def test_movements_cover_all_types(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    motif = stack.exit_reasons.create_exit_reason("Perte")
    article = _make_article(stack, stock_initial=Decimal("0"))

    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("100"), Decimal("100"))])
    stack.entries.validate_entry(entry.id)

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])
    stack.exits.validate_exit(exit_.id)

    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("10"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)
    stack.sales.cancel_sale(sale.id, "Motif de test valide")

    inv = stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("100"))])
    stack.inventory.validate_inventory(inv.id)

    movements = stack.reports.get_movements(article_id=article.id)
    types = {m.type for m in movements}

    assert TypeMouvement.ENTREE in types
    assert TypeMouvement.SORTIE in types
    assert TypeMouvement.VENTE in types
    assert TypeMouvement.ANNULATION in types
    assert TypeMouvement.AJUSTEMENT in types


def test_movements_filtered_by_period(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    in_range = stack.reports.get_movements(article_id=article.id, date_from=today, date_to=today)
    out_of_range = stack.reports.get_movements(article_id=article.id, date_from=tomorrow, date_to=tomorrow)
    before_range = stack.reports.get_movements(article_id=article.id, date_from=yesterday, date_to=yesterday)

    assert len(in_range) == 1  # ajustement du stock initial, créé "aujourd'hui"
    assert len(out_of_range) == 0
    assert len(before_range) == 0


def test_movements_filtered_by_article(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", stock_initial=Decimal("10"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-2", stock_initial=Decimal("20"), category_id=category.id)

    movements_1 = stack.reports.get_movements(article_id=article_1.id)
    movements_2 = stack.reports.get_movements(article_id=article_2.id)

    assert all(m.article_id == article_1.id for m in movements_1)
    assert all(m.article_id == article_2.id for m in movements_2)


def test_movements_filtered_by_type(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack, stock_initial=Decimal("0"))
    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))])
    stack.entries.validate_entry(entry.id)

    entree_movements = stack.reports.get_movements(article_id=article.id, type_mouvement=TypeMouvement.ENTREE)
    sortie_movements = stack.reports.get_movements(article_id=article.id, type_mouvement=TypeMouvement.SORTIE)

    assert len(entree_movements) == 1
    assert len(sortie_movements) == 0


# -- E. Entrées ---------------------------------------------------------------------


def test_entries_report_retrieves_correctly(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack)
    stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))])

    rows = stack.reports.get_entries()

    assert len(rows) == 1
    assert rows[0].numero == "ENT-000001"


def test_entries_report_filters_by_statut_distinguishing_brouillon_and_validee(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack)
    draft = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [])
    to_validate = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))])
    stack.entries.validate_entry(to_validate.id)

    brouillons = stack.reports.get_entries(statut=StatutOperation.BROUILLON)
    validees = stack.reports.get_entries(statut=StatutOperation.VALIDEE)

    assert {r.numero for r in brouillons} == {draft.numero}
    assert {r.numero for r in validees} == {to_validate.numero}


def test_entries_report_filters_by_period(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    stack.entries.create_entry(supplier.id, date(2026, 1, 15), [])

    in_range = stack.reports.get_entries(date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    out_of_range = stack.reports.get_entries(date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))
    boundary = stack.reports.get_entries(date_from=date(2026, 1, 15), date_to=date(2026, 1, 15))

    assert len(in_range) == 1
    assert len(out_of_range) == 0
    assert len(boundary) == 1  # borne inclusive


# -- F. Sorties -----------------------------------------------------------------------


def test_exits_report_retrieves_correctly(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = stack.exit_reasons.create_exit_reason("Perte")
    article = _make_article(stack, stock_initial=Decimal("50"))
    stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))])

    rows = stack.reports.get_exits()

    assert len(rows) == 1
    assert rows[0].motif_libelle == "Perte"


def test_exits_report_filters_by_motif_and_period(login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif_a = stack.exit_reasons.create_exit_reason("Perte")
    motif_b = stack.exit_reasons.create_exit_reason("Casse")
    stack.exits.create_exit(motif_a.id, date(2026, 1, 1), [])
    stack.exits.create_exit(motif_b.id, date(2026, 2, 1), [])

    filtered_by_motif = stack.reports.get_exits(motif_id=motif_a.id)
    filtered_by_period = stack.reports.get_exits(date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))

    assert len(filtered_by_motif) == 1
    assert filtered_by_motif[0].motif_libelle == "Perte"
    assert len(filtered_by_period) == 1
    assert filtered_by_period[0].motif_libelle == "Casse"


# -- G. Ventes ------------------------------------------------------------------------


def test_sales_report_uses_historized_prix_unitaire_not_catalog_price(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, prix_vente=Decimal("150"))
    stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("10"), Decimal("150"))])

    stack.articles.update_article(
        article.id, article.reference, article.designation, article.category_id, article.unite,
        article.prix_achat, Decimal("999"), article.stock_min,
    )

    rows = stack.reports.get_sales()

    assert rows[0].total == Decimal("1500.00")  # 10 * 150 (historisé), pas 10 * 999


def test_sales_report_with_multiple_lines(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", category_id=category.id, prix_vente=Decimal("100"))
    article_2 = _make_article(stack, reference="ART-2", category_id=category.id, prix_vente=Decimal("200"))

    stack.sales.create_sale(
        date(2026, 1, 1),
        [VenteLigneInput(article_1.id, Decimal("2"), Decimal("100")), VenteLigneInput(article_2.id, Decimal("3"), Decimal("200"))],
    )

    rows = stack.reports.get_sales()

    assert rows[0].total == Decimal("800.00")  # 200 + 600
    assert len(rows[0].lignes) == 2


def test_sales_report_filters_by_period_and_statut(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("10"))
    draft = stack.sales.create_sale(date(2026, 1, 1), [])
    validated = stack.sales.create_sale(date(2026, 2, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])
    stack.sales.validate_sale(validated.id)

    brouillons = stack.reports.get_sales(statut=StatutOperation.BROUILLON)
    period = stack.reports.get_sales(date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))

    assert {r.numero for r in brouillons} == {draft.numero}
    assert {r.numero for r in period} == {validated.numero}


# -- H. Inventaires -------------------------------------------------------------------


def test_inventories_report_retrieves_correctly(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("100"))
    stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("97"))])

    rows = stack.reports.get_inventories()

    assert len(rows) == 1
    assert rows[0].numero == "INV-000001"


def test_inventories_report_counts_positive_and_negative_ecarts(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-1", stock_initial=Decimal("100"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-2", stock_initial=Decimal("50"), category_id=category.id)
    article_3 = _make_article(stack, reference="ART-3", stock_initial=Decimal("10"), category_id=category.id)

    stack.inventory.create_inventory(
        date(2026, 1, 1),
        [
            InventaireLigneInput(article_1.id, Decimal("105")),  # +5
            InventaireLigneInput(article_2.id, Decimal("47")),   # -3
            InventaireLigneInput(article_3.id, Decimal("10")),   # 0
        ],
    )

    rows = stack.reports.get_inventories()

    assert rows[0].nombre_lignes == 3
    assert rows[0].nombre_ecarts_positifs == 1
    assert rows[0].nombre_ecarts_negatifs == 1
    assert rows[0].quantite_totale_ajustee == Decimal("8.000")  # |5| + |-3| + |0|


def test_inventories_report_filters_by_period_and_statut(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    draft = stack.inventory.create_inventory(date(2026, 1, 1), [])
    validated = stack.inventory.create_inventory(date(2026, 2, 1), [InventaireLigneInput(article.id, Decimal("50"))])
    stack.inventory.validate_inventory(validated.id)

    brouillons = stack.reports.get_inventories(statut=StatutInventaire.BROUILLON)
    period = stack.reports.get_inventories(date_from=date(2026, 2, 1), date_to=date(2026, 2, 28))

    assert {r.numero for r in brouillons} == {draft.numero}
    assert {r.numero for r in period} == {validated.numero}


# -- permissions ----------------------------------------------------------------------


def test_report_view_permission_enforced(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.reports.get_stock_state()
    with pytest.raises(PermissionDeniedError):
        stack.reports.get_movements()
    with pytest.raises(PermissionDeniedError):
        stack.reports.get_entries()
    with pytest.raises(PermissionDeniedError):
        stack.reports.get_sales()
    with pytest.raises(PermissionDeniedError):
        stack.reports.get_inventories()
    with pytest.raises(PermissionDeniedError):
        stack.reports.get_valorisation()


def test_consultation_can_view_reports(login_as) -> None:
    stack, _ = login_as("Consultation")

    assert stack.reports.get_stock_state() == []


def test_report_export_permission_enforced(login_as, tmp_path) -> None:
    stack, _ = login_as("Consultation")  # REPORT_VIEW mais pas REPORT_EXPORT

    with pytest.raises(PermissionDeniedError):
        stack.reports.export_to_csv(tmp_path / "out.csv", ["A"], [["1"]])


def test_report_export_writes_csv(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    out_file = tmp_path / "export.csv"

    stack.reports.export_to_csv(out_file, ["Référence", "Stock"], [["ART-1", "10"], ["ART-2", "5"]])

    content = out_file.read_text(encoding="utf-8-sig")
    assert "Référence;Stock" in content
    assert "ART-1;10" in content


# -- lecture seule ----------------------------------------------------------------------


def test_reports_never_modify_stock_or_cmup(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack, stock_initial=Decimal("50"), cmup=Decimal("300"))
    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("400"))])
    stack.entries.validate_entry(entry.id)

    stock_before = stack.articles.get_article(article.id).stock_actuel
    cmup_before = stack.articles.get_article(article.id).cout_moyen_pondere

    stack.reports.get_stock_state()
    stack.reports.get_low_stock()
    stack.reports.get_out_of_stock()
    stack.reports.get_valorisation()
    stack.reports.get_movements()
    stack.reports.get_entries()
    stack.reports.get_exits()
    stack.reports.get_sales()
    stack.reports.get_inventories()

    stock_after = stack.articles.get_article(article.id).stock_actuel
    cmup_after = stack.articles.get_article(article.id).cout_moyen_pondere
    assert stock_after == stock_before
    assert cmup_after == cmup_before


def test_reports_never_create_movements(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))

    movements_before = len(stack.reports.get_movements(article_id=article.id))

    stack.reports.get_stock_state()
    stack.reports.get_valorisation()
    stack.reports.get_movements()

    movements_after = len(stack.reports.get_movements(article_id=article.id))
    assert movements_after == movements_before


def test_reports_never_modify_business_documents(login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("F")
    article = _make_article(stack)
    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))])

    stack.reports.get_entries()
    stack.reports.get_stock_state()

    reloaded = stack.entries.get_entry(entry.id)
    assert reloaded.statut == StatutOperation.BROUILLON
    assert len(reloaded.lignes) == 1
