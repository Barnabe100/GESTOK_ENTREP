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
