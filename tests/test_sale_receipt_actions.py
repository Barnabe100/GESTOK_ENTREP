"""Tests d'intégration des actions de reçu (export PDF / impression)
exposées par ``SaleDetailDialog``, avec de vrais services (via ``login_as``)
plutôt que des doublures — complète ``test_sale_detail_dialog.py`` (rendu
du dialogue) et ``test_receipt_service.py``/``test_receipt_document.py``
(données/gabarits) en validant le chemin complet déclenché par un clic.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from app.services.documents.receipt_document import ReceiptFormat
from app.services.sales.sale_service import VenteLigneInput
from app.views.sale_detail_dialog import SaleDetailDialog


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.views.sale_detail_dialog.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.sale_detail_dialog.QMessageBox.warning", lambda *a, **k: None)


def _make_article(stack, reference="ART-1", stock_initial=Decimal("50")):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=stock_initial,
    )


def _build_dialog_for_validated_sale(qtbot, stack, client_id=None):
    article = _make_article(stack)
    sale_draft = stack.sales.create_sale(
        date(2026, 1, 15), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client_id
    )
    validated = stack.sales.validate_sale(sale_draft.id)
    sale = stack.sales.get_sale(validated.id)
    movements = stack.sales.get_sale_movements(validated.id)

    dialog = SaleDetailDialog(sale, movements, "XOF", stack.documents, stack.permissions)
    qtbot.addWidget(dialog)
    return dialog, sale


# -- export PDF ----------------------------------------------------------------------


def test_export_a4_writes_pdf_file(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    out = tmp_path / "recu.pdf"
    result = dialog._export_receipt_to(str(out), ReceiptFormat.A4)

    assert result is True
    assert out.exists()
    assert out.read_bytes()[:5] == b"%PDF-"


def test_export_ticket_writes_pdf_file(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    out = tmp_path / "recu_ticket.pdf"
    result = dialog._export_receipt_to(str(out), ReceiptFormat.TICKET_80MM)

    assert result is True
    assert out.exists()


def test_export_refused_for_brouillon_sale(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    draft = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))])
    sale = stack.sales.get_sale(draft.id)

    dialog = SaleDetailDialog(sale, [], "XOF", stack.documents, stack.permissions)
    qtbot.addWidget(dialog)

    out = tmp_path / "recu.pdf"
    result = dialog._export_receipt_to(str(out), ReceiptFormat.A4)

    assert result is False
    assert not out.exists()


def test_export_does_not_affect_stock(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    dialog, sale = _build_dialog_for_validated_sale(qtbot, stack)
    article_id = sale.lignes[0].article_id
    stock_before = stack.articles.get_article(article_id).stock_actuel

    dialog._export_receipt_to(str(tmp_path / "recu.pdf"), ReceiptFormat.A4)

    stock_after = stack.articles.get_article(article_id).stock_actuel
    assert stock_before == stock_after


# -- impression ------------------------------------------------------------------------


def test_print_shows_message_when_no_printer_available(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    # Cet environnement de test n'a jamais d'imprimante installée — c'est
    # précisément le cas « aucune imprimante disponible » à couvrir.
    result = dialog._print_receipt(ReceiptFormat.A4)

    assert result is False


def test_print_succeeds_when_printer_available_and_dialog_accepted(
    qtbot, login_as, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QPrinterInfo.availablePrinters", staticmethod(lambda: ["Imprimante factice"])
    )
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QPrintDialog.exec", lambda self: QDialog.DialogCode.Accepted
    )

    result = dialog._print_receipt(ReceiptFormat.TICKET_80MM)

    assert result is True


def test_print_cancelled_via_dialog_returns_false(qtbot, login_as, monkeypatch: pytest.MonkeyPatch) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QPrinterInfo.availablePrinters", staticmethod(lambda: ["Imprimante factice"])
    )
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QPrintDialog.exec", lambda self: QDialog.DialogCode.Rejected
    )

    result = dialog._print_receipt(ReceiptFormat.A4)

    assert result is False


# -- avec client (lot Intégration du client dans les reçus et PDF) ---------------------


def test_export_a4_with_client_writes_pdf_file(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    client = stack.clients.create_client("Jean Dupont", telephone="0102030405")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack, client_id=client.id)

    out = tmp_path / "recu_client.pdf"
    result = dialog._export_receipt_to(str(out), ReceiptFormat.A4)

    assert result is True
    assert out.exists()
    assert out.read_bytes()[:5] == b"%PDF-"


def test_export_ticket_with_client_writes_pdf_file(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    client = stack.clients.create_client("Jean Dupont", telephone="0102030405")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack, client_id=client.id)

    out = tmp_path / "recu_ticket_client.pdf"
    result = dialog._export_receipt_to(str(out), ReceiptFormat.TICKET_80MM)

    assert result is True
    assert out.exists()


def test_print_with_client_succeeds_when_printer_available(
    qtbot, login_as, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack, _ = login_as("Administrateur")
    client = stack.clients.create_client("Jean Dupont")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack, client_id=client.id)

    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QPrinterInfo.availablePrinters", staticmethod(lambda: ["Imprimante factice"])
    )
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QPrintDialog.exec", lambda self: QDialog.DialogCode.Accepted
    )

    result = dialog._print_receipt(ReceiptFormat.A4)

    assert result is True


def test_export_with_deactivated_client_still_succeeds(qtbot, login_as, tmp_path) -> None:
    """§8 : un client désactivé associé à une vente historique ne doit
    jamais empêcher l'export du reçu."""
    stack, _ = login_as("Administrateur")
    client = stack.clients.create_client("Client historique")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack, client_id=client.id)
    stack.clients.deactivate_client(client.id)

    out = tmp_path / "recu_client_desactive.pdf"
    result = dialog._export_receipt_to(str(out), ReceiptFormat.A4)

    assert result is True
    assert out.exists()
