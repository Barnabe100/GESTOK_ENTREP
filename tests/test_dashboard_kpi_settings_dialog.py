"""Tests de ``DashboardKpiSettingsDialog`` (Mission 3, §6.2)."""
from app.views.dashboard_kpi_settings_dialog import DashboardKpiSettingsDialog, KpiOption

_OPTIONS = [
    KpiOption("articles", "Articles actifs", "Stock"),
    KpiOption("stock_value", "Valeur du stock", "Stock"),
    KpiOption("sales_amount", "Chiffre d'affaires", "Activité commerciale"),
    KpiOption("rental_count", "Locations", "Locations"),
]


def test_checkboxes_reflect_initial_selection(qtbot) -> None:
    dialog = DashboardKpiSettingsDialog(_OPTIONS, ["articles", "rental_count"], ["articles", "stock_value"])
    qtbot.addWidget(dialog)

    assert dialog._checkboxes["articles"].isChecked() is True
    assert dialog._checkboxes["stock_value"].isChecked() is False
    assert dialog._checkboxes["rental_count"].isChecked() is True


def test_selected_ids_returns_only_checked_options(qtbot) -> None:
    dialog = DashboardKpiSettingsDialog(_OPTIONS, ["articles"], ["articles"])
    qtbot.addWidget(dialog)

    dialog._checkboxes["sales_amount"].setChecked(True)
    dialog._checkboxes["articles"].setChecked(False)

    assert dialog.selected_ids() == ["sales_amount"]


def test_reset_button_restores_default_selection(qtbot) -> None:
    dialog = DashboardKpiSettingsDialog(_OPTIONS, ["rental_count"], ["articles", "stock_value"])
    qtbot.addWidget(dialog)

    dialog.reset_button.click()

    assert set(dialog.selected_ids()) == {"articles", "stock_value"}


def test_options_are_grouped_by_category(qtbot) -> None:
    from PySide6.QtWidgets import QGroupBox

    dialog = DashboardKpiSettingsDialog(_OPTIONS, [], [])
    qtbot.addWidget(dialog)

    group_titles = {g.title() for g in dialog.findChildren(QGroupBox)}
    assert group_titles == {"Stock", "Activité commerciale", "Locations"}


def test_cancel_rejects_and_save_accepts(qtbot) -> None:
    from PySide6.QtWidgets import QDialog

    dialog = DashboardKpiSettingsDialog(_OPTIONS, [], [])
    qtbot.addWidget(dialog)
    dialog.save_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted

    dialog2 = DashboardKpiSettingsDialog(_OPTIONS, [], [])
    qtbot.addWidget(dialog2)
    dialog2.cancel_button.click()
    assert dialog2.result() == QDialog.DialogCode.Rejected
