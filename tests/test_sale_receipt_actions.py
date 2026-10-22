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

from app.models.enums import StatutOperation
from app.services.documents.receipt_document import ReceiptFormat
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import AppError
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

    dialog = SaleDetailDialog(sale, movements, "XOF", stack.documents, stack.permissions, sale_service=stack.sales)
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


# -- export PDF unifié (Lot 22, §7.3) ---------------------------------------------------


def test_export_pdf_button_prompts_format_then_file_and_writes_a4(
    qtbot, login_as, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)
    out = tmp_path / "recu.pdf"

    monkeypatch.setattr(dialog, "_prompt_export_format", lambda: ReceiptFormat.A4)
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QFileDialog.getSaveFileName", lambda *a, **k: (str(out), "")
    )

    dialog._on_export_pdf_clicked()

    assert out.exists()
    assert out.read_bytes()[:5] == b"%PDF-"


def test_export_pdf_button_prompts_format_then_file_and_writes_ticket(
    qtbot, login_as, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)
    out = tmp_path / "recu_ticket.pdf"

    monkeypatch.setattr(dialog, "_prompt_export_format", lambda: ReceiptFormat.TICKET_80MM)
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QFileDialog.getSaveFileName", lambda *a, **k: (str(out), "")
    )

    dialog._on_export_pdf_clicked()

    assert out.exists()


def test_export_pdf_cancelling_format_choice_does_not_open_file_dialog_or_error(
    qtbot, login_as, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    monkeypatch.setattr(dialog, "_prompt_export_format", lambda: None)
    called = {"n": 0}
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or ("", ""),
    )

    dialog._on_export_pdf_clicked()  # ne doit jamais lever d'exception

    assert called["n"] == 0


def test_export_pdf_cancelling_file_choice_does_not_error_or_write_file(
    qtbot, login_as, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    monkeypatch.setattr(dialog, "_prompt_export_format", lambda: ReceiptFormat.A4)
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QFileDialog.getSaveFileName", lambda *a, **k: ("", "")
    )

    dialog._on_export_pdf_clicked()  # ne doit jamais lever d'exception ni modifier les données


def test_export_pdf_does_not_use_print_format_combo(qtbot, login_as, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """§7.3 : le format d'export ne doit jamais dépendre de
    ``receipt_format_combo``, réservé à l'impression — changer sa valeur
    ne doit avoir aucun effet sur le format réellement exporté."""
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)
    index = dialog.receipt_format_combo.findData(ReceiptFormat.TICKET_80MM)
    dialog.receipt_format_combo.setCurrentIndex(index)
    out = tmp_path / "recu.pdf"

    used_formats: list = []
    original_export = dialog._export_receipt_to

    def _spy_export(file_path, receipt_format):
        used_formats.append(receipt_format)
        return original_export(file_path, receipt_format)

    monkeypatch.setattr(dialog, "_export_receipt_to", _spy_export)
    monkeypatch.setattr(dialog, "_prompt_export_format", lambda: ReceiptFormat.A4)
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QFileDialog.getSaveFileName", lambda *a, **k: (str(out), "")
    )

    dialog._on_export_pdf_clicked()

    assert used_formats == [ReceiptFormat.A4]


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


# -- ventes à crédit / paiements partiels (§5) ----------------------------------------


def test_payment_section_shows_initial_state_after_validation(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, sale = _build_dialog_for_validated_sale(qtbot, stack)

    assert dialog.montant_paye_label.text() != ""
    assert dialog.reste_a_payer_label.text() != ""


def test_record_payment_button_and_method_removed(qtbot, login_as) -> None:
    """Lot 22 (§7.2) : le bouton « Enregistrer un paiement » et ses méthodes
    dédiées (``_on_record_payment_clicked``/``_submit_payment``) sont
    entièrement supprimés du détail de vente — le paiement différé d'une
    vente validée se fait désormais depuis le bouton « Payer » de la liste
    des ventes (``SalesPage``, cf. ``tests/test_sales_page.py``), qui reste
    accessible même après la fermeture de la session de caisse où la vente
    a été validée. Remplace les anciens tests
    ``test_record_payment_button_disabled_once_fully_paid``/
    ``test_record_payment_button_disabled_for_draft_sale``, devenus sans
    objet. Le tableau d'historique des paiements reste, lui, entièrement
    inchangé."""
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    assert not hasattr(dialog, "record_payment_button")
    assert not hasattr(dialog, "_on_record_payment_clicked")
    assert not hasattr(dialog, "_submit_payment")


def test_refresh_payment_section_updates_labels_and_history(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, sale = _build_dialog_for_validated_sale(qtbot, stack)  # total 300

    stack.sales.record_payment(sale.id, Decimal("100"), mode_paiement="Espèces")
    dialog._refresh_payment_section()

    assert dialog.payments_table.rowCount() == 1
    assert dialog.payments_table.item(0, 1).text() != ""
    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.montant_paye == Decimal("100")


def test_payment_receipt_button_and_method_removed(qtbot, login_as) -> None:
    """Lot 22 (§7.1) : le bouton « Reçu du paiement sélectionné (PDF) » et
    sa méthode d'export dédiée sont entièrement supprimés — remplacés par
    l'historique complet des paiements déjà présent dans le reçu de vente
    unifié (Lot 21). Remplace les anciens tests
    ``test_export_payment_receipt_*``/``test_export_payment_receipt_button_disabled_without_history``,
    devenus sans objet."""
    stack, _ = login_as("Administrateur")
    dialog, sale = _build_dialog_for_validated_sale(qtbot, stack)
    stack.sales.record_payment(sale.id, Decimal("100"))
    dialog._refresh_payment_section()

    assert not hasattr(dialog, "export_payment_receipt_button")
    assert not hasattr(dialog, "_export_payment_receipt_to")
    # L'historique complet reste bien visible et consultable à l'écran.
    assert dialog.payments_table.rowCount() == 1


def test_payment_section_without_sale_service_does_not_crash(qtbot) -> None:
    """Compatibilité arrière : un appelant qui ne fournit pas ``sale_service``
    (ancienne signature) obtient un dialogue en lecture seule, sans plantage."""
    from datetime import datetime, timezone

    from app.models.enums import StatutOperation
    from app.services.sales.sale_service import VenteLigneSummary, VenteSummary

    now = datetime.now(timezone.utc)
    ligne = VenteLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        quantite=Decimal("10"), prix_unitaire=Decimal("800"), sous_total=Decimal("8000"),
    )
    sale = VenteSummary(
        id=1, numero="VNT-000001", date=now.date(), user_id=1, username="admin",
        statut=StatutOperation.VALIDEE, total=Decimal("8000"), lignes=[ligne],
        date_creation=now, date_modification=now,
    )

    class _StubReceiptService:
        def build_sale_receipt(self, sale_id: int):
            raise NotImplementedError

    class _StubPermissions:
        def has_permission(self, code: str) -> bool:
            return True

    dialog = SaleDetailDialog(sale, [], "XOF", _StubReceiptService(), _StubPermissions())
    assert dialog.payments_table.rowCount() == 0


# -- annulation depuis le détail (Lot 15 — étape 2) -------------------------------


def _grant_sale_cancel_to_vendeur(stack) -> None:
    role_id = next(r.id for r in stack.roles.list_roles() if r.nom == "Vendeur")
    current_codes = stack.roles.get_role_permissions(role_id)
    stack.roles.update_role_permissions(role_id, current_codes + ["SALE_CANCEL"])


def _build_dialog_for_sale(qtbot, stack, sale_id):
    sale = stack.sales.get_sale(sale_id)
    try:
        movements = stack.sales.get_sale_movements(sale_id)
    except AppError:
        movements = []
    dialog = SaleDetailDialog(sale, movements, "XOF", stack.documents, stack.permissions, sale_service=stack.sales)
    qtbot.addWidget(dialog)
    return dialog, sale


class _FakeReasonDialog:
    """Même doublure que ``test_sales_page.py`` pour ``CancellationReasonDialog``
    — évite d'afficher un vrai dialogue modal pendant les tests."""

    def __init__(self, operation_label: str, parent=None) -> None:
        self.operation_label = operation_label

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted

    def reason(self) -> str:
        return "Motif saisi via le dialogue de détail"


def test_cancel_button_enabled_for_validated_sale_with_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    assert dialog.cancel_sale_button.isEnabled() is True


def test_cancel_button_disabled_for_draft_sale(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack)
    draft = stack.sales.create_sale(date(2026, 1, 15), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))])

    dialog, _sale = _build_dialog_for_sale(qtbot, stack, draft.id)

    assert dialog.cancel_sale_button.isEnabled() is False


def test_cancel_button_disabled_for_already_cancelled_sale(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    _dialog, sale = _build_dialog_for_validated_sale(qtbot, stack)
    stack.sales.cancel_sale(sale.id, "Motif de test valide")

    dialog, _sale = _build_dialog_for_sale(qtbot, stack, sale.id)

    assert dialog.cancel_sale_button.isEnabled() is False


def test_cancel_button_disabled_for_another_vendeur_sale(qtbot, login_as) -> None:
    """Respect de la propriété Vendeur (§3 de l'analyse préalable) : le
    bouton ne réimplémente pas la règle, il réutilise ``can_manage_sale``."""
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)
    _grant_sale_cancel_to_vendeur(admin_stack)

    vendeur_y_stack, _ = login_as("Vendeur")
    sale = vendeur_y_stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))]
    )
    vendeur_y_stack.sales.validate_sale(sale.id)

    vendeur_x_stack, _ = login_as("Vendeur")
    dialog, _sale = _build_dialog_for_sale(qtbot, vendeur_x_stack, sale.id)

    assert dialog.cancel_sale_button.isEnabled() is False


def test_cancel_button_enabled_for_own_sale_with_granted_permission(qtbot, login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)
    _grant_sale_cancel_to_vendeur(admin_stack)

    stack, _ = login_as("Vendeur")
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    dialog, _sale = _build_dialog_for_sale(qtbot, stack, sale.id)

    assert dialog.cancel_sale_button.isEnabled() is True


def test_on_cancel_sale_clicked_opens_reason_dialog_and_passes_reason_to_service(
    qtbot, login_as, monkeypatch
) -> None:
    stack, _ = login_as("Administrateur")
    dialog, sale = _build_dialog_for_validated_sale(qtbot, stack)
    monkeypatch.setattr("app.views.sale_detail_dialog.CancellationReasonDialog", _FakeReasonDialog)

    dialog._on_cancel_sale_clicked()

    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.statut == StatutOperation.ANNULEE
    assert reloaded.annulation_motif == "Motif saisi via le dialogue de détail"


def test_submit_cancel_sale_updates_statut_label_immediately(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    result = dialog._submit_cancel_sale("Motif de test valide")

    assert result is True
    assert dialog.statut_label.text() == "Annulée"


def test_submit_cancel_sale_shows_motif_row_after_success(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QFormLayout

    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    dialog._submit_cancel_sale("Motif affiché après annulation")

    form = dialog.findChild(QFormLayout)
    rows = {
        form.itemAt(i, QFormLayout.ItemRole.LabelRole).widget().text(): form.itemAt(
            i, QFormLayout.ItemRole.FieldRole
        ).widget()
        for i in range(form.rowCount())
        if form.itemAt(i, QFormLayout.ItemRole.LabelRole) is not None
    }
    assert rows["Motif d'annulation"].text() == "Motif affiché après annulation"


def test_submit_cancel_sale_refreshes_movements_with_permission(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)
    rows_before = dialog.movements_table.rowCount()

    dialog._submit_cancel_sale("Motif de test valide")

    assert dialog.movements_table.rowCount() == rows_before + 1
    last_row_type = dialog.movements_table.item(dialog.movements_table.rowCount() - 1, 1).text()
    assert last_row_type == "ANNULATION"


def test_submit_cancel_sale_does_not_reveal_movements_without_permission(qtbot, login_as) -> None:
    """Un utilisateur sans ``STOCK_MOVEMENT_VIEW`` (Vendeur, par défaut, cf.
    ``test_receipt_service.py``) ne doit jamais voir de mouvements, même
    après avoir lui-même déclenché l'annulation."""
    admin_stack, _ = login_as("Administrateur")
    article = _make_article(admin_stack)
    _grant_sale_cancel_to_vendeur(admin_stack)

    stack, _ = login_as("Vendeur")
    assert stack.permissions.has_permission("STOCK_MOVEMENT_VIEW") is False
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.sales.validate_sale(sale.id)

    dialog, _sale = _build_dialog_for_sale(qtbot, stack, sale.id)
    assert dialog.movements_table is None

    dialog._submit_cancel_sale("Motif de test valide")

    assert dialog.movements_table is None


def test_submit_cancel_sale_disables_receipt_actions(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)
    assert dialog.export_pdf_button.isEnabled() is True

    dialog._submit_cancel_sale("Motif de test valide")

    assert dialog.export_pdf_button.isEnabled() is False
    assert dialog.print_receipt_button.isEnabled() is False
    assert dialog.receipt_format_combo.isEnabled() is False


def test_submit_cancel_sale_preserves_payment_history(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, sale = _build_dialog_for_validated_sale(qtbot, stack)
    stack.sales.record_payment(sale.id, Decimal("100"), mode_paiement="Espèces")
    dialog._refresh_payment_section()
    assert dialog.payments_table.rowCount() == 1

    dialog._submit_cancel_sale("Motif de test valide")

    assert dialog.payments_table.rowCount() == 1
    assert dialog.montant_paye_label.text() != ""
    reloaded = stack.sales.get_sale(sale.id)
    assert reloaded.montant_paye == Decimal("100")
    assert len(stack.sales.list_payments(sale.id)) == 1


def test_submit_cancel_sale_handles_business_error_without_fake_success(qtbot, login_as, monkeypatch) -> None:
    successes: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QMessageBox.information",
        lambda *a, **k: successes.append(a[2] if len(a) > 2 else ""),
    )
    monkeypatch.setattr(
        "app.views.sale_detail_dialog.QMessageBox.warning",
        lambda *a, **k: warnings.append(a[2] if len(a) > 2 else ""),
    )

    stack, _ = login_as("Administrateur")
    dialog, sale = _build_dialog_for_validated_sale(qtbot, stack)
    # Annulation concurrente, simulant un échec métier lors du clic dans le dialogue.
    stack.sales.cancel_sale(sale.id, "Annulée entre-temps ailleurs")

    result = dialog._submit_cancel_sale("Nouvelle tentative depuis le détail")

    assert result is False
    assert warnings and not successes
    # Aucun état visuel incohérent : le libellé affiché n'a pas été modifié
    # par cette tentative échouée (toujours la valeur chargée à l'ouverture).
    assert dialog.statut_label.text() == "Validée"


def test_cannot_trigger_second_cancellation_from_refreshed_dialog(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog, _sale = _build_dialog_for_validated_sale(qtbot, stack)

    first = dialog._submit_cancel_sale("Premier motif valide")
    assert first is True
    assert dialog.cancel_sale_button.isEnabled() is False

    second = dialog._submit_cancel_sale("Deuxième motif valide")
    assert second is False
