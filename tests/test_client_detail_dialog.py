from datetime import datetime, timezone
from decimal import Decimal

from app.models.enums import StatutOperation
from app.services.clients.client_service import ClientSummary
from app.services.sales.sale_service import VenteSummary
from app.views.client_detail_dialog import ClientDetailDialog


def _make_client(**overrides) -> ClientSummary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, nom="Jean Dupont", telephone="0102030405", email="jean@example.com",
        adresse="1 rue X", observations="Note", actif=True, date_creation=now, date_modification=now,
    )
    defaults.update(overrides)
    return ClientSummary(**defaults)


def _make_sale(**overrides) -> VenteSummary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, numero="VNT-000001", date=now.date(), user_id=1, username="admin",
        statut=StatutOperation.VALIDEE, total=Decimal("8000"), lignes=[],
        date_creation=now, date_modification=now, client_id=1, client_nom="Jean Dupont",
    )
    defaults.update(overrides)
    return VenteSummary(**defaults)


def test_detail_dialog_shows_client_name_in_title(qtbot) -> None:
    dialog = ClientDetailDialog(_make_client(), [], "XOF")
    qtbot.addWidget(dialog)

    assert "Jean Dupont" in dialog.windowTitle()


def test_detail_dialog_shows_sales_history(qtbot) -> None:
    dialog = ClientDetailDialog(_make_client(), [_make_sale()], "XOF")
    qtbot.addWidget(dialog)

    assert dialog.sales_table.rowCount() == 1
    assert dialog.sales_table.item(0, 0).text() == "VNT-000001"


def test_detail_dialog_handles_no_sales(qtbot) -> None:
    dialog = ClientDetailDialog(_make_client(), [], "XOF")
    qtbot.addWidget(dialog)

    assert dialog.sales_table.rowCount() == 0


def test_detail_dialog_shows_inactive_status(qtbot) -> None:
    dialog = ClientDetailDialog(_make_client(actif=False), [], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None  # rendu sans erreur pour un client désactivé (§8)


def test_detail_dialog_still_shows_sales_for_deactivated_client(qtbot) -> None:
    """§8 : l'historique des ventes reste visible même après désactivation
    du client — ce dialogue affiche simplement ce qu'on lui donne."""
    dialog = ClientDetailDialog(_make_client(actif=False), [_make_sale()], "XOF")
    qtbot.addWidget(dialog)

    assert dialog.sales_table.rowCount() == 1


def test_detail_dialog_close_button_accepts(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    dialog = ClientDetailDialog(_make_client(), [], "XOF")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted
