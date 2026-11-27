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

Mission 4, §4 : bouton « Supprimer » symétrique, pour retirer une unité
créée par erreur — délègue de la même façon à ``on_delete_unite`` (callback
prenant le libellé actuellement sélectionné) : ce dialogue ne connaît ni la
vérification d'usage, ni la confirmation, ni la suppression elle-même,
toutes entièrement du ressort de l'appelant (``ArticlesPage``).

Mission 5, §2/§3 : tarifs alternatifs (sous-traitant + intervalle « autre »)
pour la vente ET pour la location, totalement indépendants l'un de l'autre.
Entièrement facultatifs (laissés vides, aucun tarif alternatif n'est
configuré) et soumis au même activation/désactivation par mode de gestion
que les champs existants qu'ils complètent (``prix_vente``/
``tarif_location_jour``) — jamais vidés, seulement désactivés dans le mode
où ils sont sans objet. La validation côté serveur (``ArticleService``) reste
seule autoritaire et obligatoire ; ce formulaire ne fait que collecter la
saisie. Le contenu du formulaire est désormais placé dans une zone
défilante : les six nouveaux champs auraient autrement rendu le dialogue
trop haut pour un écran 1366×768.

Mission 5.2 (Problème B) : les deux bornes de chaque intervalle « Autre
prix »/« Autre tarif location » sont regroupées sur une seule ligne
(« Autre prix : [début] à [fin] »), plutôt que deux lignes de formulaire
distinctes — présentation plus compacte, sans changer les noms de champs.

Mission 5.2 (Problème C) : ce formulaire appelle désormais
``ArticleService.validate_tariff_interval`` (même fonction que le service,
jamais une réimplémentation) pendant la saisie, pour avertir immédiatement
d'une incohérence tarifaire près du champ concerné — purement indicatif,
cette validation ne remplace jamais celle, obligatoire, du service au
moment de l'enregistrement. Au clic sur « Enregistrer », ``on_submit``
(fourni par ``ArticlesPage``) est appelé AVANT tout ``accept()`` : le
dialogue ne se ferme que si l'enregistrement réussit réellement, jamais
sur une erreur de validation (voir ``_on_save_clicked``) — c'est ce qui
évite l'ancien effet de fermeture/réouverture (``run_modal_form``
recréait un nouveau dialogue à chaque tentative ratée).
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import ModeGestionArticle
from app.services.articles.article_service import validate_tariff_interval
from app.utils.exceptions import ValidationError
from app.utils.quantity import format_quantity
from app.views.common import (
    FormSubmitResult,
    build_required_field_legend,
    format_decimal_for_input,
    parse_optional_decimal,
    required_label,
)
from app.views.design_system import refresh_style

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
        on_delete_unite: Optional[Callable[[str], Optional[tuple[list[str], Optional[str]]]]] = None,
        on_submit: Optional[Callable[[dict], FormSubmitResult]] = None,
        multi_price_enabled: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        initial = initial or {}
        self.is_edit = is_edit
        # Mission « Gestion configurable des prix multiples » : décidé une
        # fois par l'appelant (``is_multi_price_enabled()``, voir
        # ``ArticlesPage``), jamais relu ici. ``True`` par défaut — aucun
        # appelant existant (tests compris) qui ne précise pas ce paramètre
        # ne voit son comportement changer.
        self._multi_price_enabled = multi_price_enabled
        self._on_create_unite = on_create_unite
        self._on_delete_unite = on_delete_unite
        # Mission 5.2, Problème C : si fourni, appelé AVANT tout ``accept()``
        # — voir ``_on_save_clicked``. ``None`` préserve exactement l'ancien
        # comportement (accepte toujours), pour les appelants/tests qui ne
        # branchent aucune validation de service sur ce dialogue.
        self._on_submit = on_submit
        self._highlighted_widgets: list[QWidget] = []

        self.setWindowTitle("Article")
        self.setModal(True)
        self.setMinimumWidth(820)

        layout = QVBoxLayout(self)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)

        columns_row = QHBoxLayout()
        columns_row.setSpacing(28)
        left_form = QFormLayout()
        left_form.setSpacing(10)
        right_form = QFormLayout()
        right_form.setSpacing(10)
        # Mission 5.2, Problème A : sur Windows, certains libellés longs
        # (« Tarif de location sous-traitant », « Stock actuel (piloté par
        # le système) »...) forçaient chaque colonne — et donc le dialogue
        # entier, via la zone défilante ci-dessous — à exiger une largeur
        # minimale supérieure à ce que la fenêtre proposait, provoquant un
        # défilement horizontal. ``WrapLongRows`` (plutôt qu'un simple
        # agrandissement de la fenêtre, qui ne règle rien structurellement)
        # fait passer l'étiquette au-dessus du champ sur les lignes trop
        # étroites, bornant la largeur minimale de chaque colonne à celle du
        # champ lui-même plutôt qu'à « étiquette + champ » côte à côte.
        left_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        right_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
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
        # Mission 4, §4.1 : action symétrique de « Nouveau », pour retirer
        # une unité créée par erreur — rouge et icône explicite, jamais
        # confondue avec les actions neutres/positives qui l'entourent.
        # Icône seule (option explicitement prévue par la mission) plutôt
        # qu'icône + texte : cette ligne de formulaire, déjà partagée avec le
        # sélecteur et le bouton « Nouveau », reste étroite dans la mise en
        # page en deux colonnes — ne pas la surcharger.
        self.delete_unite_button = QPushButton(self)
        self.delete_unite_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.delete_unite_button.setToolTip("Supprimer l'unité sélectionnée")
        self.delete_unite_button.setProperty("variant", "danger")
        self.delete_unite_button.setFixedWidth(40)
        self.delete_unite_button.setEnabled(on_delete_unite is not None)
        self.delete_unite_button.clicked.connect(self._on_delete_unite_clicked)
        self.unite_row.addWidget(self.delete_unite_button)
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

        # Mission 5, §3 : tarifs alternatifs de location — entièrement
        # indépendants des tarifs de vente (jamais dérivés l'un de l'autre).
        self.tarif_location_sous_traitant_edit = QLineEdit(self)
        self.tarif_location_sous_traitant_edit.setPlaceholderText("Facultatif")
        self.tarif_location_sous_traitant_edit.setText(
            _as_text(initial.get("tarif_location_sous_traitant"))
            if initial.get("tarif_location_sous_traitant") is not None else ""
        )
        left_form.addRow("Tarif de location sous-traitant", self.tarif_location_sous_traitant_edit)

        # Mission 5.2, Problème B : les deux bornes regroupées sur une seule
        # ligne (« Autre tarif location : [début] à [fin] ») plutôt que deux
        # lignes de formulaire distinctes — mêmes champs, mêmes noms
        # (``tarif_location_autre_min``/``tarif_location_autre_max``),
        # seule la présentation change.
        self.tarif_location_autre_min_edit = QLineEdit(self)
        self.tarif_location_autre_min_edit.setPlaceholderText("Facultatif")
        self.tarif_location_autre_min_edit.setMaximumWidth(130)
        self.tarif_location_autre_min_edit.setText(
            _as_text(initial.get("tarif_location_autre_min"))
            if initial.get("tarif_location_autre_min") is not None else ""
        )
        self.tarif_location_autre_max_edit = QLineEdit(self)
        self.tarif_location_autre_max_edit.setPlaceholderText("Facultatif")
        self.tarif_location_autre_max_edit.setMaximumWidth(130)
        self.tarif_location_autre_max_edit.setText(
            _as_text(initial.get("tarif_location_autre_max"))
            if initial.get("tarif_location_autre_max") is not None else ""
        )
        tarif_location_autre_row = QHBoxLayout()
        tarif_location_autre_row.addWidget(self.tarif_location_autre_min_edit)
        tarif_location_autre_row.addWidget(QLabel("à", self))
        tarif_location_autre_row.addWidget(self.tarif_location_autre_max_edit)
        tarif_location_autre_row.addStretch(1)
        left_form.addRow("Autre tarif location", tarif_location_autre_row)

        # Avertissement de cohérence (Mission 5.2, Problème C, §A) : affiché
        # près du groupe concerné pendant la saisie, jamais pour un champ
        # facultatif resté vide (voir ``_apply_tariff_group_validity``) —
        # purement indicatif, la validation du service reste seule
        # obligatoire au moment de l'enregistrement.
        self.location_tariff_warning_label = QLabel("", self)
        self.location_tariff_warning_label.setStyleSheet("color: #B54708; font-size: 11px;")
        self.location_tariff_warning_label.setWordWrap(True)
        left_form.addRow(self.location_tariff_warning_label)

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

        # Mission 5, §2 : tarifs alternatifs de vente — entièrement
        # facultatifs, co-localisés avec le prix de vente qu'ils complètent.
        self.prix_sous_traitant_edit = QLineEdit(self)
        self.prix_sous_traitant_edit.setPlaceholderText("Facultatif")
        self.prix_sous_traitant_edit.setText(
            _as_text(initial.get("prix_sous_traitant")) if initial.get("prix_sous_traitant") is not None else ""
        )
        right_form.addRow("Prix sous-traitant", self.prix_sous_traitant_edit)

        # Mission 5.2, Problème B : même regroupement que « Autre tarif
        # location » ci-dessus — « Autre prix : [début] à [fin] ».
        self.prix_autre_min_edit = QLineEdit(self)
        self.prix_autre_min_edit.setPlaceholderText("Facultatif")
        self.prix_autre_min_edit.setMaximumWidth(130)
        self.prix_autre_min_edit.setText(
            _as_text(initial.get("prix_autre_min")) if initial.get("prix_autre_min") is not None else ""
        )
        self.prix_autre_max_edit = QLineEdit(self)
        self.prix_autre_max_edit.setPlaceholderText("Facultatif")
        self.prix_autre_max_edit.setMaximumWidth(130)
        self.prix_autre_max_edit.setText(
            _as_text(initial.get("prix_autre_max")) if initial.get("prix_autre_max") is not None else ""
        )
        prix_autre_row = QHBoxLayout()
        prix_autre_row.addWidget(self.prix_autre_min_edit)
        prix_autre_row.addWidget(QLabel("à", self))
        prix_autre_row.addWidget(self.prix_autre_max_edit)
        prix_autre_row.addStretch(1)
        right_form.addRow("Autre prix", prix_autre_row)

        self.sale_tariff_warning_label = QLabel("", self)
        self.sale_tariff_warning_label.setStyleSheet("color: #B54708; font-size: 11px;")
        self.sale_tariff_warning_label.setWordWrap(True)
        right_form.addRow(self.sale_tariff_warning_label)

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

        # Mission 5.2, Problème C : une seule table de correspondance
        # champ -> widget, utilisée à la fois pour mettre en évidence le
        # champ visé par une erreur de validation (voir
        # ``_highlight_invalid_fields``) et, implicitement, pour documenter
        # l'ensemble des clés attendues par ``values()``.
        self._field_widgets: dict[str, QWidget] = {
            "reference": self.reference_edit,
            "designation": self.designation_edit,
            "category_id": self.category_combo,
            "fournisseur_principal_id": self.supplier_combo,
            "unite": self.unite_combo,
            "prix_achat": self.prix_achat_edit,
            "prix_vente": self.prix_vente_edit,
            "stock_min": self.stock_min_edit,
            "stock_max": self.stock_max_edit,
            "emplacement": self.emplacement_edit,
            "code_barres": self.code_barres_edit,
            "tarif_location_jour": self.tarif_location_jour_edit,
            "prix_sous_traitant": self.prix_sous_traitant_edit,
            "prix_autre_min": self.prix_autre_min_edit,
            "prix_autre_max": self.prix_autre_max_edit,
            "tarif_location_sous_traitant": self.tarif_location_sous_traitant_edit,
            "tarif_location_autre_min": self.tarif_location_autre_min_edit,
            "tarif_location_autre_max": self.tarif_location_autre_max_edit,
        }
        if self.stock_initial_edit is not None:
            self._field_widgets["stock_initial"] = self.stock_initial_edit

        # Appelé une fois les deux colonnes construites (lit à la fois
        # tarif_location_jour_edit — colonne gauche — et prix_vente_edit —
        # colonne droite).
        self._update_price_fields_state()

        # Mission 5.2, Problème C, §A : avertissement de cohérence affiché
        # dès la saisie, jamais seulement au clic sur Enregistrer — voir
        # ``_apply_tariff_group_validity``. Les deux groupes (vente/location)
        # restent entièrement indépendants, comme la règle métier elle-même.
        for edit in (
            self.prix_vente_edit, self.prix_sous_traitant_edit,
            self.prix_autre_min_edit, self.prix_autre_max_edit,
        ):
            edit.textChanged.connect(self._revalidate_sale_tariffs)
        for edit in (
            self.tarif_location_jour_edit, self.tarif_location_sous_traitant_edit,
            self.tarif_location_autre_min_edit, self.tarif_location_autre_max_edit,
        ):
            edit.textChanged.connect(self._revalidate_location_tariffs)
        self._revalidate_sale_tariffs()
        self._revalidate_location_tariffs()

        content_layout.addLayout(columns_row)

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
        content_layout.addLayout(description_form)

        content_layout.addStretch(1)
        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

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
        # Mission 5.2, Problème C : plus jamais connecté directement à
        # ``self.accept`` — voir ``_on_save_clicked``, qui n'accepte (et donc
        # ne ferme) le dialogue qu'après un ``on_submit`` réellement réussi.
        self.save_button.clicked.connect(self._on_save_clicked)

        # Correction ergonomique (après Mission 5.2) : une hauteur fixe
        # (``resize(880, 700)``) décidée avant la construction du contenu
        # dépassait largement le besoin réel (~450-500 px selon le mode) —
        # combinée à ``scroll_area.setWidgetResizable(True)`` (qui étire le
        # contenu pour remplir toute la hauteur disponible) et au
        # ``addStretch(1)`` ci-dessus, l'écart se traduisait par un grand
        # espace vide entre la Description et le pied de formulaire. La
        # largeur reste fixée explicitement (`setMinimumWidth` ne suffit
        # pas à lui seul à choisir une largeur confortable) ; la hauteur,
        # elle, est désormais calculée à partir du contenu réellement
        # construit — jamais une valeur devinée à l'avance — en gardant une
        # marge raisonnable pour accueillir un message d'erreur sans
        # redimensionnement.
        self.resize(880, self.sizeHint().height() + 60)

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

    def _on_delete_unite_clicked(self) -> None:
        """Mission 4, §4.1/§4.5 : délègue entièrement la vérification
        d'usage, la confirmation et la suppression à l'appelant — ce
        dialogue ne fait que répercuter le résultat sur le menu déroulant
        (liste réactualisée + sélection d'une autre unité disponible),
        jamais de logique métier ici."""
        if self._on_delete_unite is None:
            return
        libelle = self.unite_combo.currentText()
        if not libelle:
            return
        result = self._on_delete_unite(libelle)
        if result is None:
            return
        remaining_unites, next_selected = result
        self._populate_unite_combo(remaining_unites, next_selected)

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
        # Mission 5 : les tarifs alternatifs suivent le même état que le
        # tarif normal qu'ils complètent — jamais vidés, seulement
        # désactivés dans le mode où ils sont sans objet. Mission « Gestion
        # configurable des prix multiples » : désactivés de la même façon
        # (jamais vidés — voir la docstring de cette méthode) dès que les
        # prix multiples sont désactivés pour cette installation, quel que
        # soit le mode par ailleurs.
        extra_price_placeholder = (
            "Facultatif" if self._multi_price_enabled else "Prix multiples désactivés pour cette installation"
        )
        for edit in (self.prix_sous_traitant_edit, self.prix_autre_min_edit, self.prix_autre_max_edit):
            edit.setEnabled(not is_location and self._multi_price_enabled)
            if not self._multi_price_enabled:
                edit.setPlaceholderText(extra_price_placeholder)
        for edit in (
            self.tarif_location_sous_traitant_edit,
            self.tarif_location_autre_min_edit,
            self.tarif_location_autre_max_edit,
        ):
            edit.setEnabled(is_location and self._multi_price_enabled)
            if not self._multi_price_enabled:
                edit.setPlaceholderText(extra_price_placeholder)
        # Un changement de mode peut rendre pertinent un avertissement
        # jusqu'ici masqué par un champ désactivé (ou l'inverse) — toujours
        # recalculé ici, jamais laissé dans un état obsolète.
        self._revalidate_sale_tariffs()
        self._revalidate_location_tariffs()

    # -- Mission 5.2, Problème C, §A : avertissement pendant la saisie --------------
    #
    # Purement indicatif : réutilise ``ArticleService.validate_tariff_interval``
    # (jamais une réimplémentation des règles) pour prévenir l'utilisateur au
    # plus tôt, mais ne remplace jamais la validation obligatoire du service
    # au moment de l'enregistrement (voir ``_on_save_clicked``).

    def _revalidate_sale_tariffs(self) -> None:
        self._apply_tariff_group_validity(
            normal_edit=self.prix_vente_edit,
            sous_traitant_edit=self.prix_sous_traitant_edit,
            min_edit=self.prix_autre_min_edit,
            max_edit=self.prix_autre_max_edit,
            label="de vente (autre prix)",
            warning_label=self.sale_tariff_warning_label,
        )

    def _revalidate_location_tariffs(self) -> None:
        self._apply_tariff_group_validity(
            normal_edit=self.tarif_location_jour_edit,
            sous_traitant_edit=self.tarif_location_sous_traitant_edit,
            min_edit=self.tarif_location_autre_min_edit,
            max_edit=self.tarif_location_autre_max_edit,
            label="de location (autre tarif)",
            warning_label=self.location_tariff_warning_label,
        )

    def _apply_tariff_group_validity(
        self,
        *,
        normal_edit: QLineEdit,
        sous_traitant_edit: QLineEdit,
        min_edit: QLineEdit,
        max_edit: QLineEdit,
        label: str,
        warning_label: QLabel,
    ) -> None:
        edits = (normal_edit, sous_traitant_edit, min_edit, max_edit)
        for edit in edits:
            edit.setProperty("valid", None)
            refresh_style(edit)
        try:
            normal = parse_optional_decimal(normal_edit.text(), "prix normal")
            sous_traitant = parse_optional_decimal(sous_traitant_edit.text(), "prix sous-traitant")
            intervalle_min = parse_optional_decimal(min_edit.text(), "début de l'intervalle")
            intervalle_max = parse_optional_decimal(max_edit.text(), "fin de l'intervalle")
        except ValidationError:
            # Format de nombre invalide : ce n'est pas une incohérence
            # tarifaire — chaque champ numérique reste responsable de son
            # propre contrôle de saisie ; pas de double message ici.
            warning_label.setText("")
            return
        try:
            validate_tariff_interval(
                prix_normal=normal, prix_sous_traitant=sous_traitant,
                intervalle_min=intervalle_min, intervalle_max=intervalle_max, label=label,
            )
        except ValidationError as exc:
            message = str(exc)
            warning_label.setText(message)
            invalid_edits = [min_edit, max_edit]
            if "sous-traitant" in message:
                invalid_edits.insert(0, sous_traitant_edit)
            if "prix normal" in message:
                invalid_edits.insert(0, normal_edit)
            for edit in invalid_edits:
                edit.setProperty("valid", False)
                refresh_style(edit)
            return
        warning_label.setText("")

    # -- Mission 5.2, Problème C, §B : validation au clic sur Enregistrer -----------

    def _on_save_clicked(self) -> None:
        self._clear_field_highlight()
        if self._on_submit is None:
            self.accept()
            return
        result = self._on_submit(self.values())
        if result.success:
            self.accept()
            return
        self.set_error(result.message)
        self._highlight_invalid_fields(result.fields)

    def _clear_field_highlight(self) -> None:
        for widget in self._highlighted_widgets:
            widget.setProperty("valid", None)
            refresh_style(widget)
        self._highlighted_widgets = []

    def _highlight_invalid_fields(self, fields: tuple[str, ...]) -> None:
        """Mission 5.2, Problème C, §B (points 5/6) : met en évidence
        chaque champ concerné et place le curseur sur le premier d'entre
        eux — jamais de fermeture du dialogue, jamais de perte de saisie
        (voir ``_on_save_clicked``, qui n'appelle ``accept()`` qu'en cas de
        succès)."""
        focused = False
        for key in fields:
            widget = self._field_widgets.get(key)
            if widget is None:
                continue
            widget.setProperty("valid", False)
            refresh_style(widget)
            self._highlighted_widgets.append(widget)
            if not focused:
                widget.setFocus()
                if isinstance(widget, QLineEdit):
                    widget.selectAll()
                focused = True

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
            "prix_sous_traitant": self.prix_sous_traitant_edit.text(),
            "prix_autre_min": self.prix_autre_min_edit.text(),
            "prix_autre_max": self.prix_autre_max_edit.text(),
            "tarif_location_sous_traitant": self.tarif_location_sous_traitant_edit.text(),
            "tarif_location_autre_min": self.tarif_location_autre_min_edit.text(),
            "tarif_location_autre_max": self.tarif_location_autre_max_edit.text(),
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
