from datetime import date, timedelta
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QTableWidget

from app.views.audit_detail_dialog import AuditDetailDialog
from app.views.pages.audit_page import AuditPage, _DEFAULT_PERIOD_DAYS


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.pages.audit_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.audit_page.QMessageBox.warning", lambda *a, **k: None)


def _build_page(stack) -> AuditPage:
    return AuditPage(stack.audit, stack.permissions)


def _make_article(stack, reference="ART-1"):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
    )


# -- affichage --------------------------------------------------------------------------


def test_page_lists_audits_on_load(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")

    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.rowCount() >= 1  # au moins l'entrée LOGIN du login_as
    assert "entrée" in page.summary_label.text()


def test_columns_include_required_fields(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
    for expected in ["Date/heure", "Utilisateur", "Action", "Entité", "Référence", "Résultat", "Détails"]:
        assert expected in headers


def test_page_has_no_edit_or_delete_controls(qtbot, login_as) -> None:
    """Lecture seule stricte (Lot B) : aucune action de modification/suppression."""
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert not hasattr(page, "edit_button")
    assert not hasattr(page, "delete_button")
    assert not hasattr(page, "add_button")
    assert page.table.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers


# -- permissions / licence ---------------------------------------------------------------


def test_consultation_role_cannot_view_audit(qtbot, login_as) -> None:
    """Consultation n'a pas AUDIT_VIEW (seule Administrateur l'a) : la page,
    si elle était atteinte, n'affiche rien."""
    stack, _ = login_as("Consultation")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 0


# -- période par défaut -------------------------------------------------------------------


def test_default_period_is_last_30_days(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")

    page = _build_page(stack)
    qtbot.addWidget(page)

    today = date.today()
    expected_from = (today - timedelta(days=_DEFAULT_PERIOD_DAYS)).isoformat()
    assert page.date_from_edit.text() == expected_from
    assert page.date_to_edit.text() == today.isoformat()


def test_default_period_notice_is_visible(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    assert str(_DEFAULT_PERIOD_DAYS) in page.period_notice_label.text()


def test_reset_filters_restores_default_period(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    page.date_from_edit.setText("2020-01-01")
    page.date_to_edit.setText("2020-01-02")
    page.search_edit.setText("quelque chose")
    page.refresh()

    page._on_reset_filters_clicked()

    today = date.today()
    assert page.date_from_edit.text() == (today - timedelta(days=_DEFAULT_PERIOD_DAYS)).isoformat()
    assert page.date_to_edit.text() == today.isoformat()
    assert page.search_edit.text() == ""


# -- accès à l'historique complet ----------------------------------------------------------


def test_clearing_date_fields_gives_access_to_full_history(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)
    rows_within_default_period = page.table.rowCount()

    page.date_from_edit.setText("2000-01-01")
    page.refresh()

    # Toujours au moins autant de lignes (jamais moins) une fois la période
    # étendue à un historique bien plus large que la fenêtre par défaut.
    assert page.table.rowCount() >= rows_within_default_period


# -- filtres ----------------------------------------------------------------------------


def test_entite_filter_narrows_results(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    index = page.entite_filter_combo.findText("articles")
    assert index != -1
    page.entite_filter_combo.setCurrentIndex(index)
    page.refresh()

    assert page.table.rowCount() == 1
    assert page.table.item(0, 3).text() == "articles"


def test_search_filters_by_action(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)

    page = _build_page(stack)
    qtbot.addWidget(page)

    page.search_edit.setText("ARTICLE_CREATE")
    page.refresh()

    assert page.table.rowCount() == 1
    assert page.table.item(0, 2).text() == "ARTICLE_CREATE"


# -- sélection / détail -------------------------------------------------------------------


def test_double_click_opens_detail_dialog(qtbot, login_as, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    opened: list[object] = []
    monkeypatch.setattr(AuditDetailDialog, "exec", lambda self: opened.append(self) or 0)

    page._on_row_double_clicked(0, 0)

    assert len(opened) == 1
    assert isinstance(opened[0], AuditDetailDialog)


def test_double_click_out_of_range_does_nothing(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    page = _build_page(stack)
    qtbot.addWidget(page)

    # Ne doit pas lever, même hors bornes.
    page._on_row_double_clicked(9999, 0)
    page._on_row_double_clicked(-1, 0)


# -- sécurité : aucun secret affiché --------------------------------------------------------


def test_no_password_ever_shown_in_table_after_password_reset(qtbot, login_as, make_user) -> None:
    make_user("Vendeur", "cible_secu")
    stack, _ = login_as("Administrateur")
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_secu")
    stack.users.reset_password(target_id, "NouveauMotDePasseSecret99")

    page = _build_page(stack)
    qtbot.addWidget(page)

    for row in range(page.table.rowCount()):
        for column in range(page.table.columnCount()):
            item = page.table.item(row, column)
            text = item.text() if item is not None else ""
            assert "NouveauMotDePasseSecret99" not in text
