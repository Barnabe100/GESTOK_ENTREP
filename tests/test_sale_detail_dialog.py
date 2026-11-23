from datetime import datetime, timezone
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QTableWidget

from app.models.enums import StatutOperation, TypeMouvement
from app.services.sales.sale_service import VenteLigneSummary, VenteSummary
from app.services.stock.movement_summary import MouvementSummary
from app.views.sale_detail_dialog import SaleDetailDialog


class _StubPermissions:
    """Remplace PermissionService dans les tests qui ne portent que sur le
    rendu du dialogue (pas sur le contenu réel d'un reçu) : évite de monter
    une base de test complète juste pour vérifier que la boîte s'affiche."""

    def has_permission(self, code: str) -> bool:
        return True


class _StubReceiptService:
    """Jamais appelé par les tests qui ne cliquent pas sur les boutons de
    reçu — présent uniquement pour satisfaire la signature du dialogue."""

    def build_sale_receipt(self, sale_id: int):
        raise NotImplementedError


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


def _build_dialog(sale, movements=(), currency="XOF"):
    return SaleDetailDialog(sale, list(movements), currency, _StubReceiptService(), _StubPermissions())


def test_detail_dialog_shows_numero_in_title(qtbot) -> None:
    dialog = _build_dialog(_make_sale())
    qtbot.addWidget(dialog)

    assert "VNT-000001" in dialog.windowTitle()


def test_detail_dialog_formats_line_and_movement_quantities(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    ligne = VenteLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        quantite=Decimal("1.500"), prix_unitaire=Decimal("800"), sous_total=Decimal("1200"),
    )
    movement = _make_movement(
        quantite=Decimal("-1.500"), stock_avant=Decimal("50.000"), stock_apres=Decimal("48.500"),
    )
    dialog = _build_dialog(_make_sale(lignes=[ligne]), [movement])
    qtbot.addWidget(dialog)

    tables = dialog.findChildren(QTableWidget)
    lines_table, movements_table = tables[0], tables[-1]  # entre les deux : l'historique des paiements
    assert lines_table.item(0, 1).text() == "1,5"
    assert movements_table.item(0, 2).text() == "-1,5"
    assert movements_table.item(0, 3).text() == "50"  # jamais "50.000"
    assert movements_table.item(0, 4).text() == "48,5"


def test_detail_dialog_does_not_crash_with_no_movements(qtbot) -> None:
    dialog = _build_dialog(_make_sale())
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_shows_movements(qtbot) -> None:
    dialog = _build_dialog(_make_sale(), [_make_movement()])
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_close_button_accepts(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    dialog = _build_dialog(_make_sale())
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_detail_dialog_handles_no_lines(qtbot) -> None:
    dialog = _build_dialog(_make_sale(lignes=[], total=Decimal("0")))
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_receipt_buttons_disabled_for_brouillon(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.BROUILLON))
    qtbot.addWidget(dialog)

    assert dialog.export_pdf_button.isEnabled() is False
    assert dialog.print_receipt_button.isEnabled() is False


def test_receipt_buttons_disabled_for_annulee(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.ANNULEE))
    qtbot.addWidget(dialog)

    assert dialog.export_pdf_button.isEnabled() is False


def test_receipt_buttons_enabled_for_validee(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE))
    qtbot.addWidget(dialog)

    assert dialog.export_pdf_button.isEnabled() is True
    assert dialog.print_receipt_button.isEnabled() is True


def test_receipt_buttons_disabled_without_sale_view_permission(qtbot) -> None:
    class _NoAccess:
        def has_permission(self, code: str) -> bool:
            return False

    dialog = SaleDetailDialog(
        _make_sale(statut=StatutOperation.VALIDEE), [], "XOF", _StubReceiptService(), _NoAccess()
    )
    qtbot.addWidget(dialog)

    assert dialog.export_pdf_button.isEnabled() is False


def test_payment_receipt_button_no_longer_exists(qtbot) -> None:
    """Lot 22 (§7.1) : le bouton « Reçu du paiement sélectionné (PDF) » est
    entièrement supprimé de l'interface — le reçu de vente unifié (Lot 21)
    contient déjà l'historique complet des paiements."""
    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE))
    qtbot.addWidget(dialog)

    assert not hasattr(dialog, "export_payment_receipt_button")


def test_single_export_pdf_button_replaces_the_two_format_specific_buttons(qtbot) -> None:
    """Lot 22 (§7.3) : un seul bouton d'export, les deux boutons distincts
    A4/Ticket n'existent plus."""
    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE))
    qtbot.addWidget(dialog)

    assert not hasattr(dialog, "export_a4_button")
    assert not hasattr(dialog, "export_ticket_button")
    assert dialog.export_pdf_button.text() == "Exporter en PDF"


def test_detail_dialog_shows_motif_when_annulee(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    dialog = _build_dialog(
        _make_sale(statut=StatutOperation.ANNULEE, annulation_motif="Client a annulé sa commande")
    )
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Client a annulé sa commande" in labels


def test_detail_dialog_hides_motif_row_when_not_annulee(qtbot) -> None:
    from PySide6.QtWidgets import QFormLayout

    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE))
    qtbot.addWidget(dialog)

    # Mission 5.1, Correction C : « Informations générales » est désormais
    # répartie sur 3 colonnes (3 ``QFormLayout`` distincts, voir
    # ``MultiColumnForm``) plutôt qu'un seul — on parcourt donc tous les
    # ``QFormLayout`` du dialogue, pas seulement le premier trouvé.
    row_labels = [
        label_item.widget().text()
        for form in dialog.findChildren(QFormLayout)
        for i in range(form.rowCount())
        if (label_item := form.itemAt(i, QFormLayout.ItemRole.LabelRole)) is not None
    ]
    assert "Motif d'annulation" not in row_labels


# -- Lot 15, étape 1 : regroupement visuel, mouvements conditionnels, défilement --

def test_detail_dialog_sections_are_grouped(qtbot) -> None:
    from PySide6.QtWidgets import QGroupBox

    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE), [_make_movement()])
    qtbot.addWidget(dialog)

    titles = {group.title() for group in dialog.findChildren(QGroupBox)}
    assert {
        "Informations générales", "Articles et montants", "Paiement",
        "Mouvements de stock générés", "Reçu",
    } <= titles


def test_detail_dialog_uses_scroll_area(qtbot) -> None:
    from PySide6.QtWidgets import QScrollArea

    dialog = _build_dialog(_make_sale())
    qtbot.addWidget(dialog)

    scroll_areas = dialog.findChildren(QScrollArea)
    assert len(scroll_areas) == 1
    assert scroll_areas[0].widgetResizable() is True
    assert scroll_areas[0].widget() is not None


def test_movements_section_hidden_when_no_movements(qtbot) -> None:
    from PySide6.QtWidgets import QGroupBox

    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE), [])
    qtbot.addWidget(dialog)

    assert dialog.movements_table is None
    titles = {group.title() for group in dialog.findChildren(QGroupBox)}
    assert "Mouvements de stock générés" not in titles


def test_movements_section_hidden_for_brouillon_without_movements(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.BROUILLON), [])
    qtbot.addWidget(dialog)

    assert dialog.movements_table is None


def test_movements_section_shown_when_movements_present(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE), [_make_movement()])
    qtbot.addWidget(dialog)

    assert dialog.movements_table is not None
    assert dialog.movements_table.rowCount() == 1


def test_movements_section_shown_for_annulee_with_movements(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.ANNULEE), [_make_movement()])
    qtbot.addWidget(dialog)

    assert dialog.movements_table is not None
    assert dialog.movements_table.rowCount() == 1


def test_detail_dialog_remains_usable_with_large_content(qtbot) -> None:
    from PySide6.QtWidgets import QScrollArea, QTableWidget

    lignes = [
        VenteLigneSummary(
            id=i, article_id=i, article_reference=f"ART-{i}", article_designation=f"Article {i}",
            quantite=Decimal("1"), prix_unitaire=Decimal("100"), sous_total=Decimal("100"),
        )
        for i in range(1, 51)
    ]
    movements = [_make_movement(id=i) for i in range(1, 51)]
    dialog = _build_dialog(
        _make_sale(statut=StatutOperation.VALIDEE, lignes=lignes, total=Decimal("5000")), movements
    )
    qtbot.addWidget(dialog)

    lines_table = dialog.findChildren(QTableWidget)[0]
    assert lines_table.rowCount() == 50
    assert dialog.movements_table.rowCount() == 50

    scroll_area = dialog.findChild(QScrollArea)
    assert scroll_area is not None
    assert scroll_area.widget() is not None


def test_statut_paiement_label_reflects_payee_status(qtbot) -> None:
    from app.models.enums import StatutPaiement

    dialog = _build_dialog(
        _make_sale(
            statut=StatutOperation.VALIDEE, total=Decimal("8000"),
            montant_paye=Decimal("8000"), statut_paiement=StatutPaiement.PAYEE,
        )
    )
    qtbot.addWidget(dialog)

    assert dialog.statut_paiement_label.text() == "Payée"
    assert "color" in dialog.statut_paiement_label.styleSheet()


def test_statut_paiement_label_reflects_non_payee_status(qtbot) -> None:
    from app.models.enums import StatutPaiement

    dialog = _build_dialog(
        _make_sale(statut=StatutOperation.VALIDEE, total=Decimal("8000"), statut_paiement=StatutPaiement.NON_PAYEE)
    )
    qtbot.addWidget(dialog)

    assert dialog.statut_paiement_label.text() == "Non payée"
    assert "color" in dialog.statut_paiement_label.styleSheet()


# -- Mission 5.4, Évolution C : hauteur compacte des 3 tableaux ---------------------
#
# Même traitement que ``location_detail_dialog.py`` (Évolution B) : 2 lignes
# de données visibles par défaut (plus l'en-tête), toutes les données
# restant chargées (``rowCount`` jamais tronqué), le défilement vertical du
# tableau donnant accès au reste.

from app.services.sales.sale_service import PaiementSummary


def _make_lignes(n: int) -> list[VenteLigneSummary]:
    return [
        VenteLigneSummary(
            id=i, article_id=i, article_reference=f"ART-{i}", article_designation=f"Article {i}",
            quantite=Decimal("1"), prix_unitaire=Decimal("100"), sous_total=Decimal("100"),
        )
        for i in range(1, n + 1)
    ]


def _make_movements(n: int) -> list[MouvementSummary]:
    return [_make_movement(id=i) for i in range(1, n + 1)]


class _FakeSaleServiceWithPayments:
    """Fournit uniquement ce que ``_refresh_payment_section`` utilise —
    aucune base de test complète nécessaire pour ce seul besoin."""

    def __init__(self, sale: VenteSummary, payments: list[PaiementSummary]) -> None:
        self._sale = sale
        self._payments = payments

    def get_sale(self, sale_id: int) -> VenteSummary:
        return self._sale

    def list_payments(self, sale_id: int) -> list[PaiementSummary]:
        return self._payments

    def can_manage_sale(self, sale_id: int, permission: str) -> bool:
        return False


def _make_payments(n: int) -> list[PaiementSummary]:
    now = datetime.now(timezone.utc)
    return [
        PaiementSummary(
            id=i, vente_id=1, montant=Decimal("100"), date_heure=now,
            mode_paiement=None, reference=None, user_id=1, username="admin", commentaire=None,
        )
        for i in range(1, n + 1)
    ]


def _build_dialog_with_payments(sale, payments):
    sale_service = _FakeSaleServiceWithPayments(sale, payments)
    return SaleDetailDialog(sale, [], "XOF", _StubReceiptService(), _StubPermissions(), sale_service=sale_service)


@pytest.mark.parametrize("n_lines", [0, 1, 2, 5])
def test_lines_table_height_grows_only_up_to_two_rows(qtbot, n_lines) -> None:
    dialog = _build_dialog(_make_sale(lignes=_make_lignes(n_lines), total=Decimal(str(100 * n_lines))))
    qtbot.addWidget(dialog)

    lines_table = dialog.findChildren(QTableWidget)[0]
    assert lines_table.rowCount() == n_lines
    displayed_rows = min(n_lines, 2)
    header_height = lines_table.horizontalHeader().sizeHint().height() or 32
    assert lines_table.height() == header_height + displayed_rows * 34 + 12
    assert lines_table.horizontalScrollBar().isVisible() is False


def test_lines_table_scrolls_vertically_beyond_two_rows(qtbot) -> None:
    dialog = _build_dialog(_make_sale(lignes=_make_lignes(6), total=Decimal("600")))
    qtbot.addWidget(dialog)
    dialog.show()

    lines_table = dialog.findChildren(QTableWidget)[0]
    assert lines_table.rowCount() == 6
    assert lines_table.verticalScrollBar().isVisible() is True


def test_lines_table_column_widths_preserved_after_height_change(qtbot) -> None:
    dialog = _build_dialog(_make_sale(lignes=_make_lignes(3), total=Decimal("300")))
    qtbot.addWidget(dialog)

    lines_table = dialog.findChildren(QTableWidget)[0]
    assert lines_table.columnWidth(1) == 110
    assert lines_table.columnWidth(2) == 150


@pytest.mark.parametrize("n_payments", [0, 1, 2, 4])
def test_payments_table_height_capped_at_two_rows(qtbot, n_payments) -> None:
    sale = _make_sale(statut=StatutOperation.VALIDEE)
    dialog = _build_dialog_with_payments(sale, _make_payments(n_payments))
    qtbot.addWidget(dialog)

    assert dialog.payments_table.rowCount() == n_payments
    displayed_rows = min(n_payments, 2)
    header_height = dialog.payments_table.horizontalHeader().sizeHint().height() or 32
    assert dialog.payments_table.height() == header_height + displayed_rows * 34 + 12


def test_payments_table_scrolls_vertically_beyond_two_rows(qtbot) -> None:
    sale = _make_sale(statut=StatutOperation.VALIDEE)
    dialog = _build_dialog_with_payments(sale, _make_payments(5))
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.payments_table.rowCount() == 5
    assert dialog.payments_table.verticalScrollBar().isVisible() is True


@pytest.mark.parametrize("n_movements", [0, 1, 2, 4])
def test_movements_table_height_capped_at_two_rows(qtbot, n_movements) -> None:
    movements = _make_movements(n_movements)
    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE), movements)
    qtbot.addWidget(dialog)

    if n_movements == 0:
        assert dialog.movements_table is None
        return
    assert dialog.movements_table.rowCount() == n_movements
    displayed_rows = min(n_movements, 2)
    header_height = dialog.movements_table.horizontalHeader().sizeHint().height() or 32
    assert dialog.movements_table.height() == header_height + displayed_rows * 34 + 12


def test_movements_table_scrolls_vertically_beyond_two_rows(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE), _make_movements(6))
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.movements_table.rowCount() == 6
    assert dialog.movements_table.verticalScrollBar().isVisible() is True


def test_no_horizontal_scroll_on_any_table_at_1366x768(qtbot) -> None:
    dialog = _build_dialog(
        _make_sale(lignes=_make_lignes(3), statut=StatutOperation.VALIDEE, total=Decimal("300")),
        _make_movements(3),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.resize(min(dialog.width(), 1366), min(dialog.height(), 768))
    qtbot.wait(10)

    tables = [dialog.findChildren(QTableWidget)[0], dialog.payments_table, dialog.movements_table]
    for table in tables:
        assert table.horizontalScrollBar().isVisible() is False
