from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from app.models.enums import StatutOperation
from app.services.sales.sale_service import VenteLigneInput
from app.views.pages.sales_page import SalesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.sales_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.sales_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> SalesPage:
    return SalesPage(stack.sales, stack.articles, stack.clients, stack.documents, stack.permissions)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("50")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def test_sales_page_lists_sales(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("10"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "VNT-000001" in numeros


def test_sales_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.sales.create_sale(date(2026, 1, 1), [])
    stack.sales.create_sale(date(2026, 1, 1), [])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("VNT-000001")

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {"VNT-000001"}


def test_sales_page_status_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    stack.sales.create_sale(date(2026, 1, 1), [])
    to_validate = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(to_validate.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    index = page.status_filter_combo.findData(StatutOperation.VALIDEE)
    page.status_filter_combo.setCurrentIndex(index)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {to_validate.numero}


def test_add_button_enabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True


def test_add_button_disabled_for_gestionnaire_de_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is False


def test_action_buttons_reflect_selected_row_status_for_brouillon(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    draft = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == draft.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is True
    assert page.delete_button.isEnabled() is True
    assert page.validate_button.isEnabled() is True
    assert page.cancel_button.isEnabled() is False


def test_action_buttons_reflect_selected_row_status_for_validee(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is False
    assert page.delete_button.isEnabled() is False
    assert page.validate_button.isEnabled() is False
    assert page.cancel_button.isEnabled() is True


def test_submit_form_creates_draft_sale_without_stock_impact(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1),
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("10"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(None, values)
    page.refresh()

    assert result is True
    created = stack.sales.list_sales()[0]
    assert created.statut == StatutOperation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")


def test_submit_form_updates_existing_draft(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    sale = stack.sales.create_sale(date(2026, 1, 1), [])

    values = {
        "date": date(2026, 2, 1),
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("3"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(sale.id, values)

    assert result is True
    updated = stack.sales.get_sale(sale.id)
    assert len(updated.lignes) == 1


def test_load_edit_initial_returns_lines(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(sale.id)

    assert initial is not None
    assert initial["date"] == date(2026, 1, 1)
    assert len(initial["lignes"]) == 1
    assert initial["lignes"][0]["article_id"] == article.id


def test_load_edit_initial_returns_none_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._load_edit_initial(999999) is None


def test_delete_selected_removes_draft(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._delete_selected(sale.id)

    assert result is True
    from app.utils.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        stack.sales.get_sale(sale.id)


def test_delete_selected_refused_for_validated_sale(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._delete_selected(sale.id)

    assert result is False
    assert stack.sales.get_sale(sale.id).statut == StatutOperation.VALIDEE


def test_load_sale_for_detail_includes_movements_after_validation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._load_sale_for_detail(sale.id)

    assert result is not None
    loaded_sale, movements = result
    assert loaded_sale.numero == sale.numero
    assert len(movements) == 1


def test_validate_selected_updates_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(sale.id)

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("43")


def test_validate_selected_refused_on_insufficient_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("5"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("50"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(sale.id)

    assert result is False
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("5")


def test_cancel_selected_restores_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._cancel_selected(sale.id, "Motif de test valide")

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")


def test_cancel_selected_denied_without_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)

    stack, _ = login_as("Vendeur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._cancel_selected(sale.id, "Motif de test valide")

    assert result is False
    assert stack.sales.get_sale(sale.id).statut == StatutOperation.VALIDEE


def test_on_cancel_clicked_opens_reason_dialog_and_passes_reason_to_service(
    qtbot, login_as, monkeypatch
) -> None:
    """§7 : l'annulation ne s'exécute jamais directement au clic sur
    « Annuler » — un dialogue de motif s'ouvre d'abord, et c'est son motif
    saisi qui est transmis au service."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    class _FakeReasonDialog:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

        def reason(self) -> str:
            return "Motif saisi via le dialogue"

    monkeypatch.setattr("app.views.pages.sales_page.CancellationReasonDialog", _FakeReasonDialog)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_cancel_clicked()

    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.statut == StatutOperation.ANNULEE
    assert reloaded.annulation_motif == "Motif saisi via le dialogue"


def test_load_clients_for_form_excludes_inactive(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    active = stack.clients.create_client("Client actif")
    inactive = stack.clients.create_client("Client inactif")
    stack.clients.deactivate_client(inactive.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    clients = page._load_clients_for_form()

    ids = {client_id for client_id, _ in clients}
    assert active.id in ids
    assert inactive.id not in ids


def test_create_client_from_values_persists_and_returns_tuple(qtbot, login_as) -> None:
    """§5 : la création à la volée doit persister immédiatement le client et
    retourner (id, nom) pour sélection dans le formulaire de vente."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._create_client_from_values(
        {"nom": "Client à la volée", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )

    assert result is not None
    client_id, client_nom = result
    assert client_nom == "Client à la volée"
    assert stack.clients.get_client(client_id).nom == "Client à la volée"


def test_create_client_from_values_shows_warning_on_invalid_data(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._create_client_from_values(
        {"nom": "", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )

    assert result is None


def test_submit_form_with_client_id_associates_sale_to_client(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1),
        "client_id": client.id,
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("2"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(None, values)

    assert result is True
    created = stack.sales.list_sales()[0]
    assert created.client_id == client.id


def test_confirmation_dialog_no_cancels_validate(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("7"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_validate_clicked()

    assert stack.sales.get_sale(sale.id).statut == StatutOperation.BROUILLON


# -- scan code-barres : callback de recherche transmis au formulaire ---------------


def test_lookup_article_by_barcode_finds_active_article(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Cat-scan")
    article = stack.articles.create_article(
        "ART-SCAN", "Article scanné", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), code_barres="1234567890000",
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._lookup_article_by_barcode("1234567890000")

    # Comparaison par valeur Decimal (pas par texte) : le prix relu en base
    # (Numeric(14,2)) peut afficher des zéros de fin différents du texte
    # saisi à la création, sans être une valeur différente.
    assert result is not None
    assert result[0] == article.id
    assert result[1] == "ART-SCAN — Article scanné"
    assert Decimal(result[2]) == article.prix_vente


def test_lookup_article_by_barcode_unknown_returns_none(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._lookup_article_by_barcode("0000000000000") is None


def test_scanning_barcode_in_sale_form_adds_line_and_can_be_validated(qtbot, login_as) -> None:
    """Bout en bout : scan -> ajout au panier -> enregistrement -> validation,
    sans casser la sélection manuelle ni le stock avant validation."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, "ART-SCAN2", stock_initial=Decimal("20"))
    stack.articles.update_article(
        article.id, article.reference, article.designation, article.category_id, article.unite,
        article.prix_achat, article.prix_vente, article.stock_min, code_barres="9998887770000",
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._lookup_article_by_barcode("9998887770000")
    assert result is not None
    article_id, label, prix_vente = result

    created = stack.sales.create_sale(
        date.today(), [VenteLigneInput(article_id, Decimal("1"), Decimal(prix_vente))]
    )
    # Un brouillon ne modifie jamais le stock.
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("20")

    validated = stack.sales.validate_sale(created.id)
    assert validated.statut == StatutOperation.VALIDEE
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("19")


# -- règle de propriété Vendeur (lot dédié) ---------------------------------------------


def _grant_sale_cancel_to_vendeur(stack) -> None:
    role_id = next(r.id for r in stack.roles.list_roles() if r.nom == "Vendeur")
    current_codes = stack.roles.get_role_permissions(role_id)
    stack.roles.update_role_permissions(role_id, current_codes + ["SALE_CANCEL"])


def test_action_buttons_disabled_for_another_vendeur_draft_sale(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)

    vendeur_y_stack, _ = login_as("Vendeur")
    sale_y = vendeur_y_stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))]
    )

    vendeur_x_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_x_stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale_y.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is False
    assert page.delete_button.isEnabled() is False
    assert page.validate_button.isEnabled() is False


def test_action_buttons_enabled_for_own_draft_sale(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)

    stack, _ = login_as("Vendeur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is True
    assert page.delete_button.isEnabled() is True
    assert page.validate_button.isEnabled() is True


def test_cancel_button_disabled_for_another_vendeur_validated_sale(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)
    _grant_sale_cancel_to_vendeur(admin_stack)

    vendeur_y_stack, _ = login_as("Vendeur")
    sale_y = vendeur_y_stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))]
    )
    vendeur_y_stack.sales.validate_sale(sale_y.id)

    vendeur_x_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_x_stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale_y.numero)
    page.table.selectRow(row)

    assert page.cancel_button.isEnabled() is False


def test_cancel_button_enabled_for_own_validated_sale_with_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)
    _grant_sale_cancel_to_vendeur(admin_stack)

    stack, _ = login_as("Vendeur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)

    assert page.cancel_button.isEnabled() is True


def test_on_cancel_clicked_does_not_open_reason_dialog_for_another_vendeur_sale(
    qtbot, login_as, monkeypatch
) -> None:
    """Confort UI (§ lot dédié) : le dialogue de saisie du motif ne doit pas
    s'ouvrir lorsque le refus est déjà certain — même si le bouton était
    force-activé (contournement direct de ``_on_cancel_clicked``, même
    principe que les tests de non-contournement déjà présents pour
    d'autres écrans, ex. ``test_users_page.py``). La protection réelle
    reste côté service (voir ``tests/test_sale_service.py``), pas ce
    confort d'interface."""
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)
    _grant_sale_cancel_to_vendeur(admin_stack)

    vendeur_y_stack, _ = login_as("Vendeur")
    sale_y = vendeur_y_stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))]
    )
    vendeur_y_stack.sales.validate_sale(sale_y.id)

    vendeur_x_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_x_stack)
    qtbot.addWidget(page)

    dialog_opened = {"value": False}

    def _fake_exec(self):
        dialog_opened["value"] = True
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr("app.views.cancellation_reason_dialog.CancellationReasonDialog.exec", _fake_exec)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale_y.numero)
    page.table.selectRow(row)
    page.cancel_button.setEnabled(True)  # contournement direct, comme un bouton non rafraîchi
    page._on_cancel_clicked()

    assert dialog_opened["value"] is False
    assert vendeur_x_stack.sales.get_sale(sale_y.id).statut == StatutOperation.VALIDEE


def test_record_payment_button_disabled_for_another_vendeur_sale(qtbot, login_as) -> None:
    from app.views.sale_detail_dialog import SaleDetailDialog

    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)

    vendeur_y_stack, _ = login_as("Vendeur")
    sale_y = vendeur_y_stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))]
    )
    validated_y = vendeur_y_stack.sales.validate_sale(sale_y.id)

    vendeur_x_stack, _ = login_as("Vendeur")
    sale_for_dialog = vendeur_x_stack.sales.get_sale(validated_y.id)
    dialog = SaleDetailDialog(
        sale_for_dialog, [], "EUR", vendeur_x_stack.documents, vendeur_x_stack.permissions,
        sale_service=vendeur_x_stack.sales, parent=None,
    )
    qtbot.addWidget(dialog)

    assert dialog.record_payment_button.isEnabled() is False


# -- Lot 11 : validation directe (bouton « Valider » du formulaire) ----------

def test_submit_form_validate_action_creates_and_validates_sale_in_one_step(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": None,
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("10"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(None, values, "validate")

    assert result is True
    sale = next(s for s in stack.sales.list_sales() if s.numero == "VNT-000001")
    assert sale.statut == StatutOperation.VALIDEE
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("40")


def test_submit_form_validate_action_insufficient_stock_keeps_draft_recoverable(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("5"))
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": None,
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("999"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(None, values, "validate")

    assert result is True
    sales = [s for s in stack.sales.list_sales() if s.numero == "VNT-000001"]
    assert len(sales) == 1
    created = sales[0]
    assert created.statut == StatutOperation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("5")

    # Parcours de récupération concret : correction de la quantité sur le
    # même brouillon, puis validation réussie depuis la liste.
    stack.sales.update_sale(
        created.id, date(2026, 1, 1),
        [VenteLigneInput(article.id, Decimal("3"), Decimal("150"))],
        client_id=None,
    )
    result2 = page._validate_selected(created.id)
    assert result2 is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("2")


def test_submit_form_validate_action_denied_without_permission_keeps_draft_recoverable(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack, stock_initial=Decimal("50"))

    role_id = next(r.id for r in admin_stack.roles.list_roles() if r.nom == "Vendeur")
    codes = admin_stack.roles.get_role_permissions(role_id)
    admin_stack.roles.update_role_permissions(role_id, [c for c in codes if c != "SALE_VALIDATE"])

    vendeur_stack, _ = login_as("Vendeur")
    page = _build_page(vendeur_stack)
    qtbot.addWidget(page)

    values = {
        "date": date(2026, 1, 1), "client_id": None,
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("10"), "prix_unitaire": Decimal("150")}],
    }

    result = page._submit_form(None, values, "validate")

    assert result is True
    sales = [s for s in admin_stack.sales.list_sales() if s.numero == "VNT-000001"]
    assert len(sales) == 1
    assert sales[0].statut == StatutOperation.BROUILLON
    assert admin_stack.articles.get_article(article.id).stock_actuel == Decimal("50")


# -- Lot 14 : écran de caisse plein format -----------------------------------

def test_view_stack_starts_on_list_view(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._view_stack.currentIndex() == 0


def test_add_button_opens_caisse_view(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page._on_add_clicked()

    assert page._view_stack.currentIndex() == 1
    assert page._caisse_sale_id is None
    assert page._caisse_lines == []


def test_edit_button_opens_caisse_view_prefilled(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client Test")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("3"), Decimal("150"))], client_id=client.id
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)

    page._on_edit_clicked()

    assert page._view_stack.currentIndex() == 1
    assert page._caisse_sale_id == sale.id
    assert len(page._caisse_lines) == 1
    assert page.caisse_client_combo.currentData() == client.id


def test_caisse_search_filters_and_adds_line_on_double_click(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, reference="ART-EAU")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    page.caisse_search_edit.setText("eau")
    assert page.caisse_search_results.count() == 1
    item = page.caisse_search_results.item(0)
    page._on_caisse_search_result_activated(item)

    assert len(page._caisse_lines) == 1
    assert page._caisse_lines[0]["article_id"] == article.id
    assert page._caisse_lines[0]["quantite"] == Decimal("1")
    assert page._caisse_lines[0]["prix_unitaire"] == Decimal("150")
    assert "150" in page.caisse_total_label.text()


def test_caisse_search_no_match_shows_empty_results(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack, reference="ART-EAU")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    page.caisse_search_edit.setText("inexistant")

    assert page.caisse_search_results.count() == 0


def test_caisse_scan_adds_line_with_quantity_one(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = stack.articles.create_article(
        "ART-SCAN", "Article scanné", stack.categories.create_category("Cat-Scan").id, "unité",
        Decimal("100"), Decimal("200"), Decimal("0"), stock_initial=Decimal("10"), code_barres="1234567890",
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    page.caisse_scan_edit.setText("1234567890")
    page._on_caisse_scan_entered()

    assert len(page._caisse_lines) == 1
    assert page._caisse_lines[0]["article_id"] == article.id
    assert page._caisse_lines[0]["prix_unitaire"] == Decimal("200")
    assert page.caisse_scan_edit.text() == ""


def test_caisse_scan_unknown_barcode_shows_warning_and_adds_nothing(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    page.caisse_scan_edit.setText("CODE-INCONNU")
    page._on_caisse_scan_entered()

    assert page._caisse_lines == []


def test_caisse_quantity_edit_updates_total_without_calling_service(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("1"), Decimal("150"))

    calls = {"n": 0}
    monkeypatch.setattr(stack.sales, "create_sale", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    monkeypatch.setattr(stack.sales, "update_sale", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))

    quantity_item = page.caisse_lines_table.item(0, 1)
    quantity_item.setText("4")

    assert page._caisse_lines[0]["quantite"] == Decimal("4")
    assert "600" in page.caisse_total_label.text()
    assert calls["n"] == 0  # aucun appel service pour une simple modification locale


def test_caisse_quantity_edit_rejects_invalid_value_and_reverts(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("2"), Decimal("150"))

    quantity_item = page.caisse_lines_table.item(0, 1)
    quantity_item.setText("abc")

    assert page._caisse_lines[0]["quantite"] == Decimal("2")  # inchangée
    assert page.caisse_lines_table.item(0, 1).text() == "2"  # cellule rétablie
    assert page.caisse_error_label.text() != ""


def test_caisse_quantity_edit_rejects_zero_and_negative(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("2"), Decimal("150"))

    quantity_item = page.caisse_lines_table.item(0, 1)
    quantity_item.setText("0")

    assert page._caisse_lines[0]["quantite"] == Decimal("2")


def test_caisse_remove_line_updates_total(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("2"), Decimal("150"))
    page.caisse_lines_table.selectRow(0)

    page._on_caisse_remove_line_clicked()

    assert page._caisse_lines == []
    assert page.caisse_lines_table.rowCount() == 0
    assert "0" in page.caisse_total_label.text()


def test_caisse_new_client_preserves_lines_and_selects_client(qtbot, login_as, monkeypatch) -> None:
    """§5 du lot : la création rapide ne doit jamais faire perdre la saisie
    de la vente en cours (ici : une ligne déjà ajoutée)."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("3"), Decimal("150"))

    monkeypatch.setattr(page, "_create_client_from_sale_form", lambda: (99, "Client tout neuf"))

    page._on_caisse_new_client_clicked()

    assert page.caisse_client_combo.currentData() == 99
    assert page.caisse_client_combo.currentText() == "Client tout neuf"
    assert len(page._caisse_lines) == 1
    assert page._caisse_lines[0]["quantite"] == Decimal("3")


def test_caisse_new_client_cancelled_keeps_current_selection(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    client = stack.clients.create_client("Client Existant")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._open_caisse(sale_id=None, initial={"date": date.today(), "client_id": client.id})

    monkeypatch.setattr(page, "_create_client_from_sale_form", lambda: None)

    page._on_caisse_new_client_clicked()

    assert page.caisse_client_combo.currentData() == client.id


def test_caisse_create_client_error_preserves_sale_in_progress(qtbot, login_as) -> None:
    """§4/§6 du lot : un échec de création de client (ici nom vide) ne doit
    jamais affecter la vente en cours de saisie."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("2"), Decimal("150"))

    result = page._create_client_from_values(
        {"nom": "", "telephone": "", "email": "", "adresse": "", "observations": ""}
    )

    assert result is None
    assert len(page._caisse_lines) == 1
    assert stack.clients.list_clients() == []


def test_caisse_save_draft_creates_sale_and_returns_to_list(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("2"), Decimal("150"))

    page._on_caisse_save_draft_clicked()

    assert page._view_stack.currentIndex() == 0
    created = stack.sales.list_sales()[0]
    assert created.statut == StatutOperation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")
    assert page.caisse_save_draft_button.isEnabled() is True
    assert page.caisse_validate_button.isEnabled() is True


def test_caisse_validate_creates_and_validates_sale_without_initial_payment(qtbot, login_as) -> None:
    """§3 du lot : aucune création de paiement initial à la validation."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("2"), Decimal("150"))

    page._on_caisse_validate_clicked()

    assert page._view_stack.currentIndex() == 0
    validated = stack.sales.list_sales()[0]
    assert validated.statut == StatutOperation.VALIDEE
    assert validated.montant_paye == Decimal("0")
    assert validated.reste_a_payer == validated.total
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("48")


def test_caisse_validate_rejects_empty_sale_and_stays_open(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    page._on_caisse_validate_clicked()

    # create_sale avec une liste de lignes vide réussit (brouillon vide
    # autorisé) ; c'est validate_sale qui refuse ensuite — la caisse se
    # referme malgré tout (le brouillon est conservé, retrouvable dans la
    # liste, jamais recréé en double).
    assert page._view_stack.currentIndex() == 0
    created = stack.sales.list_sales()[0]
    assert created.statut == StatutOperation.BROUILLON


def test_caisse_validate_insufficient_stock_keeps_draft_recoverable(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("1"))
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("999"), Decimal("150"))

    page._on_caisse_validate_clicked()

    assert page._view_stack.currentIndex() == 0
    created = stack.sales.list_sales()[0]
    assert created.statut == StatutOperation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("1")


def test_caisse_create_failure_keeps_caisse_open_with_lines(qtbot, login_as) -> None:
    """Un échec dès la création/modification elle-même (ici : article
    désactivé entre l'ajout de la ligne et l'enregistrement) laisse la
    caisse ouverte avec la saisie intacte, plutôt que de revenir à la
    liste."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("2"), Decimal("150"))
    stack.articles.deactivate_article(article.id)

    page._on_caisse_save_draft_clicked()

    assert page._view_stack.currentIndex() == 1
    assert len(page._caisse_lines) == 1
    assert stack.sales.list_sales() == []
    assert page.caisse_save_draft_button.isEnabled() is True
    assert page.caisse_validate_button.isEnabled() is True


def test_caisse_back_button_no_confirmation_when_no_lines(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    called = {"n": 0}
    monkeypatch.setattr("app.views.common.QMessageBox.question", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    page._on_caisse_back_clicked()

    assert called["n"] == 0
    assert page._view_stack.currentIndex() == 0


def test_caisse_back_button_confirms_before_discarding_unsaved_lines(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("1"), Decimal("150"))

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    page._on_caisse_back_clicked()
    assert page._view_stack.currentIndex() == 1  # refus : on reste dans la caisse

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    page._on_caisse_back_clicked()
    assert page._view_stack.currentIndex() == 0  # confirmé : retour à la liste


def test_confirm_can_leave_true_when_no_unsaved_lines(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    assert page.confirm_can_leave() is True


def test_confirm_can_leave_true_on_list_view_even_with_stale_state(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.confirm_can_leave() is True


def test_confirm_can_leave_respects_refusal(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("1"), Decimal("150"))

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    assert page.confirm_can_leave() is False
    assert page._view_stack.currentIndex() == 1


# -- Lot 14 (correctif) : détection des modifications réelles de la caisse --

def test_new_sale_with_lines_is_detected_as_unsaved(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    page._add_caisse_line(article.id, "ART-1 — x", Decimal("1"), Decimal("150"))

    assert page._caisse_has_unsaved_changes() is True


def test_new_sale_without_lines_is_not_unsaved(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()

    assert page._caisse_has_unsaved_changes() is False


def test_existing_draft_reopened_without_modification_is_not_unsaved(qtbot, login_as) -> None:
    """Le correctif de ce lot : rouvrir un brouillon existant tel quel ne
    doit jamais être traité comme une modification non enregistrée."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Client Test")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)

    page._on_edit_clicked()

    assert page._caisse_has_unsaved_changes() is False


def test_quantity_modification_on_existing_draft_is_detected(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))]
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_edit_clicked()
    assert page._caisse_has_unsaved_changes() is False

    page.caisse_lines_table.item(0, 1).setText("5")

    assert page._caisse_has_unsaved_changes() is True


def test_adding_a_line_on_existing_draft_is_detected(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article_a = _make_article(stack, reference="ART-A")
    article_b = _make_article(stack, reference="ART-B")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article_a.id, Decimal("2"), Decimal("150"))]
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_edit_clicked()

    page._add_caisse_line(article_b.id, "ART-B — y", Decimal("1"), Decimal("150"))

    assert page._caisse_has_unsaved_changes() is True


def test_removing_a_line_on_existing_draft_is_detected(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))]
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_edit_clicked()

    page.caisse_lines_table.selectRow(0)
    page._on_caisse_remove_line_clicked()

    assert page._caisse_has_unsaved_changes() is True


def test_date_modification_on_existing_draft_is_detected(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))]
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_edit_clicked()

    from PySide6.QtCore import QDate
    page.caisse_date_edit.setDate(QDate(2026, 1, 2))

    assert page._caisse_has_unsaved_changes() is True


def test_client_modification_on_existing_draft_is_detected(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    client = stack.clients.create_client("Nouveau client sélectionné")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))]
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_edit_clicked()

    index = page.caisse_client_combo.findData(client.id)
    page.caisse_client_combo.setCurrentIndex(index)

    assert page._caisse_has_unsaved_changes() is True


def test_reverting_to_initial_state_clears_unsaved_detection(qtbot, login_as) -> None:
    """§5 du correctif : ajouter puis supprimer la même ligne doit ramener
    la détection à « aucune modification », pas rester bloquée à vrai."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    assert page._caisse_has_unsaved_changes() is False

    page._add_caisse_line(article.id, "ART-1 — x", Decimal("1"), Decimal("150"))
    assert page._caisse_has_unsaved_changes() is True

    page.caisse_lines_table.selectRow(0)
    page._on_caisse_remove_line_clicked()

    assert page._caisse_has_unsaved_changes() is False


def test_reverting_quantity_to_original_value_clears_unsaved_detection(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))]
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_edit_clicked()

    page.caisse_lines_table.item(0, 1).setText("9")
    assert page._caisse_has_unsaved_changes() is True

    page.caisse_lines_table.item(0, 1).setText("2")
    assert page._caisse_has_unsaved_changes() is False


def test_successful_save_resets_reference_state_for_next_caisse_session(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("1"), Decimal("150"))

    page._on_caisse_save_draft_clicked()
    assert page._caisse_initial_snapshot is None  # caisse fermée, pas d'état de référence résiduel

    page._on_add_clicked()
    assert page._caisse_has_unsaved_changes() is False  # nouvelle session, repart de zéro


def test_failed_save_does_not_clear_or_corrupt_unsaved_detection(qtbot, login_as) -> None:
    """Un échec de create_sale/update_sale (ici : article désactivé entre
    l'ajout de la ligne et l'enregistrement) ne doit ni effacer la
    modification en cours, ni fausser la détection — la caisse reste
    ouverte, toujours détectée comme non enregistrée."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("2"), Decimal("150"))
    stack.articles.deactivate_article(article.id)

    page._on_caisse_save_draft_clicked()

    assert page._view_stack.currentIndex() == 1
    assert page._caisse_has_unsaved_changes() is True
    assert page._caisse_initial_snapshot is not None


def test_failed_validation_after_successful_save_does_not_corrupt_detection(qtbot, login_as) -> None:
    """Création réussie puis validation refusée (stock insuffisant) : la
    caisse se referme (le brouillon est conservé, retrouvable dans la
    liste) — vérifie que l'état de référence est bien réinitialisé plutôt
    que laissé dans un état incohérent."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("1"))
    page = _build_page(stack)
    qtbot.addWidget(page)
    page._on_add_clicked()
    page._add_caisse_line(article.id, "ART-1 — x", Decimal("999"), Decimal("150"))

    page._on_caisse_validate_clicked()

    assert page._view_stack.currentIndex() == 0
    assert page._caisse_initial_snapshot is None
    assert page._caisse_has_unsaved_changes() is False


def test_confirm_can_leave_true_for_unmodified_reopened_draft(qtbot, login_as) -> None:
    """Changement de module (confirm_can_leave) sans modification réelle :
    jamais de confirmation, même en mode édition d'un brouillon existant."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))]
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_edit_clicked()

    assert page.confirm_can_leave() is True


def test_confirm_can_leave_false_for_modified_reopened_draft_without_confirmation(
    qtbot, login_as, monkeypatch
) -> None:
    """Changement de module avec une modification réelle : la confirmation
    est demandée, et un refus bloque le départ."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))]
    )
    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == sale.numero)
    page.table.selectRow(row)
    page._on_edit_clicked()
    page.caisse_lines_table.item(0, 1).setText("3")

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    assert page.confirm_can_leave() is False
