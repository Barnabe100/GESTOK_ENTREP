from app.views.main_window import MainWindow


def test_main_window_administrateur_sees_all_modules(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Administrateur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    assert window.navigation_list.count() == 12
    assert window.visible_modules[0] == "Dashboard"


def test_main_window_starts_on_first_visible_module(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Administrateur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    assert window.navigation_list.currentRow() == 0
    assert window.page_stack.currentIndex() == 0
    assert window.page_title_label.text() == "Dashboard"


def test_navigation_switches_page_and_title(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Administrateur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    target_index = window.visible_modules.index("Ventes")
    window.navigation_list.setCurrentRow(target_index)

    assert window.page_stack.currentIndex() == target_index
    assert window.page_title_label.text() == "Ventes"


def test_window_has_expected_title(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Administrateur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    assert window.windowTitle() == "StockManager Desktop"


def test_top_bar_shows_current_user(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, current_user = login_as("Administrateur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    assert current_user.username in window.user_label.text()
    assert "Administrateur" in window.user_label.text()


def test_logout_button_logs_out_and_emits_signal(qtbot, login_as) -> None:
    auth_service, permission_service, user_service, _ = login_as("Administrateur")
    window = MainWindow(auth_service, permission_service, user_service)
    qtbot.addWidget(window)

    signal_received = []
    window.logout_requested.connect(lambda: signal_received.append(True))

    window.logout_button.click()

    assert signal_received == [True]
    assert auth_service.is_authenticated is False
