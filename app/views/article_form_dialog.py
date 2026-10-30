"""Formulaire de création/modification d'un article.

Ne connaît rien du service métier : collecte uniquement une saisie et la
restitue sous forme de dictionnaire de chaînes ; c'est :class:`ArticlesPage`
qui appelle ``ArticleService`` et gère la validation (même principe que les
formulaires Catégories/Fournisseurs/Motifs de sortie).

Point important : ce formulaire n'expose **aucun** champ « stock actuel »
librement modifiable. En création, seul un « stock initial » est proposé
(traité par le service comme une opération d'initialisation tracée, pas
comme une affectation directe). En modification, le stock actuel et le CMUP
sont affichés en lecture seule, avec une mention explicite qu'ils sont
pilotés par le système.

Lot « Gestion du mode Vente / Location » : expose également un sélecteur de
mode de gestion (Vente/Location, Vente par défaut à la création) et active
en conséquence le champ tarif de location journalier. Ce choix ne modifie
jamais directement ``Article.mode_gestion`` : c'est :class:`ArticlesPage`
qui, après création/modification des autres champs, appelle
``ArticleService.switch_mode_gestion`` si le mode diffère de celui déjà
enregistré — exactement comme le bouton « Mode de gestion… » existant.

Évolution F : le champ Unité est désormais une liste fermée (``unites``,
fournie par l'appelant) plutôt qu'une saisie libre — élimine les doublons
et fautes de frappe (§7.1). Le bouton « Nouveau » qui l'accompagne délègue
entièrement la création à ``on_create_unite`` (callback zéro-argument,
même principe que ``on_create_client`` dans ``SaleFormDialog``) : ce
dialogue ne connaît ni le service, ni la validation d'unicité. Un article
existant dont l'unité ne figure pas dans ``unites`` (saisie libre
antérieure à ce lot) reste affichée et modifiable sans aucune altération
silencieuse — ajoutée temporairement à la liste, jamais à la table de
référence tant que l'utilisateur ne la change pas explicitement.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import ModeGestionArticle
from app.utils.quantity import format_quantity
from app.views.common import build_required_field_legend, format_decimal_for_input, required_label

_DEFAULT_UNITE = "Pièce"

_MODE_GESTION_LABELS = {
    ModeGestionArticle.VENTE: "Vente",
    ModeGestionArticle.LOCATION: "Location",
}


class ArticleFormDialog(QDialog):
    def __init__(
        self,
        categories: list[tuple[int, str]],
        suppliers: list[tuple[int, str]],
        unites: list[str],
        initial: Optional[dict] = None,
        is_edit: bool = False,
        on_create_unite: Optional[Callable[[], Optional[str]]] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        initial = initial or {}
        self.is_edit = is_edit
        self._on_create_unite = on_create_unite

        self.setWindowTitle("Article")
        self.setModal(True)
        # Formulaire en deux colonnes (§6 de la finition ergonomique) :
        # réduit sensiblement la hauteur du dialogue par rapport à l'ancienne
        # colonne unique, qui imposait beaucoup de défilement. 760px laisse
        # assez de place aux libellés longs (« Tarif de location (par
        # jour) ») sans écraser les champs — reste très confortable même à
        # 1366×768 pour un dialogue modal, jamais une largeur fixe
        # (redimensionnement plus étroit toujours possible).
        self.setMinimumWidth(760)

        layout = QVBoxLayout(self)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(28)
        left_form = QFormLayout()
        left_form.setSpacing(10)
        right_form = QFormLayout()
        right_form.setSpacing(10)
        columns_row.addLayout(left_form, 1)
        columns_row.addLayout(right_form, 1)

        # -- Colonne gauche -----------------------------------------------

        self.reference_edit = QLineEdit(self)
        self.reference_edit.setText(initial.get("reference", ""))
        self.reference_edit.setMinimumWidth(160)
        left_form.addRow(required_label("Référence"), self.reference_edit)

        self.category_combo = QComboBox(self)
        for category_id, nom in categories:
            self.category_combo.addItem(nom, category_id)
        self._select_combo_data(self.category_combo, initial.get("category_id"))
        left_form.addRow(required_label("Catégorie"), self.category_combo)

        self.unite_row = QHBoxLayout()
        self.unite_combo = QComboBox(self)
        self._populate_unite_combo(unites, initial.get("unite"))
        self.unite_row.addWidget(self.unite_combo)
        self.new_unite_button = QPushButton("Nouveau", self)
        self.new_unite_button.setEnabled(on_create_unite is not None)
        self.new_unite_button.clicked.connect(self._on_new_unite_clicked)
        self.unite_row.addWidget(self.new_unite_button)
        left_form.addRow(required_label("Unité"), self.unite_row)

        self.prix_achat_edit = QLineEdit(self)
        self.prix_achat_edit.setText(_as_text(initial.get("prix_achat"), default="0"))
        left_form.addRow(required_label("Prix d'achat"), self.prix_achat_edit)

        # Module Locations (lot dédié) puis lot « Gestion du mode Vente /
        # Location » : le mode choisi ici ne modifie jamais directement
        # Article.mode_gestion — ArticlesPage._submit_form appelle
        # ArticleService.switch_mode_gestion après création/modification des
        # autres champs, exactement comme le bouton « Mode de gestion… »
        # déjà existant (conservé, inchangé). Toujours Vente par défaut pour
        # un nouvel article (comportement préservé).
        self.mode_gestion_combo = QComboBox(self)
        for mode, label in _MODE_GESTION_LABELS.items():
            self.mode_gestion_combo.addItem(label, mode)
        self._select_combo_data(
            self.mode_gestion_combo, initial.get("mode_gestion", ModeGestionArticle.VENTE)
        )
        left_form.addRow("Mode de gestion", self.mode_gestion_combo)

        # Tarif catalogue journalier de location — désactivé (mais jamais
        # effacé) en mode Vente, où il reste sans objet ; activé en mode
        # Location, où ArticlesPage exige qu'il soit strictement positif
        # avant d'appliquer la bascule (voir ArticlesPage._submit_form).
        self.tarif_location_jour_edit = QLineEdit(self)
        self.tarif_location_jour_edit.setText(
            _as_text(initial.get("tarif_location_jour")) if initial.get("tarif_location_jour") is not None else ""
        )
        left_form.addRow("Tarif de location (par jour)", self.tarif_location_jour_edit)
        self.mode_gestion_combo.currentIndexChanged.connect(self._update_price_fields_state)

        self.stock_min_edit = QLineEdit(self)
        self.stock_min_edit.setText(
            format_quantity(initial["stock_min"]) if initial.get("stock_min") is not None else "0"
        )
        left_form.addRow(required_label("Stock minimum"), self.stock_min_edit)

        # -- Colonne droite -------------------------------------------------

        self.designation_edit = QLineEdit(self)
        self.designation_edit.setText(initial.get("designation", ""))
        self.designation_edit.setMinimumWidth(160)
        right_form.addRow(required_label("Désignation"), self.designation_edit)

        self.supplier_combo = QComboBox(self)
        self.supplier_combo.addItem("(Aucun)", None)
        for supplier_id, nom in suppliers:
            self.supplier_combo.addItem(nom, supplier_id)
        self._select_combo_data(self.supplier_combo, initial.get("fournisseur_principal_id"))
        right_form.addRow("Fournisseur principal", self.supplier_combo)

        self.prix_vente_edit = QLineEdit(self)
        self.prix_vente_edit.setText(_as_text(initial.get("prix_vente"), default="0"))
        right_form.addRow(required_label("Prix de vente"), self.prix_vente_edit)

        self.stock_max_edit = QLineEdit(self)
        self.stock_max_edit.setText(
            format_quantity(initial["stock_max"]) if initial.get("stock_max") is not None else ""
        )
        right_form.addRow("Stock maximum", self.stock_max_edit)

        self.stock_initial_edit: Optional[QLineEdit] = None
        self.stock_actuel_label: Optional[QLabel] = None
        self.cmup_label: Optional[QLabel] = None

        if is_edit:
            self.stock_actuel_label = QLabel(
                format_quantity(initial["stock_actuel"]) if initial.get("stock_actuel") is not None else "0", self
            )
            self.stock_actuel_label.setStyleSheet("color: #6B7280;")
            right_form.addRow("Stock actuel (piloté par le système)", self.stock_actuel_label)

            self.cmup_label = QLabel(_as_text(initial.get("cout_moyen_pondere"), default="0"), self)
            self.cmup_label.setStyleSheet("color: #6B7280;")
            right_form.addRow("CMUP (piloté par le système)", self.cmup_label)
        else:
            self.stock_initial_edit = QLineEdit(self)
            self.stock_initial_edit.setText("0")
            right_form.addRow(required_label("Stock initial"), self.stock_initial_edit)

        self.emplacement_edit = QLineEdit(self)
        self.emplacement_edit.setText(initial.get("emplacement", "") or "")
        right_form.addRow("Emplacement", self.emplacement_edit)

        self.code_barres_edit = QLineEdit(self)
        self.code_barres_edit.setText(initial.get("code_barres", "") or "")
        right_form.addRow("Code-barres", self.code_barres_edit)

        # Appelé une fois les deux colonnes construites (lit à la fois
        # tarif_location_jour_edit — colonne gauche — et prix_vente_edit —
        # colonne droite).
        self._update_price_fields_state()

        layout.addLayout(columns_row)

        # Description : occupe toute la largeur du dialogue, sous les deux
        # colonnes (§6 : « zone suffisamment large en bas du formulaire »).
        # Conservée dans son propre QFormLayout (plutôt qu'un simple QLabel
        # à côté) pour garder un libellé réellement associé au champ, comme
        # partout ailleurs dans ce dialogue.
        description_form = QFormLayout()
        self.description_edit = QTextEdit(self)
        self.description_edit.setPlainText(initial.get("description", "") or "")
        self.description_edit.setFixedHeight(60)
        description_form.addRow("Description", self.description_edit)
        layout.addLayout(description_form)

        layout.addWidget(build_required_field_legend(self))

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Enregistrer", self)
        self.save_button.setProperty("variant", "primary")
        self.save_button.setDefault(True)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    @staticmethod
    def _select_combo_data(combo: QComboBox, data) -> None:
        if data is None:
            return
        index = combo.findData(data)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _populate_unite_combo(self, unites: list[str], current_unite: Optional[str]) -> None:
        """§7.1/§7.2 : liste fermée (plus de ``setEditable``). ``Pièce`` par
        défaut à la création (§7.2) quand elle figure dans la liste ; en
        modification, l'unité déjà enregistrée est toujours sélectionnée —
        y compris si elle ne figure pas dans ``unites`` (saisie libre
        antérieure à ce lot, §7.4) : ajoutée ici pour l'affichage, jamais à
        la table de référence tant que l'utilisateur ne la change pas
        explicitement."""
        self.unite_combo.clear()
        self.unite_combo.addItems(unites)
        if current_unite and self.unite_combo.findText(current_unite) == -1:
            self.unite_combo.addItem(current_unite)
        if current_unite:
            self.unite_combo.setCurrentText(current_unite)
        elif self.unite_combo.findText(_DEFAULT_UNITE) != -1:
            self.unite_combo.setCurrentText(_DEFAULT_UNITE)

    def _on_new_unite_clicked(self) -> None:
        if self._on_create_unite is None:
            return
        libelle = self._on_create_unite()
        if libelle is None:
            return
        if self.unite_combo.findText(libelle) == -1:
            self.unite_combo.addItem(libelle)
        self.unite_combo.setCurrentText(libelle)

    def _update_price_fields_state(self) -> None:
        """Actualise immédiatement l'état des deux champs de prix au
        changement de mode (Lot 18, symétrique du comportement déjà en
        place pour le tarif de location depuis le lot « Gestion du mode
        Vente / Location ») : désactivé mais jamais vidé dans le mode où il
        est sans objet — la saisie déjà faite (ou déjà enregistrée) n'est
        jamais perdue par un simple aller-retour entre les deux modes avant
        enregistrement. ``setEnabled`` seul n'affecte jamais le texte d'un
        ``QLineEdit`` : ``values()`` continue de renvoyer la valeur réelle
        même pour un champ désactivé."""
        is_location = self.mode_gestion_combo.currentData() == ModeGestionArticle.LOCATION
        self.tarif_location_jour_edit.setEnabled(is_location)
        self.tarif_location_jour_edit.setPlaceholderText(
            "Tarif strictement positif requis en mode Location" if is_location else "Sans objet en mode Vente"
        )
        self.prix_vente_edit.setEnabled(not is_location)

    def values(self) -> dict:
        return {
            "reference": self.reference_edit.text(),
            "designation": self.designation_edit.text(),
            "category_id": self.category_combo.currentData(),
            "fournisseur_principal_id": self.supplier_combo.currentData(),
            "unite": self.unite_combo.currentText(),
            # Correctif (incident « mode de gestion ») : QComboBox.currentData()
            # restitue la donnée associée via QVariant — pour un membre d'une
            # énumération dérivant de ``str`` (``ModeGestionArticle(str, Enum)``),
            # PySide6 la convertit silencieusement en ``str`` nu à la lecture
            # (confirmé empiriquement : type(combo.currentData()) is str, pas
            # ModeGestionArticle, bien que ``addItem`` ait reçu le membre
            # d'énumération lui-même). La comparaison ``== ModeGestionArticle.X``
            # reste vraie malgré cela (égalité de chaîne), ce qui masquait le
            # problème jusqu'ici — mais tout accès à ``.value`` plus loin
            # (``ArticleService.switch_mode_gestion``) levait
            # ``AttributeError: 'str' object has no attribute 'value'``.
            # Reconstruire explicitement le membre d'énumération ici, à la
            # frontière Qt -> code applicatif, est sans risque : le
            # constructeur d'une énumération retourne le membre déjà existant
            # si on lui passe un membre, et le reconstruit depuis sa valeur
            # sinon — jamais une conversion « aveugle », seulement la
            # restitution du type que cette méthode déclare déjà retourner.
            "mode_gestion": ModeGestionArticle(self.mode_gestion_combo.currentData()),
            "prix_achat": self.prix_achat_edit.text(),
            "prix_vente": self.prix_vente_edit.text(),
            "stock_min": self.stock_min_edit.text(),
            "stock_max": self.stock_max_edit.text(),
            "emplacement": self.emplacement_edit.text(),
            "code_barres": self.code_barres_edit.text(),
            "description": self.description_edit.toPlainText(),
            "stock_initial": self.stock_initial_edit.text() if self.stock_initial_edit else "0",
            "tarif_location_jour": self.tarif_location_jour_edit.text(),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)


def _as_text(value, default: str = "") -> str:
    """Lot 23 (§E) : les champs utilisant ce helper sont tous des montants
    (prix d'achat/vente, tarif de location, CMUP) — ``format_decimal_for_input``
    supprime les décimales superflues (``7500.00`` -> ``7500``) sans jamais
    perdre une décimale réellement significative."""
    if value is None:
        return default
    return format_decimal_for_input(value)
