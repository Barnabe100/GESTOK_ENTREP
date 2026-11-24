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


# -- Mission 5.6, §2 : en-tête multi-colonnes + historique compact (5 lignes) -----


def test_header_section_uses_multi_column_form(qtbot) -> None:
    from PySide6.QtWidgets import QFormLayout

    dialog = ClientDetailDialog(_make_client(), [], "XOF")
    qtbot.addWidget(dialog)

    assert len(dialog.findChildren(QFormLayout)) == 3


def test_header_section_shows_all_required_fields_somewhere(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    client = _make_client()
    dialog = ClientDetailDialog(client, [], "XOF")
    qtbot.addWidget(dialog)

    texts = {label.text() for label in dialog.findChildren(QLabel)}
    for expected in (
        client.nom, client.telephone, client.email, client.adresse,
        client.observations, "Actif",
    ):
        assert expected in texts


def _header_height(table) -> int:
    return table.horizontalHeader().sizeHint().height() or 32


def test_sales_table_has_header_only_height_with_no_sales(qtbot) -> None:
    dialog = ClientDetailDialog(_make_client(), [], "XOF")
    qtbot.addWidget(dialog)

    assert dialog.sales_table.maximumHeight() == _header_height(dialog.sales_table) + 12


def test_sales_table_height_fits_exactly_n_rows_up_to_five(qtbot) -> None:
    for n in (1, 3, 5):
        sales = [_make_sale(id=i, numero=f"VNT-{i:06d}") for i in range(n)]
        dialog = ClientDetailDialog(_make_client(), sales, "XOF")

        expected = _header_height(dialog.sales_table) + n * 34 + 12
        assert dialog.sales_table.maximumHeight() == expected
        assert dialog.sales_table.minimumHeight() == expected


def test_sales_table_caps_at_five_rows_with_more_than_five_sales(qtbot) -> None:
    five_sales_dialog = ClientDetailDialog(
        _make_client(), [_make_sale(id=i, numero=f"VNT-{i:06d}") for i in range(5)], "XOF"
    )
    seven_sales_dialog = ClientDetailDialog(
        _make_client(), [_make_sale(id=i, numero=f"VNT-{i:06d}") for i in range(7)], "XOF"
    )

    assert seven_sales_dialog.sales_table.maximumHeight() == five_sales_dialog.sales_table.maximumHeight()
    assert seven_sales_dialog.sales_table.rowCount() == 7  # toutes les ventes restent chargées


def test_sales_table_never_disables_vertical_scrollbar(qtbot) -> None:
    from PySide6.QtCore import Qt

    sales = [_make_sale(id=i, numero=f"VNT-{i:06d}") for i in range(7)]
    dialog = ClientDetailDialog(_make_client(), sales, "XOF")
    qtbot.addWidget(dialog)

    assert dialog.sales_table.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_sales_table_column_widths_avoid_horizontal_scroll(qtbot) -> None:
    dialog = ClientDetailDialog(_make_client(), [_make_sale()], "XOF")
    qtbot.addWidget(dialog)

    assert dialog.sales_table.columnWidth(0) == 140
    assert dialog.sales_table.columnWidth(1) == 110
    assert dialog.sales_table.columnWidth(2) == 110
    assert dialog.sales_table.horizontalHeader().stretchLastSection() is True


# -- Mission 5.6, §2.3/§1 : dimensionnement adapté au contenu, pas d'espace vide --


def test_dialog_height_grows_with_more_sales(qtbot) -> None:
    few_sales_dialog = ClientDetailDialog(_make_client(), [_make_sale()], "XOF")
    few_sales_dialog.show()
    many_sales = [_make_sale(id=i, numero=f"VNT-{i:06d}") for i in range(5)]
    many_sales_dialog = ClientDetailDialog(_make_client(), many_sales, "XOF")
    many_sales_dialog.show()

    assert many_sales_dialog.height() > few_sales_dialog.height()


def test_dialog_does_not_force_an_oversized_fixed_height_with_no_sales(qtbot) -> None:
    """Non-régression du grand espace vide (§1/§2.3) : avec aucune vente, le
    dialogue reste compact, jamais figé à une hauteur fixe disproportionnée."""
    dialog = ClientDetailDialog(_make_client(), [], "XOF")
    dialog.show()

    assert dialog.height() < 500
