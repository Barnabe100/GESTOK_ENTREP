from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from app.models.enums import StatutOperation
from app.services.exits.exit_service import SortieLigneInput
from app.views.pages.exits_page import ExitsPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.exits_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.exits_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> ExitsPage:
    return ExitsPage(stack.exits, stack.exit_reasons, stack.articles, stack.permissions)


def _make_motif(stack, libelle="Perte"):
    return stack.exit_reasons.create_exit_reason(libelle)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("50")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def test_exits_page_lists_exits(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack)
    stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("10"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    numeros = {page.table.item(row, 0).text() for row in range(page.table.rowCount())}
    assert "SOR-000001" in numeros


def test_exits_page_search_filters_table(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif_a = _make_motif(stack, "Perte")
    motif_b = _make_motif(stack, "Casse")
    stack.exits.create_exit(motif_a.id, date(2026, 1, 1), [])
    stack.exits.create_exit(motif_b.id, date(2026, 1, 1), [])

    page = _build_page(stack)
    qtbot.addWidget(page)
    page.search_edit.setText("Perte")

    motifs = {page.table.item(row, 2).text() for row in range(page.table.rowCount())}
    assert motifs == {"Perte"}


def test_exits_page_status_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack)
    stack.exits.create_exit(motif.id, date(2026, 1, 1), [])
    to_validate = stack.exits.create_exit(
        motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))]
    )
    stack.exits.validate_exit(to_validate.id)

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
    motif = _make_motif(stack)
    article = _make_article(stack)
    draft = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))])

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == draft.numero)
    page.table.selectRow(row)

    assert page.edit_button.isEnabled() is True
    assert page.validate_button.isEnabled() is True
    assert page.cancel_button.isEnabled() is False


def test_cancel_button_enabled_only_for_validee_with_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack)
    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))])
    stack.exits.validate_exit(exit_.id)

    page = _build_page(stack)
    qtbot.addWidget(page)
    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == exit_.numero)
    page.table.selectRow(row)

    assert page.cancel_button.isEnabled() is True
    assert page.edit_button.isEnabled() is False
    assert page.validate_button.isEnabled() is False


def test_submit_form_creates_draft_exit_without_stock_impact(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "motif_id": motif.id, "date": "2026-01-01",
        "beneficiaire": "Service X", "reference": "REF-1", "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("10"), "cout_unitaire": Decimal("100")}],
    }

    result = page._submit_form(None, values)
    page.refresh()

    assert result is True
    created = stack.exits.list_exits(search="REF-1")[0]
    assert created.statut == StatutOperation.BROUILLON
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")


def test_submit_form_rejects_missing_motif(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "motif_id": None, "date": "2026-01-01",
        "beneficiaire": "", "reference": "", "commentaire": "", "lignes": [],
    }

    result = page._submit_form(None, values)

    assert result is False


def test_submit_form_rejects_invalid_date(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    values = {
        "motif_id": motif.id, "date": "pas une date",
        "beneficiaire": "", "reference": "", "commentaire": "", "lignes": [],
    }

    result = page._submit_form(None, values)

    assert result is False


def test_submit_form_updates_existing_draft(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack)
    page = _build_page(stack)
    qtbot.addWidget(page)

    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [])

    values = {
        "motif_id": motif.id, "date": "2026-02-01",
        "beneficiaire": "", "reference": "REF-2", "commentaire": "",
        "lignes": [{"article_id": article.id, "article_label": "x", "quantite": Decimal("3"), "cout_unitaire": Decimal("100")}],
    }

    result = page._submit_form(exit_.id, values)

    assert result is True
    updated = stack.exits.get_exit(exit_.id)
    assert updated.reference == "REF-2"
    assert len(updated.lignes) == 1


def test_load_edit_initial_returns_lines(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack)
    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("7"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    initial = page._load_edit_initial(exit_.id)

    assert initial is not None
    assert initial["motif_id"] == motif.id
    assert len(initial["lignes"]) == 1
    assert initial["lignes"][0]["article_id"] == article.id


def test_load_edit_initial_returns_none_on_error(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page._load_edit_initial(999999) is None


def test_load_exit_for_detail_includes_movements_after_validation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack)
    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("7"))])
    stack.exits.validate_exit(exit_.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._load_exit_for_detail(exit_.id)

    assert result is not None
    loaded_exit, movements = result
    assert loaded_exit.numero == exit_.numero
    assert len(movements) == 1


def test_validate_selected_updates_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))
    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("7"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(exit_.id)

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("43")


def test_validate_selected_refused_on_insufficient_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("5"))
    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("50"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._validate_selected(exit_.id)

    assert result is False
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("5")


def test_cancel_selected_restores_stock(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack, stock_initial=Decimal("50"))
    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("7"))])
    stack.exits.validate_exit(exit_.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    result = page._cancel_selected(exit_.id)

    assert result is True
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")


def test_cancel_selected_denied_without_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    motif = _make_motif(admin_stack)
    article = _make_article(admin_stack)
    exit_ = admin_stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("7"))])
    admin_stack.exits.validate_exit(exit_.id)

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    page = _build_page(gestionnaire_stack)
    qtbot.addWidget(page)

    result = page._cancel_selected(exit_.id)

    assert result is False
    assert admin_stack.exits.get_exit(exit_.id).statut == StatutOperation.VALIDEE


def test_confirmation_dialog_no_cancels_validate(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    motif = _make_motif(stack)
    article = _make_article(stack)
    exit_ = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("7"))])

    page = _build_page(stack)
    qtbot.addWidget(page)

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )

    row = next(r for r in range(page.table.rowCount()) if page.table.item(r, 0).text() == exit_.numero)
    page.table.selectRow(row)
    page._on_validate_clicked()

    assert stack.exits.get_exit(exit_.id).statut == StatutOperation.BROUILLON


def test_load_motifs_for_form_excludes_inactive(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    active = _make_motif(stack, "Actif")
    inactive = _make_motif(stack, "Inactif")
    stack.exit_reasons.deactivate_exit_reason(inactive.id)

    page = _build_page(stack)
    qtbot.addWidget(page)

    options = page._load_motifs_for_form()

    ids = {option[0] for option in options}
    assert active.id in ids
    assert inactive.id not in ids
