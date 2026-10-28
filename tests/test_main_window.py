from datetime import date
from decimal import Decimal

import pytest

from app.db.seed import INITIAL_ADMIN_USERNAME
from app.services.sales.sale_service import VenteLigneInput
from app.views.about_dialog import AboutDialog
from app.views.main_window import MainWindow
from app.views.onboarding_dialog import OnboardingDialog
from app.views.pages.dashboard_page import DashboardPage
from app.views.pages.locations_page import LocationsPage
from app.views.pages.placeholder_page import PlaceholderPage
from app.views.pages.reports_page import ReportsPage


def _build_window(stack) -> MainWindow:
    return MainWindow(stack)


def test_main_window_administrateur_sees_all_modules(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    # Lot D : +1 module ("Base de données", DATABASE_CONFIG_VIEW — Administrateur uniquement).
    assert window.navigation_list.count() == 21
    assert window.visible_modules[0] == "Dashboard"


def test_main_window_starts_on_first_visible_module(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.navigation_list.currentRow() == 0
    assert window.page_stack.currentIndex() == 0
    assert window.page_title_label.text() == "Dashboard"


def test_navigation_switches_page_and_title(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    target_index = window.visible_modules.index("Ventes")
    window.navigation_list.setCurrentRow(target_index)

    assert window.page_stack.currentIndex() == target_index
    assert window.page_title_label.text() == "Ventes"


def test_navigating_to_receivables_refreshes_payment_made_on_another_page(qtbot, login_as) -> None:
    """Reproduction du bug « Créances » (voir diagnostic) : un paiement
    enregistré alors que la page Créances est déjà construite (comme dans
    le QStackedWidget persistant de MainWindow) doit être visible dès qu'on
    y navigue — sans qu'il soit nécessaire de recréer la fenêtre."""
    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("50"),
    )
    client = stack.clients.create_client("Client Test")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("62500"))], client_id=client.id
    )
    validated = stack.sales.validate_sale(sale.id, Decimal("0"))  # validée, non payée

    window = _build_window(stack)
    qtbot.addWidget(window)

    receivables_index = window.visible_modules.index("Créances")
    ventes_index = window.visible_modules.index("Ventes")
    # Visite initiale de Créances : construit ET rafraîchit la page une
    # première fois, avec la vente encore non payée à ce moment.
    window.navigation_list.setCurrentRow(receivables_index)
    receivables_page = window.page_stack.widget(receivables_index)
    # Ce test porte sur la réactivité de la navigation, pas sur le filtre
    # par défaut : on sélectionne explicitement « Toutes » pour continuer à
    # voir la vente une fois qu'elle passera à Payée (le filtre par défaut
    # « En cours » l'exclurait alors).
    all_index = receivables_page.statut_paiement_combo.findData(None)
    receivables_page.statut_paiement_combo.setCurrentIndex(all_index)
    assert receivables_page.table.item(0, 6).text() == "Non payée"

    # Le paiement est enregistré « ailleurs » (ex. depuis SaleDetailDialog
    # sur la page Ventes) pendant que la page Créances reste construite en
    # arrière-plan dans le QStackedWidget.
    window.navigation_list.setCurrentRow(ventes_index)
    stack.sales.record_payment(validated.id, Decimal("62500"))

    # Retour sur Créances : doit refléter le paiement, pas l'état figé.
    window.navigation_list.setCurrentRow(receivables_index)

    assert receivables_page.table.item(0, 4).text() == "62 500 FCFA"
    assert receivables_page.table.item(0, 5).text() == "0 FCFA"
    assert receivables_page.table.item(0, 6).text() == "Payée"


def test_navigation_changed_does_not_crash_for_page_without_refresh(qtbot, login_as, monkeypatch) -> None:
    """Certaines pages (ex. PlaceholderPage, modules pas encore
    implémentés) n'exposent pas de refresh() — la navigation ne doit
    jamais planter dans ce cas."""
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    placeholder = PlaceholderPage("Module de test")
    assert not hasattr(placeholder, "refresh")
    monkeypatch.setattr(window.page_stack, "widget", lambda index: placeholder)

    window._on_navigation_changed(0)  # ne doit lever aucune exception


def test_window_has_expected_title(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.windowTitle() == "StockManager Desktop"


def test_top_bar_shows_current_user(qtbot, login_as) -> None:
    stack, current_user = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert current_user.username in window.user_label.text()
    assert "Administrateur" in window.user_label.text()


def test_logout_button_logs_out_and_emits_signal(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    signal_received = []
    window.logout_requested.connect(lambda: signal_received.append(True))

    window.logout_button.click()

    assert signal_received == [True]
    assert stack.auth.is_authenticated is False


# -- « À propos » (Lot P) --------------------------------------------------------------


def test_about_button_present_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert hasattr(window, "about_button")
    assert window.about_button.isEnabled() is True


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_about_button_accessible_to_every_connected_role(qtbot, login_as, role_name: str) -> None:
    """Le bouton « À propos » n'est gardé par aucune permission : accessible
    à tout utilisateur connecté, quel que soit son rôle."""
    stack, _ = login_as(role_name)
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.about_button.isEnabled() is True


def test_about_button_click_opens_about_dialog(qtbot, login_as, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    opened: list[object] = []
    monkeypatch.setattr(AboutDialog, "exec", lambda self: opened.append(self) or 0)

    window.about_button.click()

    assert len(opened) == 1
    assert isinstance(opened[0], AboutDialog)


def test_about_button_does_not_regress_other_top_bar_buttons(qtbot, login_as, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    monkeypatch.setattr(AboutDialog, "exec", lambda self: 0)
    window.about_button.click()

    assert window.change_password_button.isEnabled() is True
    assert window.logout_button.isEnabled() is True

    signal_received = []
    window.logout_requested.connect(lambda: signal_received.append(True))
    window.logout_button.click()
    assert signal_received == [True]


# -- guide de démarrage (Lot O) ----------------------------------------------------------


def test_onboarding_button_present_and_enabled_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert hasattr(window, "onboarding_button")
    assert window.onboarding_button.isEnabled() is True


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_onboarding_button_disabled_without_settings_view(qtbot, login_as, role_name: str) -> None:
    stack, _ = login_as(role_name)
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.onboarding_button.isEnabled() is False


def test_onboarding_button_click_opens_onboarding_dialog(qtbot, login_as, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    opened: list[object] = []
    monkeypatch.setattr(OnboardingDialog, "exec", lambda self: opened.append(self) or 0)

    window.onboarding_button.click()

    assert len(opened) == 1
    assert isinstance(opened[0], OnboardingDialog)


def test_onboarding_dialog_auto_shown_on_initial_admin_first_login(
    qtbot, make_user, make_stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§Lot O : uniquement pour le compte administrateur initial (identifiant
    exact ``admin``), jamais pour un compte créé via ``login_as``."""
    make_user("Administrateur", INITIAL_ADMIN_USERNAME, "MotDePasse!23")
    stack = make_stack()
    stack.auth.login(INITIAL_ADMIN_USERNAME, "MotDePasse!23")

    opened: list[object] = []
    monkeypatch.setattr(OnboardingDialog, "exec", lambda self: opened.append(self) or 0)

    window = _build_window(stack)
    qtbot.addWidget(window)

    assert len(opened) == 1


def test_onboarding_dialog_not_auto_shown_for_a_regular_administrateur_login(
    qtbot, login_as, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack, _ = login_as("Administrateur")

    opened: list[object] = []
    monkeypatch.setattr(OnboardingDialog, "exec", lambda self: opened.append(self) or 0)

    window = _build_window(stack)
    qtbot.addWidget(window)

    assert opened == []


def test_onboarding_dialog_not_auto_shown_once_already_completed(
    qtbot, make_user, make_stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_user("Administrateur", INITIAL_ADMIN_USERNAME, "MotDePasse!23")
    stack = make_stack()
    stack.auth.login(INITIAL_ADMIN_USERNAME, "MotDePasse!23")
    stack.onboarding.mark_completed()

    opened: list[object] = []
    monkeypatch.setattr(OnboardingDialog, "exec", lambda self: opened.append(self) or 0)

    window = _build_window(stack)
    qtbot.addWidget(window)

    assert opened == []


def test_onboarding_manual_reopen_works_even_after_automatic_dismissal(
    qtbot, make_user, make_stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La réouverture manuelle reste possible même une fois le guidage
    automatique définitivement marqué terminé — ce n'est pas la même porte
    d'entrée que le déclenchement automatique."""
    make_user("Administrateur", INITIAL_ADMIN_USERNAME, "MotDePasse!23")
    stack = make_stack()
    stack.auth.login(INITIAL_ADMIN_USERNAME, "MotDePasse!23")
    stack.onboarding.mark_completed()

    opened: list[object] = []
    monkeypatch.setattr(OnboardingDialog, "exec", lambda self: opened.append(self) or 0)

    window = _build_window(stack)
    qtbot.addWidget(window)
    assert opened == []  # non déclenché automatiquement

    window.onboarding_button.click()

    assert len(opened) == 1


def test_onboarding_does_not_regress_other_top_bar_buttons(qtbot, login_as, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    monkeypatch.setattr(OnboardingDialog, "exec", lambda self: 0)
    window.onboarding_button.click()

    assert window.about_button.isEnabled() is True
    assert window.change_password_button.isEnabled() is True
    assert window.logout_button.isEnabled() is True


def test_dashboard_module_renders_a_real_dashboard_page(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    dashboard_index = window.visible_modules.index("Dashboard")
    assert isinstance(window.page_stack.widget(dashboard_index), DashboardPage)


def test_switch_to_module_moves_navigation_and_returns_true(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    result = window.switch_to_module("Ventes")

    assert result is True
    assert window.page_stack.currentIndex() == window.visible_modules.index("Ventes")


def test_switch_to_module_returns_false_for_a_module_the_user_cannot_see(qtbot, login_as) -> None:
    stack, _ = login_as("Vendeur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    result = window.switch_to_module("Utilisateurs")

    assert result is False


def test_switch_to_module_with_report_preset_preselects_report_type(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    window.switch_to_module("Rapports", "Stock faible")

    reports_index = window.visible_modules.index("Rapports")
    reports_page = window.page_stack.widget(reports_index)
    assert isinstance(reports_page, ReportsPage)
    assert reports_page.report_combo.currentText() == "Stock faible"


def test_dashboard_navigate_callback_switches_main_window_tab(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    dashboard_index = window.visible_modules.index("Dashboard")
    dashboard_page = window.page_stack.widget(dashboard_index)
    assert isinstance(dashboard_page, DashboardPage)

    dashboard_page.navigation_buttons["Ventes"].click()

    assert window.page_stack.currentIndex() == window.visible_modules.index("Ventes")


# -- Lot 14 : hook confirm_can_leave (écran de caisse) -----------------------

def test_navigation_respects_confirm_can_leave_refusal(qtbot, login_as, monkeypatch) -> None:
    """Hook optionnel (voir SalesPage.confirm_can_leave) : si la page
    courante refuse, la navigation reste sur place — ni le contenu affiché
    ni le titre ne doivent changer."""
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    class _RefusingPage:
        def confirm_can_leave(self) -> bool:
            return False

    dashboard_index = window.navigation_list.currentRow()
    monkeypatch.setattr(window.page_stack, "widget", lambda index: _RefusingPage())

    target_index = window.visible_modules.index("Ventes")
    window.navigation_list.setCurrentRow(target_index)

    assert window.navigation_list.currentRow() == dashboard_index
    assert window.page_stack.currentIndex() == dashboard_index
    assert window.page_title_label.text() == "Dashboard"


def test_navigation_allows_leave_when_confirm_can_leave_returns_true(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    class _AllowingPage:
        def confirm_can_leave(self) -> bool:
            return True

        def refresh(self) -> None:
            pass

    monkeypatch.setattr(window.page_stack, "widget", lambda index: _AllowingPage())

    target_index = window.visible_modules.index("Ventes")
    window.navigation_list.setCurrentRow(target_index)

    assert window.page_stack.currentIndex() == target_index
    assert window.page_title_label.text() == "Ventes"


def test_navigation_away_from_caisse_with_unsaved_sale_is_blocked_until_confirmed(
    qtbot, login_as, monkeypatch
) -> None:
    """Scénario de bout en bout : la caisse (SalesPage) contient une ligne
    non enregistrée, l'utilisateur clique sur un autre module — la
    navigation doit être bloquée tant que l'abandon n'est pas confirmé."""
    from PySide6.QtWidgets import QMessageBox

    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("Boissons")
    article = stack.articles.create_article(
        "ART-1", "Eau", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
        stock_initial=Decimal("50"),
    )
    window = _build_window(stack)
    qtbot.addWidget(window)

    ventes_index = window.visible_modules.index("Ventes")
    window.navigation_list.setCurrentRow(ventes_index)
    sales_page = window.page_stack.widget(ventes_index)
    sales_page._on_add_clicked()
    sales_page._add_caisse_line(article.id, "ART-1 — Eau", Decimal("1"), Decimal("150"))

    articles_index = window.visible_modules.index("Articles")
    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    window.navigation_list.setCurrentRow(articles_index)
    assert window.page_stack.currentIndex() == ventes_index  # bloqué : refus

    monkeypatch.setattr(
        "app.views.common.QMessageBox.question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    window.navigation_list.setCurrentRow(articles_index)
    assert window.page_stack.currentIndex() == articles_index  # confirmé : autorisé


# -- module Location, activation/désactivation (Lot 16) -----------------------------


def test_locations_entry_visible_when_module_active_and_permission_present(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_rental_module_enabled(True)

    window = _build_window(stack)
    qtbot.addWidget(window)

    assert "Locations" in window.visible_modules


def test_locations_entry_hidden_when_module_disabled(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_rental_module_enabled(False)

    window = _build_window(stack)
    qtbot.addWidget(window)

    assert "Locations" not in window.visible_modules
    # Lot D : +1 module ("Base de données") par rapport au compte historique (20 - 1 Locations + 1).
    assert window.navigation_list.count() == 20


def test_other_modules_unaffected_by_locations_deactivation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_rental_module_enabled(False)

    window = _build_window(stack)
    qtbot.addWidget(window)

    for module in (
        "Dashboard", "Articles", "Ventes", "Créances", "Clients", "Paramètres", "Rapports", "Licences",
    ):
        assert module in window.visible_modules


def test_readonly_locations_button_hidden_when_module_active(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_rental_module_enabled(True)

    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.locations_readonly_button.isHidden() is True


def test_readonly_locations_button_visible_when_module_disabled_with_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_rental_module_enabled(False)

    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.locations_readonly_button.isHidden() is False


def test_readonly_locations_button_hidden_without_location_view_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    admin_stack.parameters.set_rental_module_enabled(False)
    role_id = next(r.id for r in admin_stack.roles.list_roles() if r.nom == "Vendeur")
    current_codes = admin_stack.roles.get_role_permissions(role_id)
    admin_stack.roles.update_role_permissions(role_id, [c for c in current_codes if c != "LOCATION_VIEW"])

    stack, _ = login_as("Vendeur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.locations_readonly_button.isHidden() is True


def test_readonly_locations_dialog_builds_read_only_page(qtbot, login_as, monkeypatch) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.set_rental_module_enabled(False)

    window = _build_window(stack)
    qtbot.addWidget(window)

    monkeypatch.setattr("app.views.main_window.QDialog.exec", lambda self: None)
    captured: list[LocationsPage] = []
    monkeypatch.setattr(
        "app.views.main_window.LocationsPage",
        lambda *a, **k: captured.append(LocationsPage(*a, **k)) or captured[-1],
    )

    window._on_open_locations_readonly_clicked()

    assert len(captured) == 1
    page = captured[0]
    assert page._read_only is True
    assert page.add_button.isEnabled() is False


def test_readonly_locations_page_does_not_expose_mutating_actions(qtbot, login_as) -> None:
    """Le chemin de consultation ne doit permettre aucune création, ni
    modification, ni action mutante — seule la consultation reste active."""
    stack, _ = login_as("Administrateur")
    page = LocationsPage(
        stack.rentals, stack.articles, stack.clients, stack.permissions, read_only=True,
    )
    qtbot.addWidget(page)

    assert page.add_button.isEnabled() is False
    assert page.edit_button.isEnabled() is False
    assert page.delete_button.isEnabled() is False
    # La consultation elle-même (détail) reste accessible.
    assert page.detail_button is not None


# -- Lot 22 (anomalie B) : stabilité de la taille de la fenêtre -----------------------


def test_main_window_has_minimum_size_matching_initial_size(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.minimumSize().width() == 1200
    assert window.minimumSize().height() == 750


def test_window_size_unchanged_across_every_module_navigation(qtbot, login_as) -> None:
    """Reproduit le scénario de recette (anomalie B) : parcourir tous les
    modules visibles l'un après l'autre ne doit jamais réduire ni modifier
    la taille de la fenêtre, y compris pour un module affiché pour la
    première fois."""
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)
    window.resize(1200, 750)
    initial_size = window.size()

    for index in range(len(window.visible_modules)):
        window.navigation_list.setCurrentRow(index)
        assert window.size() == initial_size, (
            f"La fenêtre a changé de taille en affichant « {window.visible_modules[index]} »"
        )

    # Un second passage (pages déjà affichées une première fois) ne doit
    # pas non plus modifier la taille.
    for index in reversed(range(len(window.visible_modules))):
        window.navigation_list.setCurrentRow(index)
        assert window.size() == initial_size


def test_window_cannot_be_resized_below_minimum_via_module_switch(qtbot, login_as) -> None:
    """Même en partant d'une fenêtre explicitement agrandie, parcourir les
    modules ne doit jamais la faire redescendre sous sa taille minimale."""
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)
    window.resize(1600, 900)

    for index in range(len(window.visible_modules)):
        window.navigation_list.setCurrentRow(index)
        assert window.size().width() >= 1200
        assert window.size().height() >= 750


# -- correctif revue finale (Point 3) : réactivité pendant la construction --
#
# La construction de toutes les pages (plusieurs secondes, voir la revue de
# ce lot) est désormais entrecoupée d'appels à ``QApplication.processEvents()``
# plutôt qu'un seul appel avant toute la boucle — c'est ce qui permet au
# voile de transition (``StartupSplash``, voir app/main.py) de réellement
# s'animer pendant cette construction, et réduit le risque qu'un délai sans
# traitement de message dépasse le seuil « Ne répond pas » de Windows.


def test_page_construction_pumps_the_event_loop_between_each_page(qtbot, login_as, monkeypatch) -> None:
    call_count = {"n": 0}

    def _counting_process_events(*args, **kwargs) -> None:
        call_count["n"] += 1

    monkeypatch.setattr("app.views.main_window.QApplication.processEvents", _counting_process_events)

    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    # Au moins un appel par page construite — jamais un seul appel global
    # avant toute la boucle (ce qui laisserait le spinner figé pendant
    # toute la construction, voir la revue de ce lot).
    assert call_count["n"] >= len(window.visible_modules)
