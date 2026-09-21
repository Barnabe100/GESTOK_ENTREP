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
