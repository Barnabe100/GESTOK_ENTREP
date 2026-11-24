from datetime import datetime, timezone
from decimal import Decimal

from app.models.enums import StatutOperation, TypeMouvement
from app.services.entries.entry_service import EntreeLigneSummary, EntreeSummary, MouvementSummary
from app.views.entry_detail_dialog import EntryDetailDialog


def _make_entry(**overrides) -> EntreeSummary:
    now = datetime.now(timezone.utc)
    ligne = EntreeLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        quantite=Decimal("10"), prix_unitaire=Decimal("500"), montant=Decimal("5000"),
    )
    defaults = dict(
        id=1, numero="ENT-000001", date=now.date(), fournisseur_id=1, fournisseur_nom="Fournisseur A",
        reference_document="BL-42", user_id=1, username="admin", commentaire="Commentaire",
        statut=StatutOperation.BROUILLON, lignes=[ligne], date_creation=now, date_modification=now,
    )
    defaults.update(overrides)
    return EntreeSummary(**defaults)


def _make_movement(**overrides) -> MouvementSummary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, article_id=10, article_reference="ART-1", type=TypeMouvement.ENTREE,
        quantite=Decimal("10"), stock_avant=Decimal("0"), stock_apres=Decimal("10"),
        cout_unitaire=Decimal("500"), date_heure=now, user_id=1, username="admin", commentaire=None,
    )
    defaults.update(overrides)
    return MouvementSummary(**defaults)


def test_detail_dialog_shows_numero_in_title(qtbot) -> None:
    dialog = EntryDetailDialog(_make_entry(), [], "XOF")
    qtbot.addWidget(dialog)

    assert "ENT-000001" in dialog.windowTitle()


def test_detail_dialog_formats_line_and_movement_quantities(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    ligne = EntreeLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        quantite=Decimal("10.500"), prix_unitaire=Decimal("500"), montant=Decimal("5250"),
    )
    movement = _make_movement(quantite=Decimal("10.500"), stock_avant=Decimal("0.000"), stock_apres=Decimal("10.500"))
    dialog = EntryDetailDialog(_make_entry(lignes=[ligne]), [movement], "XOF")
    qtbot.addWidget(dialog)

    tables = dialog.findChildren(QTableWidget)
    lines_table, movements_table = tables[0], tables[1]
    assert lines_table.item(0, 1).text() == "10,5"
    assert movements_table.item(0, 2).text() == "10,5"
    assert movements_table.item(0, 3).text() == "0"  # jamais "0.000"
    assert movements_table.item(0, 4).text() == "10,5"


def test_detail_dialog_does_not_crash_with_no_movements(qtbot) -> None:
    dialog = EntryDetailDialog(_make_entry(), [], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_shows_movements(qtbot) -> None:
    dialog = EntryDetailDialog(_make_entry(), [_make_movement()], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_close_button_accepts(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    dialog = EntryDetailDialog(_make_entry(), [], "XOF")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_detail_dialog_handles_missing_optional_fields(qtbot) -> None:
    dialog = EntryDetailDialog(
        _make_entry(reference_document=None, commentaire=None, lignes=[]), [], "XOF"
    )
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_shows_motif_when_annulee(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    dialog = EntryDetailDialog(
        _make_entry(statut=StatutOperation.ANNULEE, annulation_motif="Erreur de saisie de quantité"),
        [], "XOF",
    )
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Erreur de saisie de quantité" in labels


def test_detail_dialog_hides_motif_row_when_not_annulee(qtbot) -> None:
    from PySide6.QtWidgets import QFormLayout

    dialog = EntryDetailDialog(_make_entry(statut=StatutOperation.VALIDEE), [], "XOF")
    qtbot.addWidget(dialog)

    form = dialog.findChild(QFormLayout)
    row_labels = [
        form.itemAt(i, QFormLayout.ItemRole.LabelRole).widget().text() for i in range(form.rowCount())
    ]
    assert "Motif d'annulation" not in row_labels


# -- Mission 5.5, Évolution B : en-tête multi-colonnes + tableaux compacts --------


def test_header_section_uses_multi_column_form(qtbot) -> None:
    """Remplace la colonne unique (``QFormLayout``) par 3 colonnes côte à
    côte (:class:`MultiColumnForm`, partagé avec ``sale_detail_dialog.py``)
    — exploite la largeur désormais disponible plutôt que d'allonger la
    fenêtre."""
    from PySide6.QtWidgets import QFormLayout

    dialog = EntryDetailDialog(_make_entry(), [], "XOF")
    qtbot.addWidget(dialog)

    assert len(dialog.findChildren(QFormLayout)) == 3


def test_header_section_shows_all_required_fields_somewhere(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    entry = _make_entry()
    dialog = EntryDetailDialog(entry, [], "XOF")
    qtbot.addWidget(dialog)

    texts = {label.text() for label in dialog.findChildren(QLabel)}
    for expected in (entry.numero, entry.fournisseur_nom, str(entry.date), "BL-42", "admin", "Commentaire"):
        assert expected in texts


def test_lines_and_movements_tables_cap_at_two_visible_rows(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    lignes = [
        EntreeLigneSummary(
            id=i, article_id=10 + i, article_reference=f"ART-{i}", article_designation="X",
            quantite=Decimal("1"), prix_unitaire=Decimal("500"), montant=Decimal("500"),
        )
        for i in range(4)
    ]
    movements = [_make_movement(id=i) for i in range(4)]
    dialog = EntryDetailDialog(_make_entry(lignes=lignes), movements, "XOF")
    qtbot.addWidget(dialog)

    tables = dialog.findChildren(QTableWidget)
    lines_table, movements_table = tables[0], tables[1]
    assert lines_table.rowCount() == 4
    assert movements_table.rowCount() == 4

    header_height = lines_table.horizontalHeader().sizeHint().height() or 32
    expected = header_height + 2 * 34 + 12
    assert lines_table.maximumHeight() == expected
    assert movements_table.maximumHeight() == expected


def test_tables_never_disable_vertical_scrollbar(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTableWidget

    dialog = EntryDetailDialog(_make_entry(), [_make_movement()], "XOF")
    qtbot.addWidget(dialog)

    for table in dialog.findChildren(QTableWidget):
        assert table.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
