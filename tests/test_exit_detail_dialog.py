from datetime import datetime, timezone
from decimal import Decimal

from app.models.enums import StatutOperation, TypeMouvement
from app.services.exits.exit_service import SortieLigneSummary, SortieSummary
from app.services.stock.movement_summary import MouvementSummary
from app.views.exit_detail_dialog import ExitDetailDialog


def _make_exit(**overrides) -> SortieSummary:
    now = datetime.now(timezone.utc)
    ligne = SortieLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        quantite=Decimal("10"), cout_unitaire=Decimal("500"), montant=Decimal("5000"),
    )
    defaults = dict(
        id=1, numero="SOR-000001", date=now.date(), motif_id=1, motif_libelle="Perte",
        beneficiaire="Service RH", reference="REF-1", user_id=1, username="admin", commentaire="Commentaire",
        statut=StatutOperation.BROUILLON, lignes=[ligne], date_creation=now, date_modification=now,
    )
    defaults.update(overrides)
    return SortieSummary(**defaults)


def _make_movement(**overrides) -> MouvementSummary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, article_id=10, article_reference="ART-1", type=TypeMouvement.SORTIE,
        quantite=Decimal("-10"), stock_avant=Decimal("50"), stock_apres=Decimal("40"),
        cout_unitaire=Decimal("500"), date_heure=now, user_id=1, username="admin", commentaire=None,
    )
    defaults.update(overrides)
    return MouvementSummary(**defaults)


def test_detail_dialog_shows_numero_in_title(qtbot) -> None:
    dialog = ExitDetailDialog(_make_exit(), [], "XOF")
    qtbot.addWidget(dialog)

    assert "SOR-000001" in dialog.windowTitle()


def test_detail_dialog_formats_line_and_movement_quantities(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    ligne = SortieLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        quantite=Decimal("2.500"), cout_unitaire=Decimal("500"), montant=Decimal("1250"),
    )
    movement = _make_movement(
        quantite=Decimal("-2.500"), stock_avant=Decimal("50.000"), stock_apres=Decimal("47.500"),
    )
    dialog = ExitDetailDialog(_make_exit(lignes=[ligne]), [movement], "XOF")
    qtbot.addWidget(dialog)

    tables = dialog.findChildren(QTableWidget)
    lines_table, movements_table = tables[0], tables[1]
    assert lines_table.item(0, 1).text() == "2,5"
    assert movements_table.item(0, 2).text() == "-2,5"
    assert movements_table.item(0, 3).text() == "50"  # jamais "50.000"
    assert movements_table.item(0, 4).text() == "47,5"


def test_detail_dialog_does_not_crash_with_no_movements(qtbot) -> None:
    dialog = ExitDetailDialog(_make_exit(), [], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_shows_movements(qtbot) -> None:
    dialog = ExitDetailDialog(_make_exit(), [_make_movement()], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_close_button_accepts(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    dialog = ExitDetailDialog(_make_exit(), [], "XOF")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_detail_dialog_handles_missing_optional_fields(qtbot) -> None:
    dialog = ExitDetailDialog(
        _make_exit(beneficiaire=None, reference=None, commentaire=None, lignes=[]), [], "XOF"
    )
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_shows_motif_when_annulee(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ExitDetailDialog(
        _make_exit(statut=StatutOperation.ANNULEE, annulation_motif="Erreur de sélection"), [], "XOF"
    )
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Erreur de sélection" in labels


def test_detail_dialog_hides_motif_row_when_not_annulee(qtbot) -> None:
    from PySide6.QtWidgets import QFormLayout

    dialog = ExitDetailDialog(_make_exit(statut=StatutOperation.VALIDEE), [], "XOF")
    qtbot.addWidget(dialog)

    form = dialog.findChild(QFormLayout)
    row_labels = [
        form.itemAt(i, QFormLayout.ItemRole.LabelRole).widget().text() for i in range(form.rowCount())
    ]
    assert "Motif d'annulation" not in row_labels


# -- Mission 5.5, Évolution B : en-tête multi-colonnes + tableaux compacts --------


def test_header_section_uses_multi_column_form(qtbot) -> None:
    from PySide6.QtWidgets import QFormLayout

    dialog = ExitDetailDialog(_make_exit(), [], "XOF")
    qtbot.addWidget(dialog)

    assert len(dialog.findChildren(QFormLayout)) == 3


def test_header_section_shows_all_required_fields_somewhere(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    exit_ = _make_exit()
    dialog = ExitDetailDialog(exit_, [], "XOF")
    qtbot.addWidget(dialog)

    texts = {label.text() for label in dialog.findChildren(QLabel)}
    for expected in (exit_.numero, exit_.motif_libelle, "Service RH", "REF-1", "admin", "Commentaire"):
        assert expected in texts


def test_lines_and_movements_tables_cap_at_two_visible_rows(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    lignes = [
        SortieLigneSummary(
            id=i, article_id=10 + i, article_reference=f"ART-{i}", article_designation="X",
            quantite=Decimal("1"), cout_unitaire=Decimal("500"), montant=Decimal("500"),
        )
        for i in range(4)
    ]
    movements = [_make_movement(id=i) for i in range(4)]
    dialog = ExitDetailDialog(_make_exit(lignes=lignes), movements, "XOF")
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

    dialog = ExitDetailDialog(_make_exit(), [_make_movement()], "XOF")
    qtbot.addWidget(dialog)

    for table in dialog.findChildren(QTableWidget):
        assert table.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff


# -- Mission 5.6, §1 : suppression de l'espace vide, hauteur adaptée au contenu --


def test_content_layout_ends_with_the_last_table_group_not_a_spacer(qtbot) -> None:
    from PySide6.QtWidgets import QScrollArea

    dialog = ExitDetailDialog(_make_exit(), [_make_movement()], "XOF")
    qtbot.addWidget(dialog)

    content = dialog.findChildren(QScrollArea)[0].widget()
    last_item = content.layout().itemAt(content.layout().count() - 1)
    assert last_item.widget() is not None  # dernier élément : un widget (groupe), jamais un spacer


def test_dialog_height_is_content_driven_not_a_large_fixed_value(qtbot) -> None:
    dialog = ExitDetailDialog(
        _make_exit(beneficiaire=None, reference=None, commentaire=None, lignes=[]), [], "XOF"
    )
    dialog.show()

    assert dialog.height() < 500  # bien en-dessous de l'ancienne hauteur fixe (700)


def test_close_button_remains_accessible(qtbot) -> None:
    dialog = ExitDetailDialog(_make_exit(), [_make_movement()], "XOF")
    dialog.show()

    assert dialog.close_button.isVisible()
    assert dialog.close_button.isEnabled()


def test_scroll_area_still_scrolls_when_window_shrunk_below_content(qtbot) -> None:
    from PySide6.QtWidgets import QScrollArea

    dialog = ExitDetailDialog(_make_exit(), [_make_movement()], "XOF")
    dialog.show()
    scroll_area = dialog.findChildren(QScrollArea)[0]

    dialog.resize(dialog.width(), 200)

    assert scroll_area.verticalScrollBar().maximum() > 0


def test_dialog_fits_within_1366x768_and_1920x1080(qtbot) -> None:
    dialog = ExitDetailDialog(_make_exit(), [_make_movement()], "XOF")
    dialog.show()

    assert dialog.width() <= 1366
    assert dialog.height() <= 768
    assert dialog.width() <= 1920
    assert dialog.height() <= 1080
