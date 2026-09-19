from datetime import date

from PySide6.QtCore import QDate

from app.views.optional_date_edit import OptionalDateEdit


def test_initial_state_is_unchecked_disabled_and_returns_none(qtbot) -> None:
    widget = OptionalDateEdit()
    qtbot.addWidget(widget)

    assert widget.checkbox.isChecked() is False
    assert widget.date_edit.isEnabled() is False
    assert widget.date_or_none() is None


def test_set_date_or_none_with_a_date_checks_and_enables(qtbot) -> None:
    widget = OptionalDateEdit()
    qtbot.addWidget(widget)

    widget.set_date_or_none(date(2026, 3, 17))

    assert widget.checkbox.isChecked() is True
    assert widget.date_edit.isEnabled() is True
    assert widget.date_edit.date() == QDate(2026, 3, 17)
    assert widget.date_or_none() == date(2026, 3, 17)


def test_set_date_or_none_with_none_unchecks_and_disables(qtbot) -> None:
    widget = OptionalDateEdit()
    qtbot.addWidget(widget)
    widget.set_date_or_none(date(2026, 3, 17))

    widget.set_date_or_none(None)

    assert widget.checkbox.isChecked() is False
    assert widget.date_edit.isEnabled() is False
    assert widget.date_or_none() is None


def test_manually_checking_enables_date_and_returns_it(qtbot) -> None:
    widget = OptionalDateEdit()
    qtbot.addWidget(widget)
    widget.date_edit.setDate(QDate(2026, 5, 1))

    widget.checkbox.setChecked(True)

    assert widget.date_edit.isEnabled() is True
    assert widget.date_or_none() == date(2026, 5, 1)


def test_manually_unchecking_disables_and_returns_none(qtbot) -> None:
    widget = OptionalDateEdit()
    qtbot.addWidget(widget)
    widget.set_date_or_none(date(2026, 5, 1))

    widget.checkbox.setChecked(False)

    assert widget.date_edit.isEnabled() is False
    assert widget.date_or_none() is None


def test_display_format_is_yyyy_mm_dd(qtbot) -> None:
    widget = OptionalDateEdit()
    qtbot.addWidget(widget)

    assert widget.date_edit.displayFormat() == "yyyy-MM-dd"


def test_calendar_popup_is_enabled(qtbot) -> None:
    widget = OptionalDateEdit()
    qtbot.addWidget(widget)

    assert widget.date_edit.calendarPopup() is True


def test_date_stays_memorized_after_unchecking_and_recovered_on_recheck(qtbot) -> None:
    widget = OptionalDateEdit()
    qtbot.addWidget(widget)
    widget.set_date_or_none(date(2026, 7, 4))

    widget.checkbox.setChecked(False)
    assert widget.date_or_none() is None
    assert widget.date_edit.date() == QDate(2026, 7, 4)  # toujours mémorisée dans le widget

    widget.checkbox.setChecked(True)

    assert widget.date_or_none() == date(2026, 7, 4)
