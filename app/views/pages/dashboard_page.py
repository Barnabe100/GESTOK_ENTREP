"""Page Dashboard : synthèse et visualisation, strictement en lecture seule
(§9-10 du cahier des charges de cette phase).

Cette page n'appelle jamais ``StockService`` ni aucun service métier en
écriture : elle ne consulte que :class:`DashboardService` (lui-même
strictement lecture seule, voir son docstring). Aucune requête SQL ni
logique d'agrégation ici — uniquement construction de widgets/graphiques à
partir des DTO déjà calculés par le service (architecture UI -> Services ->
Repositories, §9).

Les accès rapides (§12) réutilisent le mécanisme de navigation de
``MainWindow`` (callback ``on_navigate``) et respectent individuellement la
permission du module cible : un bouton n'est jamais affiché vers un module
que l'utilisateur ne peut pas utiliser.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QPieSeries, QValueAxis
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import TypeMouvement
from app.services.auth.permission_service import PermissionService
from app.services.dashboard.dashboard_service import DashboardOverview, DashboardService, default_period
from app.services.settings.company_settings_service import get_effective_currency
from app.utils.exceptions import AppError
from app.utils.money import format_money
from app.views.common import parse_date

# Permissions requises pour chaque accès rapide (§12) — jamais affiché si
# l'utilisateur courant ne les a pas, indépendamment de DASHBOARD_VIEW.
_NAVIGATION_TARGETS: list[tuple[str, str, str, Optional[str]]] = [
    # (libellé bouton, module cible, permission requise, préréglage rapport)
    ("Voir les ventes", "Ventes", "SALE_VIEW", None),
    ("Voir les entrées", "Entrées", "STOCK_ENTRY_VIEW", None),
    ("Voir les sorties", "Sorties", "STOCK_EXIT_VIEW", None),
    ("Voir les mouvements", "Mouvements", "STOCK_MOVEMENT_VIEW", None),
]


def _decimal_to_float(value: Decimal) -> float:
    """Conversion strictement pour l'affichage graphique (géométrie des
    barres/secteurs) — jamais utilisée pour un calcul métier ; tous les
    montants affichés en texte restent formatés depuis le ``Decimal``
    d'origine via ``format_money``."""
    return float(value)


class DashboardPage(QWidget):
    def __init__(
        self,
        dashboard_service: DashboardService,
        permission_service: PermissionService,
        on_navigate: Optional[Callable[[str, Optional[str]], bool]] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dashboard_service = dashboard_service
        self._permissions = permission_service
        self._on_navigate = on_navigate
        self._currency_code = get_effective_currency()

        layout = QVBoxLayout(self)

        layout.addLayout(self._build_period_row())
        layout.addLayout(self._build_kpi_row())

        self.status_label = QLabel("", self)
        self.status_label.setStyleSheet("color: #b00020; font-weight: 600;")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        layout.addLayout(self._build_charts_grid())
        layout.addLayout(self._build_alerts_row())
        layout.addWidget(QLabel("Activité récente", self))
        layout.addWidget(self._build_recent_activity_table())

        period_from, period_to = default_period()
        self.date_from_edit.setText(period_from.isoformat())
        self.date_to_edit.setText(period_to.isoformat())

        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    # -- construction ---------------------------------------------------------------

    def _build_period_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Période — du", self))
        self.date_from_edit = QLineEdit(self)
        self.date_from_edit.setPlaceholderText("AAAA-MM-JJ")
        row.addWidget(self.date_from_edit)
        row.addWidget(QLabel("au", self))
        self.date_to_edit = QLineEdit(self)
        self.date_to_edit.setPlaceholderText("AAAA-MM-JJ")
        row.addWidget(self.date_to_edit)
        self.refresh_button = QPushButton("Actualiser", self)
        row.addWidget(self.refresh_button)
        row.addStretch(1)
        return row

    def _build_kpi_card(self, title: str) -> tuple[QGroupBox, QLabel]:
        card = QGroupBox(title, self)
        card_layout = QVBoxLayout(card)
        value_label = QLabel("—", card)
        value_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(value_label)
        return card, value_label

    def _build_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.kpi_articles_card, self.kpi_articles_label = self._build_kpi_card("Articles actifs")
        self.kpi_stock_value_card, self.kpi_stock_value_label = self._build_kpi_card("Valeur du stock")
        self.kpi_low_stock_card, self.kpi_low_stock_label = self._build_kpi_card("Stock faible")
        self.kpi_out_of_stock_card, self.kpi_out_of_stock_label = self._build_kpi_card("Ruptures")
        self.kpi_sales_card, self.kpi_sales_label = self._build_kpi_card("Ventes (période)")
        for card in (
            self.kpi_articles_card, self.kpi_stock_value_card, self.kpi_low_stock_card,
            self.kpi_out_of_stock_card, self.kpi_sales_card,
        ):
            row.addWidget(card)
        return row

    def _build_charts_grid(self) -> QGridLayout:
        grid = QGridLayout()

        self.sales_chart_view = QChartView(self)
        self.sales_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.sales_chart_view.setMinimumHeight(260)
        grid.addWidget(self.sales_chart_view, 0, 0)

        self.movement_chart_view = QChartView(self)
        self.movement_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.movement_chart_view.setMinimumHeight(260)
        grid.addWidget(self.movement_chart_view, 0, 1)

        self.category_value_chart_view = QChartView(self)
        self.category_value_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.category_value_chart_view.setMinimumHeight(260)
        grid.addWidget(self.category_value_chart_view, 1, 0)

        low_stock_box = QVBoxLayout()
        low_stock_box.addWidget(QLabel("Articles en stock faible", self))
        self.low_stock_table = QTableWidget(0, 3, self)
        self.low_stock_table.setHorizontalHeaderLabels(["Référence", "Désignation", "Stock actuel / min"])
        self.low_stock_table.horizontalHeader().setStretchLastSection(True)
        self.low_stock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        low_stock_box.addWidget(self.low_stock_table)
        grid.addLayout(low_stock_box, 1, 1)

        return grid

    def _build_alerts_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.low_stock_alert_label = QLabel("", self)
        row.addWidget(self.low_stock_alert_label)
        self.low_stock_alert_button = QPushButton("Voir le rapport Stock faible", self)
        self.low_stock_alert_button.clicked.connect(lambda: self._navigate("Rapports", "Stock faible"))
        row.addWidget(self.low_stock_alert_button)

        self.out_of_stock_alert_label = QLabel("", self)
        row.addWidget(self.out_of_stock_alert_label)
        self.out_of_stock_alert_button = QPushButton("Voir le rapport Ruptures", self)
        self.out_of_stock_alert_button.clicked.connect(lambda: self._navigate("Rapports", "Ruptures"))
        row.addWidget(self.out_of_stock_alert_button)

        row.addStretch(1)

        self.navigation_buttons: dict[str, QPushButton] = {}
        for label, target_module, _permission_code, preset in _NAVIGATION_TARGETS:
            button = QPushButton(label, self)
            button.clicked.connect(lambda _checked=False, m=target_module, p=preset: self._navigate(m, p))
            row.addWidget(button)
            self.navigation_buttons[target_module] = button

        can_view_reports = self._permissions.has_permission("REPORT_VIEW")
        self.low_stock_alert_button.setVisible(can_view_reports)
        self.out_of_stock_alert_button.setVisible(can_view_reports)
        for _label, target_module, permission_code, _preset in _NAVIGATION_TARGETS:
            self.navigation_buttons[target_module].setVisible(self._permissions.has_permission(permission_code))

        return row

    def _build_recent_activity_table(self) -> QTableWidget:
        self.recent_activity_table = QTableWidget(0, 5, self)
        self.recent_activity_table.setHorizontalHeaderLabels(
            ["Date/heure", "Type", "Article", "Utilisateur", "Quantité"]
        )
        self.recent_activity_table.horizontalHeader().setStretchLastSection(True)
        self.recent_activity_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        return self.recent_activity_table

    # -- navigation -------------------------------------------------------------------

    def _navigate(self, module_name: str, report_preset: Optional[str]) -> None:
        if self._on_navigate is not None:
            self._on_navigate(module_name, report_preset)

    # -- rafraîchissement ---------------------------------------------------------------

    def _read_period(self) -> Optional[tuple[date, date]]:
        try:
            period_from = parse_date(self.date_from_edit.text(), "date de début")
            period_to = parse_date(self.date_to_edit.text(), "date de fin")
        except AppError as exc:
            QMessageBox.warning(self, "Période invalide", str(exc))
            return None
        return period_from, period_to

    def refresh(self) -> None:
        period = self._read_period()
        if period is None:
            return
        period_from, period_to = period

        try:
            overview = self._dashboard_service.get_overview(period_from, period_to)
        except AppError as exc:
            self._show_status(str(exc))
            return

        self._hide_status()
        self._apply_overview(overview)

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setVisible(True)

    def _hide_status(self) -> None:
        self.status_label.setText("")
        self.status_label.setVisible(False)

    def _apply_overview(self, overview: DashboardOverview) -> None:
        catalog = overview.catalog
        self.kpi_articles_label.setText(str(catalog.active_articles) if catalog.active_articles is not None else "—")

        stock = overview.stock
        if stock is not None:
            self.kpi_stock_value_label.setText(format_money(stock.total_value, self._currency_code))
            self.kpi_low_stock_label.setText(str(stock.low_stock_count))
            self.kpi_out_of_stock_label.setText(str(stock.out_of_stock_count))
            self.low_stock_alert_label.setText(f"{stock.low_stock_count} article(s) en stock faible")
            self.out_of_stock_alert_label.setText(f"{stock.out_of_stock_count} article(s) en rupture")
        else:
            self.kpi_stock_value_label.setText("—")
            self.kpi_low_stock_label.setText("—")
            self.kpi_out_of_stock_label.setText("—")
            self.low_stock_alert_label.setText("")
            self.out_of_stock_alert_label.setText("")

        activity = overview.activity
        if activity is not None:
            self.kpi_sales_label.setText(format_money(activity.sales_amount, self._currency_code))
        else:
            self.kpi_sales_label.setText("—")

        self._apply_sales_chart(overview.sales_evolution or [])
        self._apply_movement_chart(overview.movement_breakdown or {})
        self._apply_category_value_chart(overview.stock_value_by_category or [])
        self._apply_low_stock_table(overview.low_stock_top or [])
        self._apply_recent_activity_table(overview.recent_activity or [])

    def _apply_sales_chart(self, points) -> None:
        chart = QChart()
        chart.setTitle("Évolution des ventes")
        bar_set = QBarSet("Montant des ventes")
        categories = []
        for point in points:
            bar_set.append(_decimal_to_float(point.amount))
            categories.append(point.label)
        series = QBarSeries()
        series.append(bar_set)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(False)
        self.sales_chart_view.setChart(chart)

    def _apply_movement_chart(self, breakdown: dict[TypeMouvement, int]) -> None:
        chart = QChart()
        chart.setTitle("Répartition des mouvements")
        series = QPieSeries()
        for type_mouvement, count in sorted(breakdown.items(), key=lambda kv: kv[0].value):
            series.append(f"{type_mouvement.value} ({count})", count)
        chart.addSeries(series)
        self.movement_chart_view.setChart(chart)

    def _apply_category_value_chart(self, category_values) -> None:
        chart = QChart()
        chart.setTitle("Valeur du stock par catégorie")
        bar_set = QBarSet("Valeur du stock")
        categories = []
        for row in category_values:
            bar_set.append(_decimal_to_float(row.valeur_stock))
            categories.append(row.category_nom)
        series = QBarSeries()
        series.append(bar_set)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(False)
        self.category_value_chart_view.setChart(chart)

    def _apply_low_stock_table(self, rows) -> None:
        self.low_stock_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.low_stock_table.setItem(row_index, 0, QTableWidgetItem(row.reference))
            self.low_stock_table.setItem(row_index, 1, QTableWidgetItem(row.designation))
            self.low_stock_table.setItem(
                row_index, 2, QTableWidgetItem(f"{row.stock_actuel} / {row.stock_min}")
            )

    def _apply_recent_activity_table(self, rows) -> None:
        self.recent_activity_table.setRowCount(len(rows))
        for row_index, movement in enumerate(rows):
            self.recent_activity_table.setItem(
                row_index, 0, QTableWidgetItem(movement.date_heure.strftime("%Y-%m-%d %H:%M"))
            )
            self.recent_activity_table.setItem(row_index, 1, QTableWidgetItem(movement.type.value))
            self.recent_activity_table.setItem(row_index, 2, QTableWidgetItem(movement.article_reference))
            self.recent_activity_table.setItem(row_index, 3, QTableWidgetItem(movement.username))
            self.recent_activity_table.setItem(row_index, 4, QTableWidgetItem(str(movement.quantite)))
