from datetime import datetime, timezone
from decimal import Decimal

from app.models.enums import StatutInventaire, TypeMouvement
from app.services.inventory.inventory_service import InventaireLigneSummary, InventaireSummary
from app.services.stock.movement_summary import MouvementSummary
from app.views.inventory_detail_dialog import InventoryDetailDialog


def _make_inventory(**overrides) -> InventaireSummary:
    now = datetime.now(timezone.utc)
    ligne = InventaireLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        stock_theorique=Decimal("100"), stock_physique=Decimal("97"), ecart=Decimal("-3"),
    )
    defaults = dict(
        id=1, numero="INV-000001", date=now.date(), user_id=1, username="admin",
        statut=StatutInventaire.BROUILLON, lignes=[ligne], date_creation=now, date_modification=now,
    )
    defaults.update(overrides)
    return InventaireSummary(**defaults)


def _make_movement(**overrides) -> MouvementSummary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, article_id=10, article_reference="ART-1", type=TypeMouvement.AJUSTEMENT,
        quantite=Decimal("-3"), stock_avant=Decimal("100"), stock_apres=Decimal("97"),
        cout_unitaire=Decimal("500"), date_heure=now, user_id=1, username="admin", commentaire=None,
    )
    defaults.update(overrides)
    return MouvementSummary(**defaults)


def test_detail_dialog_shows_numero_in_title(qtbot) -> None:
    dialog = InventoryDetailDialog(_make_inventory(), [])
    qtbot.addWidget(dialog)

    assert "INV-000001" in dialog.windowTitle()


def test_detail_dialog_does_not_crash_with_no_movements(qtbot) -> None:
    dialog = InventoryDetailDialog(_make_inventory(), [])
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_formats_ecart_global_with_sign_and_no_extra_decimals(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    dialog = InventoryDetailDialog(_make_inventory(), [])
    qtbot.addWidget(dialog)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "-3" in texts  # ecart_total = -3 (voir _make_inventory), jamais "-3.000"


def test_detail_dialog_line_columns_preserve_decimal_ecart(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    ligne = InventaireLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        stock_theorique=Decimal("10.000"), stock_physique=Decimal("11.500"), ecart=Decimal("1.500"),
    )
    dialog = InventoryDetailDialog(_make_inventory(lignes=[ligne]), [])
    qtbot.addWidget(dialog)

    lines_table = dialog.findChildren(QTableWidget)[0]
    assert lines_table.item(0, 1).text() == "10"  # stock théorique, sans décimale superflue
    assert lines_table.item(0, 2).text() == "11,5"  # stock compté, décimale réelle conservée
    assert lines_table.item(0, 3).text() == "+1,5"  # écart signé


def test_detail_dialog_shows_movements(qtbot) -> None:
    dialog = InventoryDetailDialog(_make_inventory(), [_make_movement()])
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_close_button_accepts(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    dialog = InventoryDetailDialog(_make_inventory(), [])
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_detail_dialog_handles_no_lines(qtbot) -> None:
    dialog = InventoryDetailDialog(_make_inventory(lignes=[]), [])
    qtbot.addWidget(dialog)
    assert dialog is not None
