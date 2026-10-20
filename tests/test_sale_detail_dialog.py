from datetime import datetime, timezone
from decimal import Decimal

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

    assert dialog.export_a4_button.isEnabled() is False
    assert dialog.export_ticket_button.isEnabled() is False
    assert dialog.print_receipt_button.isEnabled() is False


def test_receipt_buttons_disabled_for_annulee(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.ANNULEE))
    qtbot.addWidget(dialog)

    assert dialog.export_a4_button.isEnabled() is False


def test_receipt_buttons_enabled_for_validee(qtbot) -> None:
    dialog = _build_dialog(_make_sale(statut=StatutOperation.VALIDEE))
    qtbot.addWidget(dialog)

    assert dialog.export_a4_button.isEnabled() is True
    assert dialog.export_ticket_button.isEnabled() is True
    assert dialog.print_receipt_button.isEnabled() is True


def test_receipt_buttons_disabled_without_sale_view_permission(qtbot) -> None:
    class _NoAccess:
        def has_permission(self, code: str) -> bool:
            return False

    dialog = SaleDetailDialog(
        _make_sale(statut=StatutOperation.VALIDEE), [], "XOF", _StubReceiptService(), _NoAccess()
    )
    qtbot.addWidget(dialog)

    assert dialog.export_a4_button.isEnabled() is False


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

    form = dialog.findChild(QFormLayout)
    row_labels = [
        form.itemAt(i, QFormLayout.ItemRole.LabelRole).widget().text() for i in range(form.rowCount())
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
