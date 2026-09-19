"""Page de gestion des articles.

Toute action (création, modification, activation/désactivation) passe par
:class:`ArticleService`, qui revérifie la permission côté service. Le stock
actuel et le CMUP ne sont jamais des champs modifiables depuis cette page :
ils sont affichés comme des informations pilotées par le système (voir
``ArticleFormDialog`` et ``ArticleDetailDialog``).

Le filtre par catégorie est dérivé des articles visibles par l'utilisateur
(pas d'appel à ``CategoryService``), afin de rester utilisable par un rôle
disposant de ``ARTICLE_VIEW`` sans nécessairement disposer de
``CATEGORY_VIEW`` (ex. Vendeur). Le formulaire de création/modification,
lui, n'est de toute façon atteignable que par un rôle disposant de
``ARTICLE_CREATE``/``ARTICLE_UPDATE`` — dans la matrice RBAC actuelle, ces
rôles disposent aussi de ``CATEGORY_VIEW``/``SUPPLIER_VIEW``.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.articles.article_service import ArticleService
from app.services.auth.permission_service import PermissionService
from app.services.categories.category_service import CategoryService
from app.services.settings.company_settings_service import get_effective_currency
from app.services.suppliers.supplier_service import SupplierService
from app.utils.exceptions import AppError, ValidationError
from app.utils.money import format_money
from app.views.article_detail_dialog import ArticleDetailDialog
from app.views.article_form_dialog import ArticleFormDialog
from app.views.common import confirm_action, parse_decimal, parse_optional_decimal, run_modal_form

_COLUMNS = [
    "Référence", "Désignation", "Catégorie", "Stock actuel", "Stock min", "Stock max",
    "Prix achat", "Prix vente", "CMUP", "Statut",
]

_RUPTURE_BG = QColor("#FEE2E2")
_RUPTURE_FG = QColor("#DC2626")
_LOW_STOCK_BG = QColor("#FEF3C7")
_LOW_STOCK_FG = QColor("#B45309")

_STATUS_FILTERS = [("Tous", "tous"), ("Actifs", "actifs"), ("Inactifs", "inactifs")]


class ArticlesPage(QWidget):
    def __init__(
        self,
        article_service: ArticleService,
        category_service: CategoryService,
        supplier_service: SupplierService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._article_service = article_service
        self._category_service = category_service
        self._supplier_service = supplier_service
        self._permissions = permission_service
        self._currency_code = get_effective_currency()

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher (référence, désignation, catégorie)…")
        toolbar.addWidget(self.search_edit)

        self.category_filter_combo = QComboBox(self)
        self._populate_category_filter()
        toolbar.addWidget(self.category_filter_combo)

        self.status_filter_combo = QComboBox(self)
        for label, value in _STATUS_FILTERS:
            self.status_filter_combo.addItem(label, value)
        self.status_filter_combo.setCurrentIndex(1)  # Actifs par défaut
        toolbar.addWidget(self.status_filter_combo)

        self.low_stock_checkbox = QCheckBox("Stock faible uniquement", self)
        toolbar.addWidget(self.low_stock_checkbox)

        toolbar.addStretch(1)

        self.add_button = QPushButton("Ajouter", self)
        self.add_button.setEnabled(self._permissions.has_permission("ARTICLE_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        self.edit_button.setEnabled(self._permissions.has_permission("ARTICLE_UPDATE"))
        toolbar.addWidget(self.edit_button)

        self.detail_button = QPushButton("Détails", self)
        toolbar.addWidget(self.detail_button)

        self.toggle_button = QPushButton("Activer / désactiver", self)
        self.toggle_button.setEnabled(
            self._permissions.has_permission("ARTICLE_ACTIVATE")
            or self._permissions.has_permission("ARTICLE_DEACTIVATE")
        )
        toolbar.addWidget(self.toggle_button)

        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(_COLUMNS), self)
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.search_edit.textChanged.connect(self.refresh)
        self.category_filter_combo.currentIndexChanged.connect(self.refresh)
        self.status_filter_combo.currentIndexChanged.connect(self.refresh)
        self.low_stock_checkbox.stateChanged.connect(self.refresh)
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.detail_button.clicked.connect(self._on_detail_clicked)
        self.toggle_button.clicked.connect(self._on_toggle_clicked)

        self.refresh()

    # -- affichage ---------------------------------------------------------

    def _populate_category_filter(self) -> None:
        self.category_filter_combo.addItem("(Toutes catégories)", None)
        try:
            articles = self._article_service.list_articles(include_inactive=True)
        except AppError:
            return
        seen: dict[int, str] = {}
        for article in articles:
            seen[article.category_id] = article.category_nom
        for category_id, nom in sorted(seen.items(), key=lambda item: item[1]):
            self.category_filter_combo.addItem(nom, category_id)

    def refresh(self) -> None:
        category_id = self.category_filter_combo.currentData()
        try:
            articles = self._article_service.list_articles(
                search=self.search_edit.text(),
                category_id=category_id,
                include_inactive=True,
                low_stock_only=self.low_stock_checkbox.isChecked(),
            )
        except AppError:
            self.table.setRowCount(0)
            return

        status_filter = self.status_filter_combo.currentData()
        if status_filter == "actifs":
            articles = [a for a in articles if a.actif]
        elif status_filter == "inactifs":
            articles = [a for a in articles if not a.actif]

        self.table.setRowCount(len(articles))
        for row, article in enumerate(articles):
            reference_item = QTableWidgetItem(article.reference)
            reference_item.setData(Qt.ItemDataRole.UserRole, article.id)
            self.table.setItem(row, 0, reference_item)
            self.table.setItem(row, 1, QTableWidgetItem(article.designation))
            self.table.setItem(row, 2, QTableWidgetItem(article.category_nom))

            stock_item = QTableWidgetItem(str(article.stock_actuel))
            if article.en_rupture:
                stock_item.setBackground(_RUPTURE_BG)
                stock_item.setForeground(_RUPTURE_FG)
            elif article.stock_faible:
                stock_item.setBackground(_LOW_STOCK_BG)
                stock_item.setForeground(_LOW_STOCK_FG)
            self.table.setItem(row, 3, stock_item)

            self.table.setItem(row, 4, QTableWidgetItem(str(article.stock_min)))
            self.table.setItem(row, 5, QTableWidgetItem(str(article.stock_max) if article.stock_max is not None else "—"))
            self.table.setItem(row, 6, QTableWidgetItem(format_money(article.prix_achat, self._currency_code)))
            self.table.setItem(row, 7, QTableWidgetItem(format_money(article.prix_vente, self._currency_code)))
            self.table.setItem(row, 8, QTableWidgetItem(format_money(article.cout_moyen_pondere, self._currency_code)))
            self.table.setItem(row, 9, QTableWidgetItem("Actif" if article.actif else "Inactif"))

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    def _selected_article_id(self) -> Optional[int]:
        row = self._selected_row()
        if row is None:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    # -- chargement des listes pour les formulaires -------------------------

    def _load_categories_for_form(self, include_category_id: Optional[int] = None) -> list[tuple[int, str]]:
        try:
            categories = self._category_service.list_categories(include_inactive=False)
        except AppError:
            categories = []
        result = [(c.id, c.nom) for c in categories]
        known_ids = {c[0] for c in result}
        if include_category_id is not None and include_category_id not in known_ids:
            try:
                current = self._category_service.get_category(include_category_id)
                result.append((current.id, f"{current.nom} (inactive)"))
            except AppError:
                pass
        return result

    def _load_suppliers_for_form(self, include_supplier_id: Optional[int] = None) -> list[tuple[int, str]]:
        try:
            suppliers = self._supplier_service.list_suppliers(include_inactive=False)
        except AppError:
            suppliers = []
        result = [(s.id, s.nom) for s in suppliers]
        known_ids = {s[0] for s in result}
        if include_supplier_id is not None and include_supplier_id not in known_ids:
            try:
                current = self._supplier_service.get_supplier(include_supplier_id)
                result.append((current.id, f"{current.nom} (inactif)"))
            except AppError:
                pass
        return result

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        categories = self._load_categories_for_form()
        suppliers = self._load_suppliers_for_form()
        self._open_form(article_id=None, categories=categories, suppliers=suppliers, initial={})

    def _on_edit_clicked(self) -> None:
        article_id = self._selected_article_id()
        if article_id is None:
            return
        initial = self._load_edit_initial(article_id)
        if initial is None:
            return
        categories = self._load_categories_for_form(include_category_id=initial["category_id"])
        suppliers = self._load_suppliers_for_form(include_supplier_id=initial["fournisseur_principal_id"])
        self._open_form(article_id=article_id, categories=categories, suppliers=suppliers, initial=initial)

    def _load_edit_initial(self, article_id: int) -> Optional[dict]:
        """Récupère les valeurs actuelles d'un article pour pré-remplir le
        formulaire de modification. Isolé de ``_on_edit_clicked`` pour rester
        testable sans dialogue modal."""
        try:
            full = self._article_service.get_article(article_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        return {
            "reference": full.reference,
            "designation": full.designation,
            "category_id": full.category_id,
            "fournisseur_principal_id": full.fournisseur_principal_id,
            "unite": full.unite,
            "prix_achat": full.prix_achat,
            "prix_vente": full.prix_vente,
            "stock_min": full.stock_min,
            "stock_max": full.stock_max,
            "stock_actuel": full.stock_actuel,
            "cout_moyen_pondere": full.cout_moyen_pondere,
            "emplacement": full.emplacement,
            "code_barres": full.code_barres,
            "description": full.description,
        }

    def _open_form(
        self,
        article_id: Optional[int],
        categories: list[tuple[int, str]],
        suppliers: list[tuple[int, str]],
        initial: dict,
    ) -> None:
        state = {"values": initial}

        def factory() -> ArticleFormDialog:
            return ArticleFormDialog(
                categories, suppliers, state["values"], is_edit=(article_id is not None), parent=self
            )

        def submit(dialog: ArticleFormDialog) -> bool:
            state["values"] = dialog.values()
            return self._submit_form(article_id, state["values"])

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_form(self, article_id: Optional[int], values: dict) -> bool:
        """Convertit la saisie, appelle le service et affiche le résultat.
        Isolé de ``_open_form`` pour rester testable sans dialogue modal."""
        try:
            category_id = values["category_id"]
            if category_id is None:
                raise ValidationError("Veuillez sélectionner une catégorie.")

            prix_achat = parse_decimal(values["prix_achat"], "prix d'achat")
            prix_vente = parse_decimal(values["prix_vente"], "prix de vente")
            stock_min = parse_decimal(values["stock_min"], "stock minimum")
            stock_max = parse_optional_decimal(values["stock_max"], "stock maximum")

            if article_id is None:
                stock_initial = parse_decimal(values["stock_initial"], "stock initial")
                created = self._article_service.create_article(
                    values["reference"],
                    values["designation"],
                    category_id,
                    values["unite"],
                    prix_achat,
                    prix_vente,
                    stock_min,
                    fournisseur_principal_id=values["fournisseur_principal_id"],
                    stock_max=stock_max,
                    emplacement=values["emplacement"],
                    description=values["description"],
                    code_barres=values["code_barres"],
                    stock_initial=stock_initial,
                )
                QMessageBox.information(
                    self, "Article créé", f"L'article « {created.reference} » a été créé."
                )
            else:
                updated = self._article_service.update_article(
                    article_id,
                    values["reference"],
                    values["designation"],
                    category_id,
                    values["unite"],
                    prix_achat,
                    prix_vente,
                    stock_min,
                    fournisseur_principal_id=values["fournisseur_principal_id"],
                    stock_max=stock_max,
                    emplacement=values["emplacement"],
                    description=values["description"],
                    code_barres=values["code_barres"],
                )
                QMessageBox.information(
                    self, "Article modifié", f"L'article « {updated.reference} » a été modifié."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- consultation détaillée ----------------------------------------------

    def _on_detail_clicked(self) -> None:
        article_id = self._selected_article_id()
        if article_id is None:
            return
        article = self._load_article_for_detail(article_id)
        if article is None:
            return
        dialog = ArticleDetailDialog(article, self._currency_code, parent=self)
        dialog.exec()

    def _load_article_for_detail(self, article_id: int):
        """Isolé de ``_on_detail_clicked`` pour rester testable sans dialogue modal."""
        try:
            return self._article_service.get_article(article_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None

    # -- activation / désactivation -----------------------------------------

    def _on_toggle_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            return

        article_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        reference = self.table.item(row, 0).text()
        currently_active = self.table.item(row, 9).text() == "Actif"
        action_label = "désactiver" if currently_active else "activer"

        if not confirm_action(
            self, "Confirmation", f"Voulez-vous vraiment {action_label} l'article « {reference} » ?"
        ):
            return

        if self._toggle_status(article_id, currently_active):
            self.refresh()

    def _toggle_status(self, article_id: int, currently_active: bool) -> bool:
        """Effectue le changement de statut. Isolé de ``_on_toggle_clicked``
        pour rester testable sans boîte de confirmation modale."""
        try:
            if currently_active:
                updated = self._article_service.deactivate_article(article_id)
                QMessageBox.information(
                    self, "Article désactivé", f"L'article « {updated.reference} » a été désactivé."
                )
            else:
                updated = self._article_service.activate_article(article_id)
                QMessageBox.information(
                    self, "Article activé", f"L'article « {updated.reference} » a été activé."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True
