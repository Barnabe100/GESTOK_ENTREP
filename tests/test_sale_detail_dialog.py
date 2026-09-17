from datetime import datetime, timezone
from decimal import Decimal

from app.models.enums import StatutOperation, TypeMouvement
from app.services.sales.sale_service import VenteLigneSummary, VenteSummary
from app.services.stock.movement_summary import MouvementSummary
from app.views.sale_detail_dialog import SaleDetailDialog


def _make_sale(**overrides) -> VenteSummary:
    now = datetime.now(timezone.utc)
    ligne = VenteLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        quantite=Decimal("10"), prix_unitaire=Decimal("800"), sous_total=Decimal("8000"),
    )
    defaults = dict(
        id=1, numero="VNT-000001", date=now.date(), user_id=1, username="admin",
        statut=StatutOperation.BROUILLON, total=Decimal("8000"), lignes=[ligne],
        date_creation=now, date_modification=now,
    )
    defaults.update(overrides)
    return VenteSummary(**defaults)


def _make_movement(**overrides) -> MouvementSummary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, article_id=10, article_reference="ART-1", type=TypeMouvement.VENTE,
        quantite=Decimal("-10"), stock_avant=Decimal("50"), stock_apres=Decimal("40"),
        cout_unitaire=Decimal("500"), date_heure=now, user_id=1, username="admin", commentaire=None,
    )
    defaults.update(overrides)
    return MouvementSummary(**defaults)


def test_detail_dialog_shows_numero_in_title(qtbot) -> None:
    dialog = SaleDetailDialog(_make_sale(), [], "XOF")
    qtbot.addWidget(dialog)

    assert "VNT-000001" in dialog.windowTitle()


def test_detail_dialog_does_not_crash_with_no_movements(qtbot) -> None:
    dialog = SaleDetailDialog(_make_sale(), [], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_shows_movements(qtbot) -> None:
    dialog = SaleDetailDialog(_make_sale(), [_make_movement()], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_close_button_accepts(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    dialog = SaleDetailDialog(_make_sale(), [], "XOF")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_detail_dialog_handles_no_lines(qtbot) -> None:
    dialog = SaleDetailDialog(_make_sale(lignes=[], total=Decimal("0")), [], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None
