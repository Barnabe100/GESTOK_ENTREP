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
