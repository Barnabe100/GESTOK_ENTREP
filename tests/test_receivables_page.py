from datetime import date
from decimal import Decimal

from app.models.enums import StatutPaiement
from app.services.sales.sale_service import VenteLigneInput
from app.views.pages.receivables_page import ReceivablesPage


def _build_page(stack) -> ReceivablesPage:
    return ReceivablesPage(stack.sales, stack.clients, stack.permissions)


def _make_article(stack, reference="ART-1"):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("50"),
    )


def _validated_sale(stack, article, quantite=Decimal("2"), client_id=None, paiement_initial=Decimal("0")):
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, quantite, Decimal("150"))], client_id=client_id
    )
    return stack.sales.validate_sale(sale.id, paiement_initial)


def test_receivables_page_lists_validated_sales_with_payment_columns(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client A")
    _validated_sale(stack, article, client_id=client.id, paiement_initial=Decimal("100"))

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "Client A"
    assert page.table.item(0, 6).text() == "Partiellement payée"


def test_receivables_page_reflects_payment_made_after_page_was_built(qtbot, login_as) -> None:
    """Scénario exact du bug diagnostiqué : la page est construite (donc
    rafraîchie une première fois) AVANT le paiement — reproduit le
    QStackedWidget persistant de MainWindow, où une page déjà ouverte ne se
    met pas à jour toute seule. Un appel explicite à refresh() doit alors
    afficher les valeurs correctes, exactement comme le détail de la
    vente."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client Test")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("62500"))], client_id=client.id
    )
    validated = stack.sales.validate_sale(sale.id, Decimal("0"))  # validée, non payée

    page = _build_page(stack)
    qtbot.addWidget(page)
    assert page.table.item(0, 4).text() == "0 FCFA"
    assert page.table.item(0, 6).text() == "Non payée"

    # Paiement enregistré APRÈS la construction de la page (ailleurs, ex.
    # SaleDetailDialog) — la page elle-même n'est pas notifiée automatiquement.
    stack.sales.record_payment(validated.id, Decimal("62500"))

    # Toujours figée sur l'état d'avant paiement tant que refresh() n'a pas
    # été appelé (comportement attendu de ce composant, purement passif).
    assert page.table.item(0, 4).text() == "0 FCFA"

    page.refresh()

    assert page.table.item(0, 4).text() == "62 500 FCFA"
    assert page.table.item(0, 5).text() == "0 FCFA"
    assert page.table.item(0, 6).text() == "Payée"

    # Cohérence avec le détail de la vente (même source, même service).
    detail = stack.sales.get_sale(validated.id)
    assert detail.montant_paye == Decimal("62500")
    assert detail.reste_a_payer == Decimal("0")
    assert detail.statut_paiement == StatutPaiement.PAYEE


def test_receivables_page_excludes_draft_and_cancelled_sales(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])
    cancelled = _validated_sale(stack, article)
    stack.sales.cancel_sale(cancelled.id, "Motif de test valide")

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0


def test_receivables_page_filters_by_client(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client_a = stack.clients.create_client("Client A")
    client_b = stack.clients.create_client("Client B")
    _validated_sale(stack, article, client_id=client_a.id)
    _validated_sale(stack, article, client_id=client_b.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    index = page.client_filter_combo.findData(client_a.id)
    page.client_filter_combo.setCurrentIndex(index)

    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "Client A"


def test_receivables_page_filters_by_statut_paiement(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    _validated_sale(stack, article, paiement_initial=Decimal("300"))  # PAYEE
    _validated_sale(stack, article)  # NON_PAYEE

    page = _build_page(stack)
    qtbot.addWidget(page)
    index = page.statut_paiement_combo.findData(StatutPaiement.PAYEE)
    page.statut_paiement_combo.setCurrentIndex(index)

    assert page.table.rowCount() == 1
    assert page.table.item(0, 6).text() == "Payée"


def test_receivables_page_shows_client_receivable_total_when_client_selected(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client Créance")
    _validated_sale(stack, article, client_id=client.id, paiement_initial=Decimal("100"))

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.client_total_label.text() == ""

    index = page.client_filter_combo.findData(client.id)
    page.client_filter_combo.setCurrentIndex(index)

    assert "Créance client" in page.client_total_label.text()
    assert page.client_total_label.text() != ""


def test_receivables_page_search_filters_by_numero(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    v1 = _validated_sale(stack, article)
    _validated_sale(stack, article)

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText(v1.numero)

    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == v1.numero
