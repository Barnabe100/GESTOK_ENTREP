from PySide6.QtWidgets import QListWidget, QListWidgetItem, QTableWidget

from app.views.design_system import apply_comfortable_list_height, apply_compact_row_height


def _table(rows: int) -> QTableWidget:
    table = QTableWidget(rows, 3)
    table.setHorizontalHeaderLabels(["A", "B", "C"])
    return table


# -- Mission 5.4 : apply_compact_row_height (plafond, pas plancher) -----------------


def test_empty_table_gets_header_only_height(qtbot) -> None:
    table = _table(0)

    apply_compact_row_height(table, visible_rows=2)

    header_height = table.horizontalHeader().sizeHint().height() or 32
    assert table.minimumHeight() == header_height + 12
    assert table.maximumHeight() == header_height + 12


def test_one_row_table_height_fits_exactly_one_row(qtbot) -> None:
    table = _table(1)

    apply_compact_row_height(table, visible_rows=2)

    header_height = table.horizontalHeader().sizeHint().height() or 32
    expected = header_height + 34 + 12
    assert table.minimumHeight() == expected
    assert table.maximumHeight() == expected


def test_height_caps_at_visible_rows_even_with_more_data(qtbot) -> None:
    two_rows = _table(2)
    five_rows = _table(5)

    apply_compact_row_height(two_rows, visible_rows=2)
    apply_compact_row_height(five_rows, visible_rows=2)

    assert two_rows.maximumHeight() == five_rows.maximumHeight()


def test_min_and_max_height_are_equal_for_deterministic_rendering(qtbot) -> None:
    table = _table(3)

    apply_compact_row_height(table, visible_rows=2)

    assert table.minimumHeight() == table.maximumHeight()


def test_recomputing_after_row_count_change_updates_height(qtbot) -> None:
    table = _table(0)
    apply_compact_row_height(table, visible_rows=2)
    empty_height = table.maximumHeight()

    table.setRowCount(2)
    apply_compact_row_height(table, visible_rows=2)

    assert table.maximumHeight() > empty_height


# -- Mission 5.4 : apply_comfortable_list_height (panneau de recherche) ------------


def _list_with_items(n: int) -> QListWidget:
    widget = QListWidget()
    for i in range(n):
        QListWidgetItem(f"Item {i}", widget)
    return widget


def test_list_height_uses_fallback_when_empty(qtbot) -> None:
    widget = _list_with_items(0)

    apply_comfortable_list_height(widget, visible_rows=5, fallback_row_height=24)

    assert widget.height() == 5 * 24 + 6


def test_list_height_self_calibrates_to_actual_row_height(qtbot) -> None:
    widget = _list_with_items(3)

    apply_comfortable_list_height(widget, visible_rows=5)

    row_height = widget.sizeHintForRow(0)
    assert row_height > 0
    assert widget.height() == 5 * row_height + 6
