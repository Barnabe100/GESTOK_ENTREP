from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from app.models.enums import StatutOperation
from app.services.entries.entry_service import EntreeLigneInput
from app.views.pages.entries_page import EntriesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.entries_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.entries_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> EntriesPage:
    return EntriesPage(stack.entries, stack.suppliers, stack.articles, stack.permissions)


def _make_supplier(stack, nom="Fournisseur Test"):
    return stack.suppliers.create_supplier(nom)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("0")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def test_entries_page_lists_entries(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "ENT-000001" in numeros


def test_entries_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier_a = _make_supplier(stack, "Alpha")
    supplier_b = _make_supplier(stack, "Beta")
    stack.entries.create_entry(supplier_a.id, date(2026, 1, 1), [])
    stack.entries.create_entry(supplier_b.id, date(2026, 1, 1), [])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("Alpha")

    fournisseurs = {page.table.item(row, 2).text() for row in range(page.table.rowCount())}
    assert fournisseurs == {"Alpha"}


def test_entries_page_status_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    draft = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [])
    to_validate = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
    )
    stack.entries.validate_entry(to_validate.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    index = page.status_filter_combo.findData(StatutOperation.VALIDEE)
    page.status_filter_combo.setCurrentIndex(index)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert numeros == {to_validate.numero}


def test_add_button_enabled_for_gestionnaire_de_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is True


def test_add_button_disabled_for_vendeur(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is False


def test_action_buttons_reflect_selected_row_status(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    draft = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
    )

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == draft.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is True
    assert page.validate_button.isEnabled() is True
    assert page.cancel_button.isEnabled() is False


def test_cancel_button_enabled_only_for_validee_with_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == entry.numero)
    page.table.selectRow(row)

    assert page.cancel_button.isEnabled() is True
    assert page.edit_button.isEnabled() is False
    assert page.validate_button.isEnabled() is False


def test_submit_form_creates_draft_entry_without_stock_impact(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "fournisseur_id": supplier.id, "date": date(2026, 1, 1),
        "reference_document": "BL-1", "commentaire": "",
        "lignes": [
            {"article_id": article.id, "article_label": "x", "quantite": Decimal("10"), "prix_unitaire": Decimal("100")}
        ],
    }

    result = page._submit_form(None, values)
    page.refresh()

    assert result is True
    created = stack.entries.list_entries(search="BL-1")[0]
    assert created.statut == StatutOperation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("0")


def test_submit_form_rejects_missing_supplier(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "fournisseur_id": None, "date": date(2026, 1, 1),
        "reference_document": "", "commentaire": "", "lignes": [],
    }

    result = page._submit_form(None, values)

    assert result is False


def test_submit_form_updates_existing_draft(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [])

    values = {
        "fournisseur_id": supplier.id, "date": date(2026, 2, 1),
        "reference_document": "BL-2", "commentaire": "",
        "lignes": [
            {"article_id": article.id, "article_label": "x", "quantite": Decimal("3"), "prix_unitaire": Decimal("50")}
        ],
    }

    result = page._submit_form(entry.id, values)

    assert result is True
    updated = stack.entries.get_entry(entry.id)
    assert updated.reference_document == "BL-2"
    assert len(updated.lignes) == 1


def test_load_edit_initial_returns_lines(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("7"), Decimal("100"))]
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(entry.id)

    assert initial is not None
    assert initial["fournisseur_id"] == supplier.id
    assert initial["date"] == date(2026, 1, 1)
    assert len(initial["lignes"]) == 1
    assert initial["lignes"][0]["article_id"] == article.id


def test_load_edit_initial_returns_none_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._load_edit_initial(999999) is None


def test_load_entry_for_detail_includes_movements_after_validation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("7"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._load_entry_for_detail(entry.id)

    assert result is not None
    loaded_entry, movements = result
    assert loaded_entry.numero == entry.numero
    assert len(movements) == 1


def test_validate_selected_updates_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("7"), Decimal("100"))]
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(entry.id)

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("7")


def test_cancel_selected_reverts_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("7"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._cancel_selected(entry.id, "Motif de test valide")

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("0")


def test_cancel_selected_denied_without_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    supplier = _make_supplier(admin_stack)
    article = _make_article(admin_stack)
    entry = admin_stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("7"), Decimal("100"))]
    )
    admin_stack.entries.validate_entry(entry.id)

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    page = _build_page(gestionnaire_stack)
    qtbot.addWidget(page)

    result = page._cancel_selected(entry.id, "Motif de test valide")

    assert result is False
    assert admin_stack.entries.get_entry(entry.id).statut == StatutOperation.VALIDEE


def test_confirmation_dialog_no_cancels_validate(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("7"), Decimal("100"))]
    )

    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == entry.numero)
    page.table.selectRow(row)
    page._on_validate_clicked()

    assert stack.entries.get_entry(entry.id).statut == StatutOperation.BROUILLON


def test_on_cancel_clicked_opens_reason_dialog_and_passes_reason_to_service(
    qtbot, login_as, monkeypatch
) -> None:
    """§7 : l'annulation ne s'exécute jamais directement au clic sur
    « Annuler » — un dialogue de motif s'ouvre d'abord, et c'est son motif
    saisi qui est transmis au service."""
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("7"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    class _FakeReasonDialog:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

        def reason(self) -> str:
            return "Motif saisi via le dialogue"

    monkeypatch.setattr("app.views.pages.entries_page.CancellationReasonDialog", _FakeReasonDialog)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == entry.numero)
    page.table.selectRow(row)
    page._on_cancel_clicked()

    reloaded = stack.entries.get_entry(entry.id)
    assert reloaded.statut == StatutOperation.ANNULEE
    assert reloaded.annulation_motif == "Motif saisi via le dialogue"


def test_on_cancel_clicked_does_nothing_if_reason_dialog_rejected(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    supplier = _make_supplier(stack)
    article = _make_article(stack)
    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("7"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    class _FakeReasonDialog:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Rejected

        def reason(self) -> str:
            return ""

    monkeypatch.setattr("app.views.pages.entries_page.CancellationReasonDialog", _FakeReasonDialog)

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == entry.numero)
    page.table.selectRow(row)
    page._on_cancel_clicked()

    assert stack.entries.get_entry(entry.id).statut == StatutOperation.VALIDEE
