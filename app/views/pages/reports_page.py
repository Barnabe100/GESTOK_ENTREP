"""Page Rapports : consultation en lecture seule de l'état et de
l'historique du stock.

Strictement une vue de consultation (§2 du cahier des charges de cette
phase) : cette page n'appelle jamais ``StockService`` ni aucun service de
document en écriture, uniquement les méthodes ``get_*`` de
:class:`ReportService`, elles-mêmes garanties en lecture seule. Aucune
requête SQL n'est construite ici : toute la logique d'agrégation/filtrage
reste dans ``ReportService``/les repositories, conformément à l'architecture
UI -> Services -> Repositories -> SQLAlchemy.

Un unique sélecteur de rapport pilote un panneau de filtres dont seuls les
champs pertinents pour le rapport choisi sont visibles, et un tableau dont
les colonnes sont reconstruites à chaque rafraîchissement — plutôt que neuf
pages quasi identiques, pour rester simple à maintenir (§7 : « interface
fluide et lisible », pas de graphiques dans cette phase).

Export : deux boutons indépendants, CSV (``_export_to``, texte déjà formaté
pour l'affichage — ``ReportService.export_to_csv``) et Excel
(``_export_xlsx_to``, valeurs réellement typées pour des montants/quantités
triables et calculables dans Excel — ``ReportService.export_to_xlsx``), tous
deux soumis à la permission ``REPORT_EXPORT``. Chaque ``_refresh_*`` alimente
donc ``_set_table`` avec, en plus des lignes déjà formatées en texte pour le
tableau Qt et le CSV, les mêmes lignes en valeurs typées (``_current_rows_raw``)
et les formats de cellule associés (``_current_column_formats``) pour l'Excel.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
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

from app.models.enums import StatutInventaire, StatutOperation, TypeMouvement
from app.services.articles.article_service import ArticleService
from app.services.auth.permission_service import PermissionService
from app.services.categories.category_service import CategoryService
from app.services.exit_reasons.exit_reason_service import ExitReasonService
from app.services.reports.report_service import ReportService
from app.services.settings.company_settings_service import get_effective_currency
from app.utils.exceptions import AppError, ValidationError
from app.utils.money import format_money, money_decimal_places
from app.utils.quantity import format_quantity
from app.views.loading_overlay import LoadingOverlay
from app.views.optional_date_edit import OptionalDateEdit

_REPORTS = [
    "État du stock", "Stock faible", "Ruptures", "Mouvements",
    "Entrées", "Sorties", "Ventes", "Inventaires", "Valorisation",
]

# Rapports pour lesquels chaque filtre est pertinent.
_USES_SEARCH = {"État du stock", "Stock faible", "Ruptures", "Valorisation"}
_USES_CATEGORY = {"État du stock", "Stock faible", "Ruptures", "Valorisation"}
_USES_INCLUDE_INACTIVE = {"État du stock", "Valorisation"}
_USES_PERIOD = {"Mouvements", "Entrées", "Sorties", "Ventes", "Inventaires"}
_USES_ARTICLE = {"Mouvements"}
_USES_TYPE_MOUVEMENT = {"Mouvements"}
_USES_STATUT_OPERATION = {"Entrées", "Sorties", "Ventes"}
_USES_STATUT_INVENTAIRE = {"Inventaires"}
_USES_MOTIF = {"Sorties"}

_STATUT_OPERATION_LABELS = {
    StatutOperation.BROUILLON: "Brouillon", StatutOperation.VALIDEE: "Validée", StatutOperation.ANNULEE: "Annulée",
}
_STATUT_INVENTAIRE_LABELS = {StatutInventaire.BROUILLON: "Brouillon", StatutInventaire.VALIDE: "Validé"}


def _money_number_format(currency_code: str) -> str:
    """Format de cellule Excel pour un montant dans cette devise — même
    convention de décimales que :func:`format_money` (voir
    :func:`app.utils.money.money_decimal_places`)."""
    return "#,##0" if money_decimal_places(currency_code) == 0 else "#,##0.00"


def _slugify_report_name(report_name: str) -> str:
    """Nom de fichier par défaut lisible (sans accent ni espace) pour les
    boîtes de dialogue d'export — ex. « État du stock » -> « etat_du_stock »."""
    ascii_text = unicodedata.normalize("NFKD", report_name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


class ReportsPage(QWidget):
    def __init__(
        self,
        report_service: ReportService,
        category_service: CategoryService,
        article_service: ArticleService,
        exit_reason_service: ExitReasonService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._report_service = report_service
        self._category_service = category_service
        self._article_service = article_service
        self._exit_reason_service = exit_reason_service
        self._permissions = permission_service
        self._currency_code = get_effective_currency()

        self._current_headers: list[str] = []
        self._current_rows_as_text: list[list[str]] = []
        self._current_rows_raw: list[list[object]] = []
        self._current_column_formats: list[Optional[str]] = []

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Rapport", self))
        self.report_combo = QComboBox(self)
        self.report_combo.addItems(_REPORTS)
        top_row.addWidget(self.report_combo)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        self._filters_grid = QGridLayout()
        layout.addLayout(self._filters_grid)
        self._build_filter_widgets()

        button_row = QHBoxLayout()
        self.refresh_button = QPushButton("Actualiser", self)
        self.refresh_button.setProperty("variant", "primary")
        button_row.addWidget(self.refresh_button)
        self.reset_button = QPushButton("Réinitialiser les filtres", self)
        button_row.addWidget(self.reset_button)
        self.export_button = QPushButton("Exporter CSV", self)
        self.export_button.setProperty("variant", "export")
        self.export_button.setEnabled(self._permissions.has_permission("REPORT_EXPORT"))
        button_row.addWidget(self.export_button)
        self.export_xlsx_button = QPushButton("Exporter Excel", self)
        self.export_xlsx_button.setProperty("variant", "export")
        self.export_xlsx_button.setEnabled(self._permissions.has_permission("REPORT_EXPORT"))
        button_row.addWidget(self.export_xlsx_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.summary_label = QLabel("", self)
        self.summary_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 0, self)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Phase amélioration UX, point 3 : voile pendant la génération d'un
        # rapport (déclenchée uniquement par un clic explicite — voir
        # ``refresh``, jamais à chaque frappe dans un champ de filtre).
        self._loading_overlay = LoadingOverlay(self)

        self.report_combo.currentIndexChanged.connect(self._on_report_changed)
        self.refresh_button.clicked.connect(self.refresh)
        self.reset_button.clicked.connect(self._on_reset_filters_clicked)
        self.export_button.clicked.connect(self._on_export_clicked)
        self.export_xlsx_button.clicked.connect(self._on_export_xlsx_clicked)

        self._reload_category_combo()
        self._reload_article_combo()
        self._reload_motif_combo()
        # Correctif revue finale (Point 3) : ``show_loading=False`` — voir
        # la docstring de ``refresh`` pour la justification (page pas
        # encore visible, éventuellement construite par MainWindow pendant
        # son propre démarrage).
        self._on_report_changed(0, show_loading=False)

    def select_report_type(self, report_name: str) -> None:
        """Présélectionne un type de rapport — utilisé par le Dashboard pour
        les accès rapides (§12 de la phase Dashboard, ex. « Stock faible »
        -> rapport Stock faible). Pure commodité d'affichage, aucune logique
        métier : déclenche le même chemin que si l'utilisateur avait changé
        le sélecteur lui-même."""
        if report_name in _REPORTS:
            self.report_combo.setCurrentText(report_name)

    # -- construction des filtres ---------------------------------------------

    def _build_filter_widgets(self) -> None:
        self.search_label = QLabel("Recherche", self)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Référence, désignation…")
        self._filters_grid.addWidget(self.search_label, 0, 0)
        self._filters_grid.addWidget(self.search_edit, 0, 1)

        self.category_label = QLabel("Catégorie", self)
        self.category_combo = QComboBox(self)
        self._filters_grid.addWidget(self.category_label, 0, 2)
        self._filters_grid.addWidget(self.category_combo, 0, 3)

        self.include_inactive_checkbox = QCheckBox("Inclure les articles inactifs", self)
        self._filters_grid.addWidget(self.include_inactive_checkbox, 0, 4)

        self.date_from_label = QLabel("Du", self)
        self.date_from_edit = OptionalDateEdit(self)
        self._filters_grid.addWidget(self.date_from_label, 1, 0)
        self._filters_grid.addWidget(self.date_from_edit, 1, 1)

        self.date_to_label = QLabel("Au", self)
        self.date_to_edit = OptionalDateEdit(self)
        self._filters_grid.addWidget(self.date_to_label, 1, 2)
        self._filters_grid.addWidget(self.date_to_edit, 1, 3)

        self.article_label = QLabel("Article", self)
        self.article_combo = QComboBox(self)
        self._filters_grid.addWidget(self.article_label, 2, 0)
        self._filters_grid.addWidget(self.article_combo, 2, 1)

        self.type_mouvement_label = QLabel("Type de mouvement", self)
        self.type_mouvement_combo = QComboBox(self)
        self.type_mouvement_combo.addItem("(Tous)", None)
        for type_mouvement in TypeMouvement:
            self.type_mouvement_combo.addItem(type_mouvement.value, type_mouvement)
        self._filters_grid.addWidget(self.type_mouvement_label, 2, 2)
        self._filters_grid.addWidget(self.type_mouvement_combo, 2, 3)

        self.statut_label = QLabel("Statut", self)
        self.statut_combo = QComboBox(self)
        self._filters_grid.addWidget(self.statut_label, 2, 4)
        self._filters_grid.addWidget(self.statut_combo, 2, 5)

        self.motif_label = QLabel("Motif", self)
        self.motif_combo = QComboBox(self)
        self._filters_grid.addWidget(self.motif_label, 1, 4)
        self._filters_grid.addWidget(self.motif_combo, 1, 5)

    def _reload_category_combo(self) -> None:
        self.category_combo.clear()
        self.category_combo.addItem("(Toutes)", None)
        try:
            categories = self._category_service.list_categories(include_inactive=False)
        except AppError:
            categories = []
        for category in categories:
            self.category_combo.addItem(category.nom, category.id)

    def _reload_article_combo(self) -> None:
        self.article_combo.clear()
        self.article_combo.addItem("(Tous)", None)
        try:
            articles = self._article_service.list_articles(include_inactive=True)
        except AppError:
            articles = []
        for article in articles:
            self.article_combo.addItem(f"{article.reference} — {article.designation}", article.id)

    def _reload_motif_combo(self) -> None:
        self.motif_combo.clear()
        self.motif_combo.addItem("(Tous)", None)
        try:
            motifs = self._exit_reason_service.list_exit_reasons(include_inactive=True)
        except AppError:
            motifs = []
        for motif in motifs:
            self.motif_combo.addItem(motif.libelle, motif.id)

    def _reload_statut_combo(self, report_name: str) -> None:
        self.statut_combo.clear()
        self.statut_combo.addItem("(Tous)", None)
        if report_name in _USES_STATUT_INVENTAIRE:
            for statut in StatutInventaire:
                self.statut_combo.addItem(_STATUT_INVENTAIRE_LABELS.get(statut, statut.value), statut)
        elif report_name in _USES_STATUT_OPERATION:
            for statut in StatutOperation:
                self.statut_combo.addItem(_STATUT_OPERATION_LABELS.get(statut, statut.value), statut)

    def _on_report_changed(self, _index: int, *, show_loading: bool = True) -> None:
        report_name = self.report_combo.currentText()
        self._reload_statut_combo(report_name)

        for widget, visible in (
            (self.search_label, report_name in _USES_SEARCH),
            (self.search_edit, report_name in _USES_SEARCH),
            (self.category_label, report_name in _USES_CATEGORY),
            (self.category_combo, report_name in _USES_CATEGORY),
            (self.include_inactive_checkbox, report_name in _USES_INCLUDE_INACTIVE),
            (self.date_from_label, report_name in _USES_PERIOD),
            (self.date_from_edit, report_name in _USES_PERIOD),
            (self.date_to_label, report_name in _USES_PERIOD),
            (self.date_to_edit, report_name in _USES_PERIOD),
            (self.article_label, report_name in _USES_ARTICLE),
            (self.article_combo, report_name in _USES_ARTICLE),
            (self.type_mouvement_label, report_name in _USES_TYPE_MOUVEMENT),
            (self.type_mouvement_combo, report_name in _USES_TYPE_MOUVEMENT),
            (self.statut_label, report_name in _USES_STATUT_OPERATION or report_name in _USES_STATUT_INVENTAIRE),
            (self.statut_combo, report_name in _USES_STATUT_OPERATION or report_name in _USES_STATUT_INVENTAIRE),
            (self.motif_label, report_name in _USES_MOTIF),
            (self.motif_combo, report_name in _USES_MOTIF),
        ):
            widget.setVisible(visible)

        self.refresh(show_loading=show_loading)

    def _on_reset_filters_clicked(self) -> None:
        self.search_edit.clear()
        self.category_combo.setCurrentIndex(0)
        self.include_inactive_checkbox.setChecked(False)
        self.date_from_edit.set_date_or_none(None)
        self.date_to_edit.set_date_or_none(None)
        self.article_combo.setCurrentIndex(0)
        self.type_mouvement_combo.setCurrentIndex(0)
        self.statut_combo.setCurrentIndex(0)
        self.motif_combo.setCurrentIndex(0)
        self.refresh()

    # -- lecture des filtres communs ------------------------------------------

    def _read_period(self) -> tuple[Optional[date], Optional[date]]:
        return self.date_from_edit.date_or_none(), self.date_to_edit.date_or_none()

    # -- rafraîchissement -------------------------------------------------------

    def refresh(self, *, show_loading: bool = True) -> None:
        """``show_loading=False`` uniquement pour l'appel automatique fait
        par ``__init__`` (voir plus bas) : à ce moment, la page n'est pas
        encore visible (elle peut même être construite par ``MainWindow``
        pendant son propre démarrage, voir ``main_window.py``) — afficher
        un voile et purger les évènements en attente n'y servirait à rien
        et ajouterait, pendant cette construction déjà sensible, un appel
        ``processEvents()`` de plus qu'il n'en faut (risque de réentrance
        évité par défense en profondeur, voir la revue de ce lot).

        Limite documentée (correctif revue finale, Point 3) : cette
        méthode reste synchrone, jamais threadée — contrairement à
        ``BackupsPage`` (voir ``BackgroundTask``), un rapport mélange
        systématiquement une requête de service et le remplissage direct
        du tableau (``_set_table``, un ``QWidget``) dans la même méthode
        ``_refresh_*`` ; les séparer proprement toucherait les neuf types
        de rapport pour un gain incertain (une requête de rapport reste du
        même ordre de grandeur que n'importe quel autre rafraîchissement
        de liste déjà synchrone dans l'application — Locations, Ventes,
        etc.). Le voile affiché ci-dessous lors d'un rafraîchissement
        explicite (clic sur « Actualiser », changement de filtre) reste
        donc un message utile mais, comme avant ce correctif, ne garantit
        une animation réellement continue que pour une requête courte ;
        sur un très gros jeu de données, seul un correctif identique à
        celui de ``BackupsPage`` (service exécuté dans un ``BackgroundTask``,
        résultat déjà calculé transmis à ``_set_table`` sur le thread
        graphique) lèverait cette limite — à faire si un besoin réel
        apparaît, pas par anticipation."""
        report_name = self.report_combo.currentText()
        self.summary_label.setText("")
        if show_loading:
            self._loading_overlay.show_with_message("Génération du rapport…")
            QApplication.processEvents()
        try:
            dispatch = {
                "État du stock": self._refresh_stock_state,
                "Stock faible": self._refresh_low_stock,
                "Ruptures": self._refresh_out_of_stock,
                "Mouvements": self._refresh_movements,
                "Entrées": self._refresh_entries,
                "Sorties": self._refresh_exits,
                "Ventes": self._refresh_sales,
                "Inventaires": self._refresh_inventories,
                "Valorisation": self._refresh_valorisation,
            }
            dispatch[report_name]()
        except AppError as exc:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self._current_headers, self._current_rows_as_text = [], []
            QMessageBox.warning(self, "Rapport indisponible", str(exc))
        finally:
            if show_loading:
                self._loading_overlay.hide_overlay()

    def _set_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        rows_raw: Optional[list[list[object]]] = None,
        column_formats: Optional[list[Optional[str]]] = None,
    ) -> None:
        self._current_headers = headers
        self._current_rows_as_text = rows
        self._current_rows_raw = rows_raw if rows_raw is not None else rows
        self._current_column_formats = column_formats if column_formats is not None else [None] * len(headers)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                self.table.setItem(row_index, col_index, QTableWidgetItem(value))

    def _refresh_stock_state(self) -> None:
        rows = self._report_service.get_stock_state(
            search=self.search_edit.text(),
            category_id=self.category_combo.currentData(),
            include_inactive=self.include_inactive_checkbox.isChecked(),
        )
        headers = ["Référence", "Désignation", "Catégorie", "Fournisseur", "Unité",
                   "Stock actuel", "Stock min", "Stock max", "CMUP", "Valeur stock", "Statut"]
        money_format = _money_number_format(self._currency_code)
        self._set_table(
            headers,
            [
                [r.reference, r.designation, r.category_nom, r.fournisseur_nom or "—", r.unite,
                 format_quantity(r.stock_actuel), format_quantity(r.stock_min),
                 format_quantity(r.stock_max) if r.stock_max is not None else "—",
                 format_money(r.cout_moyen_pondere, self._currency_code),
                 format_money(r.valeur_stock, self._currency_code),
                 "Actif" if r.actif else "Inactif"]
                for r in rows
            ],
            [
                [r.reference, r.designation, r.category_nom, r.fournisseur_nom or "—", r.unite,
                 r.stock_actuel, r.stock_min, r.stock_max, r.cout_moyen_pondere, r.valeur_stock,
                 "Actif" if r.actif else "Inactif"]
                for r in rows
            ],
            [None, None, None, None, None, None, None, None, money_format, money_format, None],
        )
        self.summary_label.setText(f"{len(rows)} article(s)")

    def _refresh_low_stock(self) -> None:
        rows = self._report_service.get_low_stock(
            search=self.search_edit.text(), category_id=self.category_combo.currentData()
        )
        money_format = _money_number_format(self._currency_code)
        self._set_table(
            ["Référence", "Désignation", "Stock actuel", "Stock min", "CMUP", "Valeur stock"],
            [
                [r.reference, r.designation, format_quantity(r.stock_actuel), format_quantity(r.stock_min),
                 format_money(r.cout_moyen_pondere, self._currency_code),
                 format_money(r.valeur_stock, self._currency_code)]
                for r in rows
            ],
            [
                [r.reference, r.designation, r.stock_actuel, r.stock_min, r.cout_moyen_pondere, r.valeur_stock]
                for r in rows
            ],
            [None, None, None, None, money_format, money_format],
        )
        self.summary_label.setText(f"{len(rows)} article(s) en stock faible")

    def _refresh_out_of_stock(self) -> None:
        rows = self._report_service.get_out_of_stock(
            search=self.search_edit.text(), category_id=self.category_combo.currentData()
        )
        money_format = _money_number_format(self._currency_code)
        self._set_table(
            ["Référence", "Désignation", "Stock actuel", "Stock min", "CMUP", "Valeur stock"],
            [
                [r.reference, r.designation, format_quantity(r.stock_actuel), format_quantity(r.stock_min),
                 format_money(r.cout_moyen_pondere, self._currency_code),
                 format_money(r.valeur_stock, self._currency_code)]
                for r in rows
            ],
            [
                [r.reference, r.designation, r.stock_actuel, r.stock_min, r.cout_moyen_pondere, r.valeur_stock]
                for r in rows
            ],
            [None, None, None, None, money_format, money_format],
        )
        self.summary_label.setText(f"{len(rows)} article(s) en rupture")

    def _refresh_valorisation(self) -> None:
        report = self._report_service.get_valorisation(
            search=self.search_edit.text(),
            category_id=self.category_combo.currentData(),
            include_inactive=self.include_inactive_checkbox.isChecked(),
        )
        money_format = _money_number_format(self._currency_code)
        self._set_table(
            ["Référence", "Désignation", "Catégorie", "Stock actuel", "CMUP", "Valeur stock"],
            [
                [r.reference, r.designation, r.category_nom, format_quantity(r.stock_actuel),
                 format_money(r.cout_moyen_pondere, self._currency_code),
                 format_money(r.valeur_stock, self._currency_code)]
                for r in report.rows
            ],
            [
                [r.reference, r.designation, r.category_nom, r.stock_actuel, r.cout_moyen_pondere, r.valeur_stock]
                for r in report.rows
            ],
            [None, None, None, None, money_format, money_format],
        )
        self.summary_label.setText(f"Valeur totale du stock : {format_money(report.total, self._currency_code)}")

    def _refresh_movements(self) -> None:
        date_from, date_to = self._read_period()
        movements = self._report_service.get_movements(
            date_from=date_from, date_to=date_to,
            article_id=self.article_combo.currentData(),
            type_mouvement=self.type_mouvement_combo.currentData(),
        )
        money_format = _money_number_format(self._currency_code)
        self._set_table(
            ["Date/heure", "Article", "Type", "Quantité", "Stock avant", "Stock après",
             "Coût unitaire", "Utilisateur", "Commentaire"],
            [
                [m.date_heure.strftime("%Y-%m-%d %H:%M"), m.article_reference, m.type.value,
                 format_quantity(m.quantite), format_quantity(m.stock_avant), format_quantity(m.stock_apres),
                 format_money(m.cout_unitaire, self._currency_code) if m.cout_unitaire is not None else "—",
                 m.username, m.commentaire or "—"]
                for m in movements
            ],
            [
                [m.date_heure.strftime("%Y-%m-%d %H:%M"), m.article_reference, m.type.value,
                 m.quantite, m.stock_avant, m.stock_apres, m.cout_unitaire, m.username, m.commentaire or "—"]
                for m in movements
            ],
            [None, None, None, None, None, None, money_format, None, None],
        )
        self.summary_label.setText(f"{len(movements)} mouvement(s)")

    def _refresh_entries(self) -> None:
        date_from, date_to = self._read_period()
        entries = self._report_service.get_entries(date_from=date_from, date_to=date_to, statut=self.statut_combo.currentData())
        money_format = _money_number_format(self._currency_code)
        self._set_table(
            ["Numéro", "Date", "Fournisseur", "Utilisateur", "Statut", "Montant", "Lignes"],
            [
                [e.numero, str(e.date), e.fournisseur_nom, e.username,
                 _STATUT_OPERATION_LABELS.get(e.statut, str(e.statut)),
                 format_money(e.total, self._currency_code), str(len(e.lignes))]
                for e in entries
            ],
            [
                [e.numero, str(e.date), e.fournisseur_nom, e.username,
                 _STATUT_OPERATION_LABELS.get(e.statut, str(e.statut)), e.total, len(e.lignes)]
                for e in entries
            ],
            [None, None, None, None, None, money_format, None],
        )
        self.summary_label.setText(f"{len(entries)} entrée(s)")

    def _refresh_exits(self) -> None:
        date_from, date_to = self._read_period()
        exits = self._report_service.get_exits(
            date_from=date_from, date_to=date_to,
            motif_id=self.motif_combo.currentData(), statut=self.statut_combo.currentData(),
        )
        money_format = _money_number_format(self._currency_code)
        self._set_table(
            ["Numéro", "Date", "Motif", "Utilisateur", "Statut", "Montant", "Lignes"],
            [
                [s.numero, str(s.date), s.motif_libelle, s.username,
                 _STATUT_OPERATION_LABELS.get(s.statut, str(s.statut)),
                 format_money(s.total, self._currency_code), str(len(s.lignes))]
                for s in exits
            ],
            [
                [s.numero, str(s.date), s.motif_libelle, s.username,
                 _STATUT_OPERATION_LABELS.get(s.statut, str(s.statut)), s.total, len(s.lignes)]
                for s in exits
            ],
            [None, None, None, None, None, money_format, None],
        )
        self.summary_label.setText(f"{len(exits)} sortie(s)")

    def _refresh_sales(self) -> None:
        date_from, date_to = self._read_period()
        sales = self._report_service.get_sales(date_from=date_from, date_to=date_to, statut=self.statut_combo.currentData())
        money_format = _money_number_format(self._currency_code)
        self._set_table(
            ["Numéro", "Date", "Utilisateur", "Statut", "Montant", "Lignes"],
            [
                [v.numero, str(v.date), v.username, _STATUT_OPERATION_LABELS.get(v.statut, str(v.statut)),
                 format_money(v.total, self._currency_code), str(len(v.lignes))]
                for v in sales
            ],
            [
                [v.numero, str(v.date), v.username, _STATUT_OPERATION_LABELS.get(v.statut, str(v.statut)),
                 v.total, len(v.lignes)]
                for v in sales
            ],
            [None, None, None, None, money_format, None],
        )
        total_ca = sum((v.total for v in sales if v.statut == StatutOperation.VALIDEE), Decimal("0"))
        self.summary_label.setText(
            f"{len(sales)} vente(s) — chiffre d'affaires (ventes validées) : "
            f"{format_money(total_ca, self._currency_code)}"
        )

    def _refresh_inventories(self) -> None:
        date_from, date_to = self._read_period()
        inventories = self._report_service.get_inventories(date_from=date_from, date_to=date_to, statut=self.statut_combo.currentData())
        self._set_table(
            ["Numéro", "Date", "Utilisateur", "Statut", "Lignes", "Écarts +", "Écarts -", "Qté totale ajustée"],
            [
                [i.numero, str(i.date), i.username, _STATUT_INVENTAIRE_LABELS.get(i.statut, str(i.statut)),
                 str(i.nombre_lignes), str(i.nombre_ecarts_positifs), str(i.nombre_ecarts_negatifs),
                 format_quantity(i.quantite_totale_ajustee)]
                for i in inventories
            ],
            [
                [i.numero, str(i.date), i.username, _STATUT_INVENTAIRE_LABELS.get(i.statut, str(i.statut)),
                 i.nombre_lignes, i.nombre_ecarts_positifs, i.nombre_ecarts_negatifs, i.quantite_totale_ajustee]
                for i in inventories
            ],
        )
        self.summary_label.setText(f"{len(inventories)} inventaire(s)")

    # -- export CSV -------------------------------------------------------------

    def _on_export_clicked(self) -> None:
        if not self._current_headers:
            QMessageBox.information(self, "Export CSV", "Aucune donnée à exporter.")
            return
        file_path, _filter = QFileDialog.getSaveFileName(self, "Exporter le rapport", "", "CSV (*.csv)")
        if not file_path:
            return
        self._export_to(file_path)

    def _export_to(self, file_path: str) -> bool:
        """Isolé de ``_on_export_clicked`` pour rester testable sans boîte de
        dialogue modale de sélection de fichier."""
        try:
            self._report_service.export_to_csv(file_path, self._current_headers, self._current_rows_as_text)
            QMessageBox.information(self, "Export CSV", "Le rapport a été exporté avec succès.")
        except AppError as exc:
            QMessageBox.warning(self, "Export refusé", str(exc))
            return False
        return True

    # -- export Excel -------------------------------------------------------------

    def _on_export_xlsx_clicked(self) -> None:
        if not self._current_headers:
            QMessageBox.information(self, "Export Excel", "Aucune donnée à exporter.")
            return
        default_name = f"{_slugify_report_name(self.report_combo.currentText())}_{date.today().isoformat()}.xlsx"
        file_path, _filter = QFileDialog.getSaveFileName(self, "Exporter le rapport", default_name, "Excel (*.xlsx)")
        if not file_path:
            return
        self._export_xlsx_to(file_path)

    def _export_xlsx_to(self, file_path: str) -> bool:
        """Isolé de ``_on_export_xlsx_clicked`` pour rester testable sans
        boîte de dialogue modale de sélection de fichier (même principe que
        ``_export_to`` pour le CSV)."""
        try:
            self._report_service.export_to_xlsx(
                file_path, self._current_headers, self._current_rows_raw, self._current_column_formats
            )
            QMessageBox.information(self, "Export Excel", "Le rapport a été exporté avec succès.")
        except AppError as exc:
            QMessageBox.warning(self, "Export refusé", str(exc))
            return False
        return True
