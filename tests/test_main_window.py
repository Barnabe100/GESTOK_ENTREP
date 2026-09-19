from app.views.main_window import MainWindow
from app.views.pages.dashboard_page import DashboardPage
from app.views.pages.reports_page import ReportsPage


def _build_window(stack) -> MainWindow:
    return MainWindow(stack)


def test_main_window_administrateur_sees_all_modules(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    window = _build_window(stack)
    qtbot.addWidget(window)

    assert window.navigation_list.count() == 18
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
