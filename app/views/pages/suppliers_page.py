"""Page de gestion des fournisseurs.

Mêmes conventions visuelles et le même comportement que ``CategoriesPage``
(tableau, recherche, boutons Ajouter/Modifier/Activer-désactiver,
confirmation avant opération sensible, messages d'erreur/succès). Toute
action passe par :class:`SupplierService`, qui revérifie la permission côté
service — les boutons ne sont désactivés que par confort d'usage.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.auth.permission_service import PermissionService
from app.services.suppliers.supplier_service import SupplierService
from app.utils.exceptions import AppError
from app.views.common import confirm_action, run_modal_form
from app.views.supplier_form_dialog import SupplierFormDialog

_COLUMNS = ["Nom", "Contact", "Téléphone", "Email", "Ville", "Statut", "Créé le", "Modifié le"]


class SuppliersPage(QWidget):
    def __init__(
        self,
        supplier_service: SupplierService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._supplier_service = supplier_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher un fournisseur…")
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)

        self.add_button = QPushButton("Ajouter", self)
        self.add_button.setEnabled(self._permissions.has_permission("SUPPLIER_CREATE"))
        toolbar.addWidget(self.add_button)

        self.edit_button = QPushButton("Modifier", self)
        self.edit_button.setEnabled(self._permissions.has_permission("SUPPLIER_UPDATE"))
        toolbar.addWidget(self.edit_button)

        self.toggle_button = QPushButton("Activer / désactiver", self)
        self.toggle_button.setEnabled(
            self._permissions.has_permission("SUPPLIER_ACTIVATE")
            or self._permissions.has_permission("SUPPLIER_DEACTIVATE")
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
        self.add_button.clicked.connect(self._on_add_clicked)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.toggle_button.clicked.connect(self._on_toggle_clicked)

        self.refresh()

    # -- affichage ---------------------------------------------------------

    def refresh(self) -> None:
        try:
            suppliers = self._supplier_service.list_suppliers(search=self.search_edit.text())
        except AppError:
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(suppliers))
        for row, supplier in enumerate(suppliers):
            name_item = QTableWidgetItem(supplier.nom)
            name_item.setData(Qt.ItemDataRole.UserRole, supplier.id)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(supplier.contact or ""))
            self.table.setItem(row, 2, QTableWidgetItem(supplier.telephone or ""))
            self.table.setItem(row, 3, QTableWidgetItem(supplier.email or ""))
            self.table.setItem(row, 4, QTableWidgetItem(supplier.ville or ""))
            self.table.setItem(row, 5, QTableWidgetItem("Actif" if supplier.actif else "Inactif"))
            self.table.setItem(
                row, 6, QTableWidgetItem(supplier.date_creation.strftime("%Y-%m-%d %H:%M"))
            )
            self.table.setItem(
                row, 7, QTableWidgetItem(supplier.date_modification.strftime("%Y-%m-%d %H:%M"))
            )

    def _selected_row(self) -> Optional[int]:
        selected = self.table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    # -- création / modification --------------------------------------------

    def _on_add_clicked(self) -> None:
        self._open_form(supplier_id=None, initial={})

    def _on_edit_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        supplier_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        initial = self._load_edit_initial(supplier_id)
        if initial is None:
            return
        self._open_form(supplier_id=supplier_id, initial=initial)

    def _load_edit_initial(self, supplier_id: int) -> Optional[dict]:
        """Récupère les valeurs actuelles d'un fournisseur pour pré-remplir le
        formulaire de modification (y compris les champs non affichés en
        colonnes : adresse, pays, observations). Isolé de ``_on_edit_clicked``
        pour rester testable sans dialogue modal."""
        try:
            full = self._supplier_service.get_supplier(supplier_id)
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return None
        return {
            "nom": full.nom,
            "contact": full.contact or "",
            "telephone": full.telephone or "",
            "email": full.email or "",
            "adresse": full.adresse or "",
            "ville": full.ville or "",
            "pays": full.pays or "",
            "observations": full.observations or "",
        }

    def _open_form(self, supplier_id: Optional[int], initial: dict) -> None:
        state = {"values": initial}

        def factory() -> SupplierFormDialog:
            return SupplierFormDialog(state["values"], parent=self)

        def submit(dialog: SupplierFormDialog) -> bool:
            state["values"] = dialog.values()
            return self._submit_form(supplier_id, state["values"])

        run_modal_form(factory, submit)
        self.refresh()

    def _submit_form(self, supplier_id: Optional[int], values: dict) -> bool:
        """Effectue l'appel service et affiche le résultat. Isolé de
        ``_open_form`` pour rester testable sans dialogue modal."""
        nom = values["nom"]
        kwargs = {
            "contact": values.get("contact"),
            "telephone": values.get("telephone"),
            "email": values.get("email"),
            "adresse": values.get("adresse"),
            "ville": values.get("ville"),
            "pays": values.get("pays"),
            "observations": values.get("observations"),
        }
        try:
            if supplier_id is None:
                self._supplier_service.create_supplier(nom, **kwargs)
                QMessageBox.information(
                    self, "Fournisseur créé", f"Le fournisseur « {nom} » a été créé."
                )
            else:
                self._supplier_service.update_supplier(supplier_id, nom, **kwargs)
                QMessageBox.information(
                    self, "Fournisseur modifié", f"Le fournisseur « {nom} » a été modifié."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True

    # -- activation / désactivation -----------------------------------------

    def _on_toggle_clicked(self) -> None:
        row = self._selected_row()
        if row is None:
            return

        supplier_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        name = self.table.item(row, 0).text()
        currently_active = self.table.item(row, 5).text() == "Actif"
        action_label = "désactiver" if currently_active else "activer"

        if not confirm_action(
            self, "Confirmation", f"Voulez-vous vraiment {action_label} le fournisseur « {name} » ?"
        ):
            return

        if self._toggle_status(supplier_id, currently_active):
            self.refresh()

    def _toggle_status(self, supplier_id: int, currently_active: bool) -> bool:
        """Effectue le changement de statut. Isolé de ``_on_toggle_clicked``
        pour rester testable sans boîte de confirmation modale."""
        try:
            if currently_active:
                updated = self._supplier_service.deactivate_supplier(supplier_id)
                QMessageBox.information(
                    self, "Fournisseur désactivé", f"Le fournisseur « {updated.nom} » a été désactivé."
                )
            else:
                updated = self._supplier_service.activate_supplier(supplier_id)
                QMessageBox.information(
                    self, "Fournisseur activé", f"Le fournisseur « {updated.nom} » a été activé."
                )
        except AppError as exc:
            QMessageBox.warning(self, "Opération refusée", str(exc))
            return False
        return True
