from decimal import Decimal

from app.models.enums import ModeGestionArticle
from app.views.article_mode_gestion_dialog import ArticleModeGestionDialog


def test_proposes_the_other_mode_by_default(qtbot) -> None:
    dialog = ArticleModeGestionDialog("ART-1", ModeGestionArticle.VENTE, Decimal("0"))
    qtbot.addWidget(dialog)

    assert dialog.nouveau_mode() == ModeGestionArticle.LOCATION


def test_warning_shown_when_target_is_location_without_tarif(qtbot) -> None:
    """Lot « Gestion du mode Vente / Location » (§4D/§6.3) : ce parcours
    reste volontairement aussi permissif qu'avant ce lot — la bascule sans
    tarif n'est jamais bloquée ici, seulement signalée."""
    dialog = ArticleModeGestionDialog("ART-1", ModeGestionArticle.VENTE, None)
    qtbot.addWidget(dialog)

    assert "ucun tarif" in dialog.tarif_warning_label.text()


def test_warning_hidden_when_target_is_location_with_positive_tarif(qtbot) -> None:
    dialog = ArticleModeGestionDialog("ART-1", ModeGestionArticle.VENTE, Decimal("500"))
    qtbot.addWidget(dialog)

    assert dialog.tarif_warning_label.text() == ""


def test_warning_hidden_when_target_is_vente(qtbot) -> None:
    dialog = ArticleModeGestionDialog("ART-1", ModeGestionArticle.LOCATION, None)
    qtbot.addWidget(dialog)

    assert dialog.nouveau_mode() == ModeGestionArticle.VENTE
    assert dialog.tarif_warning_label.text() == ""


def test_warning_updates_immediately_when_mode_changed(qtbot) -> None:
    dialog = ArticleModeGestionDialog("ART-1", ModeGestionArticle.LOCATION, None)
    qtbot.addWidget(dialog)
    assert dialog.tarif_warning_label.text() == ""

    index_location = dialog.mode_combo.findData(ModeGestionArticle.LOCATION)
    dialog.mode_combo.setCurrentIndex(index_location)

    assert "ucun tarif" in dialog.tarif_warning_label.text()
