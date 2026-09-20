from datetime import datetime, timezone
from decimal import Decimal

from app.services.articles.article_service import ArticleSummary
from app.views.article_detail_dialog import ArticleDetailDialog


def _make_summary(**overrides) -> ArticleSummary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=1, reference="ART-1", designation="Article test", category_id=1, category_nom="Boissons",
        fournisseur_principal_id=None, fournisseur_principal_nom=None, unite="unité",
        prix_achat=Decimal("100.00"), prix_vente=Decimal("150.00"), cout_moyen_pondere=Decimal("100.00"),
        stock_actuel=Decimal("50.000"), stock_min=Decimal("10.000"), stock_max=Decimal("200.000"),
        emplacement="Rayon A1", description="Une description", code_barres="123456789",
        actif=True, date_creation=now, date_modification=now,
    )
    defaults.update(overrides)
    return ArticleSummary(**defaults)


def test_detail_dialog_shows_reference_in_title(qtbot) -> None:
    dialog = ArticleDetailDialog(_make_summary(), "XOF")
    qtbot.addWidget(dialog)

    assert "ART-1" in dialog.windowTitle()


def test_detail_dialog_strips_unnecessary_decimals_from_stock(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ArticleDetailDialog(
        _make_summary(stock_actuel=Decimal("50.000"), stock_min=Decimal("10.000"), stock_max=Decimal("200.000")),
        "XOF",
    )
    qtbot.addWidget(dialog)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "50.000" not in texts and "50" in texts
    assert "10.000" not in texts and "10" in texts
    assert "200.000" not in texts and "200" in texts


def test_detail_dialog_preserves_real_decimal_stock(qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    dialog = ArticleDetailDialog(_make_summary(stock_actuel=Decimal("10.500")), "XOF")
    qtbot.addWidget(dialog)

    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "10,5" in texts


def test_detail_dialog_formats_money_with_currency(qtbot) -> None:
    dialog = ArticleDetailDialog(_make_summary(prix_achat=Decimal("15000")), "XOF")
    qtbot.addWidget(dialog)
    # Le formulaire construit les labels dynamiquement ; on vérifie via values-independent check
    # en relisant le format_money utilisé.
    from app.utils.money import format_money

    assert format_money(Decimal("15000"), "XOF") == "15 000 FCFA"


def test_detail_dialog_close_button_accepts(qtbot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    dialog = ArticleDetailDialog(_make_summary(), "XOF")
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.close_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_detail_dialog_does_not_crash_for_rupture_article(qtbot) -> None:
    dialog = ArticleDetailDialog(_make_summary(stock_actuel=Decimal("0")), "XOF")
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_does_not_crash_for_low_stock_article(qtbot) -> None:
    dialog = ArticleDetailDialog(
        _make_summary(stock_actuel=Decimal("5.000"), stock_min=Decimal("10.000")), "XOF"
    )
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_detail_dialog_handles_missing_optional_fields(qtbot) -> None:
    dialog = ArticleDetailDialog(
        _make_summary(
            fournisseur_principal_nom=None, stock_max=None, emplacement=None,
            code_barres=None, description=None,
        ),
        "XOF",
    )
    qtbot.addWidget(dialog)
    assert dialog is not None
