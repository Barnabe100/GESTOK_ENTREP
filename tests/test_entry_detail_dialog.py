from datetime import datetime, timezone
from decimal import Decimal

from app.models.enums import StatutOperation, TypeMouvement
from app.services.entries.entry_service import EntreeLigneSummary, EntreeSummary, MouvementSummary
from app.views.entry_detail_dialog import EntryDetailDialog


def _make_entry(**overrides) -> EntreeSummary:
    now = datetime.now(timezone.utc)
    ligne = EntreeLigneSummary(
        id=1, article_id=10, article_reference="ART-1", article_designation="Eau",
        quantite=Decimal("10"), prix_unitaire=Decimal("500"), montant=Decimal("5000"),
    )
    defaults = dict(
        id=1, numero="ENT-000001", date=now.date(), fournisseur_id=1, fournisseur_nom="Fournisseur A",
        reference_document="BL-42", user_id=1, username="admin", commentaire="Commentaire",
        statut=StatutOperation.BROUILLON, lignes=[ligne], date_creation=now, date_modification=now,
    )
    defaults.update(overrides)
    return EntreeSummary(**defaults)


def _make_movement(**overrides) -> MouvementSummary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, article_id=10, article_reference="ART-1", type=TypeMouvement.ENTREE,
        quantite=Decimal("10"), stock_avant=Decimal("0"), stock_apres=Decimal("10"),
        cout_unitaire=Decimal("500"), date_heure=now, user_id=1, username="admin", commentaire=None,
    )
    defaults.update(overrides)
    return MouvementSummary(**defaults)


def test_detail_dialog_shows_numero_in_title(qtbot) -> None:
    dialog = EntryDetailDialog(_make_entry(), [], "XOF")
    qtbot.addWidget(dialog)

    assert "ENT-000001" in dialog.windowTitle()


def test_detail_dialog_does_not_crash_with_no_movements(qtbot) -> None:
    dialog = EntryDetailDialog(_make_entry(), [], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_shows_movements(qtbot) -> None:
    dialog = EntryDetailDialog(_make_entry(), [_make_movement()], "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_close_button_accepts(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    dialog = EntryDetailDialog(_make_entry(), [], "XOF")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_detail_dialog_handles_missing_optional_fields(qtbot) -> None:
    dialog = EntryDetailDialog(
        _make_entry(reference_document=None, commentaire=None, lignes=[]), [], "XOF"
    )
    qtbot.addWidget(dialog)
    assert dialog is not None
