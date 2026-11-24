from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.views.design_system import (
    apply_comfortable_list_height,
    apply_compact_row_height,
    apply_content_driven_height,
)


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


# -- Mission 5.6, §1 : apply_content_driven_height (hauteur adaptée au contenu) ----


def _scrollable_dialog(n_lines: int) -> tuple[QDialog, QWidget, QPushButton]:
    """Reproduit le squelette commun à ``entry_detail_dialog.py``/
    ``exit_detail_dialog.py``/``inventory_detail_dialog.py``/
    ``client_detail_dialog.py`` : un ``QScrollArea`` défilant plus une ligne
    de boutons fixe en-dessous."""
    dialog = QDialog()
    layout = QVBoxLayout(dialog)

    scroll_area = QScrollArea(dialog)
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.Shape.NoFrame)
    content = QWidget(scroll_area)
    content_layout = QVBoxLayout(content)
    for i in range(n_lines):
        content_layout.addWidget(QLabel(f"Ligne {i}", content))
    scroll_area.setWidget(content)
    layout.addWidget(scroll_area)

    button_row = QHBoxLayout()
    button_row.addStretch(1)
    close_button = QPushButton("Fermer", dialog)
    button_row.addWidget(close_button)
    layout.addLayout(button_row)

    return dialog, content, close_button


def test_content_driven_height_grows_with_more_content(qtbot) -> None:
    short_dialog, short_content, short_button = _scrollable_dialog(1)
    apply_content_driven_height(short_dialog, short_content, 400, extra_height=short_button.sizeHint().height())

    tall_dialog, tall_content, tall_button = _scrollable_dialog(10)
    apply_content_driven_height(tall_dialog, tall_content, 400, extra_height=tall_button.sizeHint().height())

    assert tall_dialog.height() > short_dialog.height()


def test_content_driven_height_sets_the_requested_width(qtbot) -> None:
    dialog, content, button = _scrollable_dialog(1)

    apply_content_driven_height(dialog, content, 555, extra_height=button.sizeHint().height())

    assert dialog.width() == 555


def test_content_driven_height_leaves_no_large_empty_space(qtbot) -> None:
    """Le défilement reste fonctionnel (``show`` au-delà) mais la hauteur
    initiale ne doit pas réserver un espace disproportionné par rapport au
    contenu réel — non-régression du grand espace vide (Mission 5.6, §1)."""
    dialog, content, button = _scrollable_dialog(1)

    apply_content_driven_height(dialog, content, 400, extra_height=button.sizeHint().height())
    dialog.show()

    scroll_area = dialog.findChild(QScrollArea)
    assert scroll_area.verticalScrollBar().maximum() == 0
