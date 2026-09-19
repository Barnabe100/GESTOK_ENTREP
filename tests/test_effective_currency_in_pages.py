"""Vérifie que les pages formatant des montants utilisent bien la devise
configurée dans Paramètres (``get_effective_currency``) plutôt que la seule
devise par défaut du processus (§5 du lot Paramètres) — sans toucher à la
moindre logique de calcul monétaire, uniquement la source de la devise
affichée.
"""
from __future__ import annotations

import pytest

from app.views.pages.articles_page import ArticlesPage
from app.views.pages.dashboard_page import DashboardPage
from app.views.pages.entries_page import EntriesPage
from app.views.pages.exits_page import ExitsPage
from app.views.pages.reports_page import ReportsPage
from app.views.pages.sales_page import SalesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (
        "app.views.pages.articles_page", "app.views.pages.dashboard_page", "app.views.pages.entries_page",
        "app.views.pages.exits_page", "app.views.pages.reports_page", "app.views.pages.sales_page",
    ):
        monkeypatch.setattr(f"{module}.QMessageBox.information", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(f"{module}.QMessageBox.warning", lambda *a, **k: None, raising=False)


def test_pages_default_to_settings_default_currency_when_unconfigured(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")

    pages = [
        DashboardPage(stack.dashboard, stack.permissions),
        ArticlesPage(stack.articles, stack.categories, stack.suppliers, stack.permissions),
        EntriesPage(stack.entries, stack.suppliers, stack.articles, stack.permissions),
        ExitsPage(stack.exits, stack.exit_reasons, stack.articles, stack.permissions),
        SalesPage(stack.sales, stack.articles, stack.clients, stack.documents, stack.permissions),
        ReportsPage(stack.reports, stack.categories, stack.articles, stack.exit_reasons, stack.permissions),
    ]
    for page in pages:
        qtbot.addWidget(page)
        assert page._currency_code == "XOF"


def test_pages_reflect_currency_configured_in_parameters(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.update_config(nom="Société", adresse=None, telephone=None, email=None, devise="EUR")

    pages = [
        DashboardPage(stack.dashboard, stack.permissions),
        ArticlesPage(stack.articles, stack.categories, stack.suppliers, stack.permissions),
        EntriesPage(stack.entries, stack.suppliers, stack.articles, stack.permissions),
        ExitsPage(stack.exits, stack.exit_reasons, stack.articles, stack.permissions),
        SalesPage(stack.sales, stack.articles, stack.clients, stack.documents, stack.permissions),
        ReportsPage(stack.reports, stack.categories, stack.articles, stack.exit_reasons, stack.permissions),
    ]
    for page in pages:
        qtbot.addWidget(page)
        assert page._currency_code == "EUR"
