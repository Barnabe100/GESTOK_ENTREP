"""Formulaire de création/modification d'un inventaire (date + lignes
dynamiques).

Le stock actuel n'est jamais un champ modifiable ici : chaque ligne affiche
le stock théorique système (lecture seule, capturé au moment de l'ajout de
la ligne — voir ``InventoryService._build_lignes``) à côté du stock compté
(seule saisie), et l'écart est recalculé à l'affichage pour donner un
retour immédiat — la valeur qui fait foi reste celle capturée par le
service, jamais une valeur recalculée ici. Aucune ligne ajoutée/modifiée ne
modifie jamais le stock réel : seule la validation (bouton « Valider »,
``InventoryService.validate_inventory``) génère des mouvements d'ajustement.

Mission 5.5, Évolution C : la sélection d'article reprend l'ergonomie déjà
en place dans les écrans de caisse Ventes/Locations et dans Entrées/Sorties
(Mission 5.3) — recherche en direct (:class:`ArticleSearchPanel`, partagé)
plutôt qu'un dialogue séparé par ligne. Le scan code-barres ajoute
désormais directement une ligne (même point d'entrée que le double-clic
d'un résultat de recherche), au lieu d'ouvrir un formulaire pré-rempli — la
recherche manuelle et le scan restent entièrement indépendants et peuvent
coexister sans conflit (aucun état partagé entre les deux, chacun ne fait
qu'appeler ``_on_article_activated``). Le stock compté devient éditable
directement dans le tableau (même délégué ``QuantityEditDelegate`` que les
tableaux de caisse et d'Entrées/Sorties) ; le stock théorique et l'écart
restent strictement en lecture seule. ``InventoryLineFormDialog`` n'est plus
utilisé par ce formulaire mais n'est pas supprimé, à l'identique de
``SaleLineFormDialog``/``EntryLineFormDialog`` après leurs harmonisations
respectives. Aucune détection de doublon n'existe ni n'est introduite ici
(aucune ne préexistait dans ``InventoryService``/l'ancien formulaire).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.utils.exceptions import ValidationError
from app.utils.quantity import format_quantity, format_quantity_signed
from app.views.article_search_panel import ArticleSearchPanel
from app.views.common import (
    build_required_field_legend,
    date_to_qdate,
    parse_decimal,
    required_label,
)
from app.views.design_system import QuantityEditDelegate, apply_compact_row_height

_LINE_COLUMNS = ["Article", "Stock théorique", "Stock compté", "Écart"]
_STOCK_PHYSIQUE_COLUMN = 2


class InventoryFormDialog(QDialog):
    def __init__(
        self,
        articles: list[tuple[int, str, str]],
        initial: Optional[dict] = None,
        on_lookup_barcode: Optional[Callable[[str], Optional[tuple[int, str, str]]]] = None,
        parent: QWidget | None = None,
    ) -> None:
        """``articles`` : liste de tuples (id, libellé affiché, stock théorique actuel en texte).
        ``initial['lignes']`` : liste de dicts {article_id, article_label, stock_theorique, stock_physique}.
        ``on_lookup_barcode`` : callback de scan (voir ``EntryFormDialog``,
        même contrat) — ici, l'article trouvé est ajouté directement comme
        ligne (même point d'entrée que le double-clic d'un résultat de
        recherche), le stock compté démarrant à la valeur du stock
        théorique (écart nul) et restant ensuite librement modifiable
        directement dans le tableau."""
        super().__init__(parent)
        initial = initial or {}
        self._articles = articles
        self._on_lookup_barcode = on_lookup_barcode
        self._lines: list[dict] = list(initial.get("lignes", []))
        self._requested_action = "draft"

        self.setWindowTitle("Inventaire")
        self.setModal(True)
        # Mission 5.5, Évolution C : même largeur que Entrées/Sorties, pour
        # lire confortablement référence + désignation + stock théorique
        # dans la liste de résultats de ``article_search_panel`` ci-dessous,
        # sans jamais nécessiter de défilement horizontal.
        self.setMinimumWidth(640)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        # Confort d'interface uniquement (§ dates futures) : le calendrier
        # ne propose pas de date future, mais la garantie réelle est
        # appliquée côté service (InventoryService.create_inventory/update_inventory).
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setDate(date_to_qdate(initial.get("date") or date.today()))
        form.addRow(required_label("Date"), self.date_edit)

        layout.addLayout(form)

        layout.addWidget(build_required_field_legend(self))

        # Mission 5.5, Évolution C : le scan reste entièrement indépendant
        # de la recherche manuelle ci-dessous — les deux ne font qu'appeler
        # ``_on_article_activated``, sans jamais se bloquer l'un l'autre.
        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Scanner / code-barres", self))
        self.scan_edit = QLineEdit(self)
        self.scan_edit.setPlaceholderText("Scanner un article ou saisir son code-barres puis Entrée…")
        self.scan_edit.setEnabled(on_lookup_barcode is not None)
        scan_row.addWidget(self.scan_edit)
        layout.addLayout(scan_row)

        # Mission 5.5, Évolution C : recherche en direct plutôt qu'un
        # dialogue séparé par ligne (``InventoryLineFormDialog``, désormais
        # inutilisé) — double-clic sur un résultat pour ajouter directement
        # la ligne, exactement comme Entrées/Sorties (Mission 5.3).
        self.article_search_panel = ArticleSearchPanel(
            [
                (article_id, f"{label}  —  Stock théorique {stock_theorique}")
                for article_id, label, stock_theorique in articles
            ],
            self,
        )
        self.article_search_panel.article_activated.connect(self._on_article_activated)
        layout.addWidget(self.article_search_panel)

        # Mission 5.5, Évolution C : compteur dynamique, actualisé par
        # ``_refresh_lines_table`` — même ergonomie que Entrées/Sorties
        # (Mission 5.4, Évolution A.2).
        self.lines_label = QLabel("Lignes (0)", self)
        layout.addWidget(self.lines_label)

        self.lines_table = QTableWidget(0, len(_LINE_COLUMNS), self)
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.setHorizontalHeaderLabels(_LINE_COLUMNS)
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lines_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        # Mission 5.5, Évolution C : seul le Stock compté devient éditable
        # en place (même déclencheur/délégué que les tableaux de caisse et
        # d'Entrées/Sorties) — le Stock théorique et l'Écart restent en
        # lecture seule, jamais directement modifiables.
        self.lines_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed
        )
        lines_header = self.lines_table.horizontalHeader()
        lines_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, width in ((1, 130), (_STOCK_PHYSIQUE_COLUMN, 120)):
            lines_header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.lines_table.setColumnWidth(col, width)
        self._quantity_delegate = QuantityEditDelegate(self.lines_table)
        self.lines_table.setItemDelegateForColumn(_STOCK_PHYSIQUE_COLUMN, self._quantity_delegate)
        self.lines_table.itemChanged.connect(self._on_line_item_changed)
        layout.addWidget(self.lines_table)

        lines_button_row = QHBoxLayout()
        self.remove_line_button = QPushButton("Supprimer la ligne", self)
        self.remove_line_button.setProperty("variant", "danger")
        lines_button_row.addWidget(self.remove_line_button)
        lines_button_row.addStretch(1)
        layout.addLayout(lines_button_row)

        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet("color: #DC2626;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("Annuler", self)
        self.save_button = QPushButton("Enregistrer en brouillon", self)
        self.save_button.setProperty("variant", "primary")
        self.validate_button = QPushButton("Valider", self)
        self.validate_button.setProperty("variant", "success")
        self.validate_button.setDefault(True)
        self.validate_button.setStyleSheet("font-weight: 600;")
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.validate_button)
        layout.addLayout(button_row)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._on_save_clicked)
        self.validate_button.clicked.connect(self._on_validate_clicked)
        self.remove_line_button.clicked.connect(self._on_remove_line_clicked)
        self.scan_edit.returnPressed.connect(self._on_scan_entered)

        self._refresh_lines_table()

    # -- scan code-barres (lecteur USB « keyboard wedge ») ---------------------

    def _on_scan_entered(self) -> None:
        """Article actif trouvé -> ajoute directement une ligne, exactement
        comme un double-clic sur un résultat de ``article_search_panel``
        (voir ``_on_article_activated``) — plus de formulaire intermédiaire.
        Introuvable -> message clair, aucune ligne ajoutée. Le texte scanné
        est toujours effacé, qu'il ait été reconnu ou non, pour rester prêt
        pour le scan suivant."""
        code = self.scan_edit.text().strip()
        self.scan_edit.clear()
        if not code or self._on_lookup_barcode is None:
            return

        result = self._on_lookup_barcode(code)
        if result is None:
            QMessageBox.warning(
                self, "Article introuvable",
                f"Aucun article actif ne correspond au code-barres « {code} ».",
            )
            return

        article_id, _label, _stock_theorique = result
        self._on_article_activated(article_id)

    # -- gestion des lignes ---------------------------------------------------

    def _refresh_lines_table(self) -> None:
        # Mission 5.5, Évolution C : le Stock compté est désormais éditable
        # en place — ``blockSignals`` évite que la reconstruction ci-dessous
        # ne redéclenche ``_on_line_item_changed`` pour chaque cellule
        # repeuplée (même principe que ``EntryFormDialog._refresh_lines_table``).
        self.lines_table.blockSignals(True)
        self.lines_table.setRowCount(len(self._lines))
        for row, line in enumerate(self._lines):
            article_item = QTableWidgetItem(line["article_label"])
            article_item.setFlags(article_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.lines_table.setItem(row, 0, article_item)

            theorique_item = QTableWidgetItem(format_quantity(line["stock_theorique"]))
            theorique_item.setFlags(theorique_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.lines_table.setItem(row, 1, theorique_item)

            physique_item = QTableWidgetItem(format_quantity(line["stock_physique"]))
            physique_item.setFlags(physique_item.flags() | Qt.ItemFlag.ItemIsEditable)
            physique_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lines_table.setItem(row, _STOCK_PHYSIQUE_COLUMN, physique_item)

            try:
                ecart = Decimal(str(line["stock_physique"])) - Decimal(str(line["stock_theorique"]))
                ecart_text = format_quantity_signed(ecart)
            except Exception:
                ecart_text = "—"
            ecart_item = QTableWidgetItem(ecart_text)
            ecart_item.setFlags(ecart_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.lines_table.setItem(row, 3, ecart_item)
        self.lines_table.blockSignals(False)
        # Mission 5.5, Évolution C : 2 lignes de données visibles par défaut
        # (plus l'en-tête), défilement vertical au-delà — même utilitaire
        # que Entrées/Sorties (Évolution A), rappelé ici à chaque
        # changement du nombre de lignes.
        apply_compact_row_height(self.lines_table, visible_rows=2)
        self.lines_label.setText(f"Lignes ({len(self._lines)})")

    def _on_article_activated(self, article_id: int) -> None:
        """Mission 5.5, Évolution C : point d'entrée unique pour ajouter une
        ligne, appelé sur double-clic d'un résultat de
        ``article_search_panel`` ou sur un scan reconnu — stock compté
        initialisé au stock théorique actuel (écart nul au départ), ensuite
        librement modifiable directement dans le tableau. Le stock
        théorique affiché provient de la liste ``articles`` fournie à la
        construction (même source que l'ancien ``InventoryLineFormDialog``),
        jamais recalculé ici : seul le service fait foi à la validation."""
        article_label = "?"
        stock_theorique = Decimal("0")
        for aid, label, theorique in self._articles:
            if aid == article_id:
                article_label = label
                stock_theorique = Decimal(str(theorique))
                break
        self._lines.append(
            {
                "article_id": article_id,
                "article_label": article_label,
                "stock_theorique": stock_theorique,
                "stock_physique": stock_theorique,
            }
        )
        self._refresh_lines_table()
        self.article_search_panel.clear_search()

    def _on_line_item_changed(self, item: QTableWidgetItem) -> None:
        """Mission 5.5, Évolution C : point d'entrée unique pour toute
        modification du stock compté saisie directement dans le tableau —
        une valeur invalide est refusée avec un message clair et la cellule
        reprend sa valeur précédente, jamais de ligne laissée dans un état
        incohérent (même principe que
        ``EntryFormDialog._on_line_item_changed``). L'écart affiché est
        toujours recalculé à partir de cette nouvelle valeur, jamais
        directement saisissable."""
        if item.column() != _STOCK_PHYSIQUE_COLUMN:
            return
        row = item.row()
        if row >= len(self._lines):
            return
        try:
            nouvelle_valeur = parse_decimal(item.text(), "stock compté")
            if nouvelle_valeur < 0:
                raise ValidationError("Le stock compté ne peut pas être négatif.")
        except ValidationError as exc:
            self.set_error(str(exc))
            self._refresh_lines_table()
            return
        self.set_error("")
        self._lines[row]["stock_physique"] = nouvelle_valeur
        self._refresh_lines_table()

    def _on_remove_line_clicked(self) -> None:
        selected = self.lines_table.selectionModel().selectedRows()
        if not selected:
            return
        row = selected[0].row()
        del self._lines[row]
        self._refresh_lines_table()

    def values(self) -> dict:
        return {
            "date": self.date_edit.date().toPython(),
            "lignes": list(self._lines),
        }

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)

    # -- distinction brouillon / validation directe ---------------------------

    def _on_save_clicked(self) -> None:
        self._requested_action = "draft"
        self.accept()

    def _on_validate_clicked(self) -> None:
        self._requested_action = "validate"
        self.save_button.setEnabled(False)
        self.validate_button.setEnabled(False)
        self.accept()

    def requested_action(self) -> str:
        """'draft' ou 'validate' selon le bouton actionné — ``accept()`` étant
        commun aux deux, c'est le seul moyen pour l'appelant de distinguer les
        deux intentions une fois le dialogue fermé."""
        return self._requested_action
