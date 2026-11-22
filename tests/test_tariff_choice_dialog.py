from decimal import Decimal

from app.models.enums import TypeTarif
from app.views.tariff_choice_dialog import TariffChoiceDialog


def _build_dialog(**kwargs):
    defaults = dict(
        article_label="ART-1 — Article de test",
        prix_normal=Decimal("500000"),
        prix_sous_traitant=Decimal("400000"),
        intervalle_min=Decimal("350000"),
        intervalle_max=Decimal("550000"),
        currency_code="XOF",
    )
    defaults.update(kwargs)
    return TariffChoiceDialog(
        defaults.pop("article_label"),
        defaults.pop("prix_normal"),
        defaults.pop("prix_sous_traitant"),
        defaults.pop("intervalle_min"),
        defaults.pop("intervalle_max"),
        defaults.pop("currency_code"),
        **defaults,
    )


# -- sélection par défaut (§2.4/§3.1) ------------------------------------------


def test_normal_is_selected_by_default(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert dialog.normal_radio.isChecked() is True
    assert dialog.values() == (TypeTarif.NORMAL, Decimal("500000"))


def test_sous_traitant_radio_disabled_when_not_configured(qtbot) -> None:
    dialog = _build_dialog(prix_sous_traitant=None)
    qtbot.addWidget(dialog)

    assert dialog.sous_traitant_radio.isEnabled() is False


def test_autre_radio_disabled_when_interval_not_configured(qtbot) -> None:
    dialog = _build_dialog(intervalle_min=None, intervalle_max=None)
    qtbot.addWidget(dialog)

    assert dialog.autre_radio.isEnabled() is False


def test_autre_field_disabled_until_autre_radio_checked(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    assert dialog.autre_montant_edit.isEnabled() is False
    dialog.autre_radio.setChecked(True)
    assert dialog.autre_montant_edit.isEnabled() is True


# -- choix et restitution -------------------------------------------------------


def test_choosing_sous_traitant_returns_its_configured_amount(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    dialog.sous_traitant_radio.setChecked(True)

    assert dialog.values() == (TypeTarif.SOUS_TRAITANT, Decimal("400000"))


def test_choosing_autre_price_inside_interval_is_accepted(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    dialog.autre_radio.setChecked(True)
    dialog.autre_montant_edit.setText("450000")
    dialog._on_ok_clicked()

    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.values() == (TypeTarif.AUTRE, Decimal("450000"))


def test_choosing_autre_price_at_inclusive_bounds_is_accepted(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    dialog.autre_radio.setChecked(True)
    dialog.autre_montant_edit.setText("350000")
    dialog._on_ok_clicked()

    assert dialog.result() == dialog.DialogCode.Accepted


def test_choosing_autre_price_below_interval_is_rejected(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    dialog.autre_radio.setChecked(True)
    dialog.autre_montant_edit.setText("349999")
    dialog._on_ok_clicked()

    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.error_label.text() != ""


def test_choosing_autre_price_above_interval_is_rejected(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    dialog.autre_radio.setChecked(True)
    dialog.autre_montant_edit.setText("550001")
    dialog._on_ok_clicked()

    assert dialog.result() != dialog.DialogCode.Accepted


def test_choosing_autre_price_with_invalid_text_is_rejected(qtbot) -> None:
    dialog = _build_dialog()
    qtbot.addWidget(dialog)

    dialog.autre_radio.setChecked(True)
    dialog.autre_montant_edit.setText("abc")
    dialog._on_ok_clicked()

    assert dialog.result() != dialog.DialogCode.Accepted
    assert dialog.error_label.text() != ""


# -- re-sélection d'une ligne déjà choisie --------------------------------------


def test_initial_type_and_montant_are_restored_for_autre(qtbot) -> None:
    dialog = _build_dialog(initial_type=TypeTarif.AUTRE, initial_montant=Decimal("480000"))
    qtbot.addWidget(dialog)

    assert dialog.autre_radio.isChecked() is True
    assert dialog.autre_montant_edit.text() in ("480000", "480000.0")


def test_initial_type_sous_traitant_is_restored(qtbot) -> None:
    dialog = _build_dialog(initial_type=TypeTarif.SOUS_TRAITANT)
    qtbot.addWidget(dialog)

    assert dialog.sous_traitant_radio.isChecked() is True


# -- adaptation du libellé Ventes/Locations --------------------------------------


def test_location_wording_uses_tarif_instead_of_prix(qtbot) -> None:
    dialog = _build_dialog(is_location=True)
    qtbot.addWidget(dialog)

    assert "Tarif normal" in dialog.normal_radio.text()
    assert "tarif" in dialog.windowTitle().lower()
