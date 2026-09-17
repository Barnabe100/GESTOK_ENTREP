from app.views.main_window import NAVIGATION_MODULES, MainWindow


def test_main_window_builds_all_navigation_items(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.navigation_list.count() == len(NAVIGATION_MODULES)
    labels = [window.navigation_list.item(i).text() for i in range(window.navigation_list.count())]
    assert labels == NAVIGATION_MODULES


def test_main_window_starts_on_dashboard(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.navigation_list.currentRow() == 0
    assert window.page_stack.currentIndex() == 0
    assert window.page_title_label.text() == "Dashboard"


def test_navigation_switches_page_and_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    target_index = NAVIGATION_MODULES.index("Ventes")
    window.navigation_list.setCurrentRow(target_index)

    assert window.page_stack.currentIndex() == target_index
    assert window.page_title_label.text() == "Ventes"


def test_window_has_expected_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "StockManager Desktop"


def test_all_pages_are_placeholder_widgets_without_business_logic(qtbot) -> None:
    from app.views.pages.placeholder_page import PlaceholderPage

    window = MainWindow()
    qtbot.addWidget(window)

    for index in range(window.page_stack.count()):
        assert isinstance(window.page_stack.widget(index), PlaceholderPage)
