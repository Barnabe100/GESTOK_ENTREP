from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from app.resources import APP_ICON_PATH
from app.services.settings.company_settings_service import (
    DEFAULT_CURRENCY,
    get_effective_currency,
    is_rental_module_enabled,
)
from app.utils.exceptions import PermissionDeniedError, ValidationError


def _make_test_image(path: Path, width: int = 20, height: int = 20) -> None:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(path))


# -- permissions ---------------------------------------------------------------------


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_non_admin_roles_are_denied_view(login_as, role_name) -> None:
    stack, _ = login_as(role_name)

    with pytest.raises(PermissionDeniedError):
        stack.parameters.get_config()


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_non_admin_roles_are_denied_update(login_as, role_name) -> None:
    stack, _ = login_as(role_name)

    with pytest.raises(PermissionDeniedError):
        stack.parameters.update_config(
            nom="Ma Société", adresse=None, telephone=None, email=None, devise="XOF"
        )


def test_administrateur_can_view_and_update(login_as) -> None:
    stack, _ = login_as("Administrateur")

    stack.parameters.update_config(nom="Ma Société", adresse=None, telephone=None, email=None, devise="XOF")
    config = stack.parameters.get_config()

    assert config.nom == "Ma Société"


# -- consultation par défaut ------------------------------------------------------------


def test_get_config_before_any_save_has_no_nom_and_default_currency(login_as) -> None:
    stack, _ = login_as("Administrateur")

    config = stack.parameters.get_config()

    assert config.nom is None
    assert config.devise == DEFAULT_CURRENCY
    assert config.logo_path is None


# -- persistance -----------------------------------------------------------------------


def test_update_config_persists_all_fields(login_as) -> None:
    stack, _ = login_as("Administrateur")

    updated = stack.parameters.update_config(
        nom="StockManager Client SARL", adresse="12 rue du Commerce, Abidjan",
        telephone="+225 01 02 03 04 05", email="contact@client.ci", devise="XOF",
    )

    assert updated.nom == "StockManager Client SARL"
    assert updated.adresse == "12 rue du Commerce, Abidjan"
    assert updated.telephone == "+225 01 02 03 04 05"
    assert updated.email == "contact@client.ci"
    assert updated.devise == "XOF"

    reloaded = stack.parameters.get_config()
    assert reloaded == updated


def test_update_config_clears_optional_fields_with_empty_string(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.update_config(
        nom="Société", adresse="Adresse initiale", telephone="0102030405", email="a@b.com", devise="XOF"
    )

    updated = stack.parameters.update_config(nom="Société", adresse="", telephone="", email="", devise="XOF")

    assert updated.adresse is None
    assert updated.telephone is None
    assert updated.email is None


# -- validations -------------------------------------------------------------------------


def test_update_config_rejects_empty_nom(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.parameters.update_config(nom="   ", adresse=None, telephone=None, email=None, devise="XOF")


def test_update_config_rejects_invalid_email(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.parameters.update_config(
            nom="Société", adresse=None, telephone=None, email="pas-un-email", devise="XOF"
        )


def test_update_config_rejects_unsupported_currency(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.parameters.update_config(nom="Société", adresse=None, telephone=None, email=None, devise="ABC")


def test_update_config_accepts_lowercase_currency(login_as) -> None:
    stack, _ = login_as("Administrateur")

    updated = stack.parameters.update_config(nom="Société", adresse=None, telephone=None, email=None, devise="eur")

    assert updated.devise == "EUR"


# -- logo de l'entreprise ---------------------------------------------------------------


def test_set_logo_persists_and_is_readable_via_get_config(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    logo_file = tmp_path / "source_logo.png"
    _make_test_image(logo_file)

    updated = stack.parameters.set_logo(logo_file)

    assert updated.logo_path is not None
    assert updated.logo_path.exists()
    assert stack.parameters.get_config().logo_path == updated.logo_path


def test_set_logo_is_stored_in_writable_data_dir_never_in_app_resources(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    logo_file = tmp_path / "source_logo.png"
    _make_test_image(logo_file)
    original_icon_bytes = APP_ICON_PATH.read_bytes()

    updated = stack.parameters.set_logo(logo_file)

    assert "app" + "/resources" not in str(updated.logo_path).replace("\\", "/")
    assert "resources" not in updated.logo_path.parts
    # Le logo produit StockManager/SM n'est ni modifié ni remplacé.
    assert APP_ICON_PATH.read_bytes() == original_icon_bytes


def test_set_logo_rejects_unsupported_extension(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    bad_file = tmp_path / "logo.gif"
    bad_file.write_bytes(b"not-really-a-gif")

    with pytest.raises(ValidationError):
        stack.parameters.set_logo(bad_file)


def test_set_logo_rejects_missing_file(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.parameters.set_logo(tmp_path / "does_not_exist.png")


def test_set_logo_rejects_oversized_file(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    huge_file = tmp_path / "huge.png"
    huge_file.write_bytes(b"0" * (6 * 1024 * 1024))

    with pytest.raises(ValidationError):
        stack.parameters.set_logo(huge_file)


def test_set_logo_rejects_oversized_dimensions(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    wide_file = tmp_path / "wide.png"
    _make_test_image(wide_file, width=4001, height=10)

    with pytest.raises(ValidationError):
        stack.parameters.set_logo(wide_file)


def test_set_logo_rejects_invalid_image_content(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"not an actual image")

    with pytest.raises(ValidationError):
        stack.parameters.set_logo(fake_image)


def test_set_logo_replaces_previous_file_of_different_extension(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    png_logo = tmp_path / "logo.png"
    _make_test_image(png_logo)
    jpg_logo = tmp_path / "logo.jpg"
    _make_test_image(jpg_logo)

    first = stack.parameters.set_logo(png_logo)
    assert first.logo_path.suffix == ".png"
    assert first.logo_path.exists()

    second = stack.parameters.set_logo(jpg_logo)
    assert second.logo_path.suffix == ".jpg"
    assert second.logo_path.exists()
    assert not first.logo_path.exists()


def test_clear_logo_removes_file_and_parameter(login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    logo_file = tmp_path / "source_logo.png"
    _make_test_image(logo_file)
    configured = stack.parameters.set_logo(logo_file)
    assert configured.logo_path.exists()

    cleared = stack.parameters.clear_logo()

    assert cleared.logo_path is None
    assert not configured.logo_path.exists()


def test_clear_logo_without_prior_logo_is_a_no_op(login_as) -> None:
    stack, _ = login_as("Administrateur")

    cleared = stack.parameters.clear_logo()

    assert cleared.logo_path is None


# -- devise effective --------------------------------------------------------------------


def test_get_effective_currency_falls_back_to_settings_default(login_as, test_settings) -> None:
    login_as("Administrateur")

    assert get_effective_currency(test_settings) == test_settings.default_currency


def test_get_effective_currency_reflects_saved_value(login_as, test_settings) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.update_config(nom="Société", adresse=None, telephone=None, email=None, devise="EUR")

    assert get_effective_currency(test_settings) == "EUR"


# -- module Location (Lot 16) ------------------------------------------------------------


def test_rental_module_enabled_by_default_when_key_absent(login_as, test_settings) -> None:
    login_as("Administrateur")

    assert is_rental_module_enabled(test_settings) is True


def test_rental_module_enabled_true_after_explicit_activation(login_as, test_settings) -> None:
    stack, _ = login_as("Administrateur")

    stack.parameters.set_rental_module_enabled(True)

    assert is_rental_module_enabled(test_settings) is True


def test_rental_module_disabled_after_explicit_deactivation(login_as, test_settings) -> None:
    stack, _ = login_as("Administrateur")

    stack.parameters.set_rental_module_enabled(False)

    assert is_rental_module_enabled(test_settings) is False


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_set_rental_module_enabled_denied_without_settings_update(login_as, test_settings, role_name) -> None:
    stack, _ = login_as(role_name)

    with pytest.raises(PermissionDeniedError):
        stack.parameters.set_rental_module_enabled(False)

    # Aucune écriture ne doit avoir eu lieu malgré le refus.
    assert is_rental_module_enabled(test_settings) is True


def test_set_rental_module_enabled_denied_does_not_modify_existing_value(login_as, test_settings) -> None:
    admin_stack, _ = login_as("Administrateur")
    admin_stack.parameters.set_rental_module_enabled(False)

    other_stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        other_stack.parameters.set_rental_module_enabled(True)

    # La valeur déjà enregistrée par l'administrateur reste inchangée.
    assert is_rental_module_enabled(test_settings) is False


def test_rental_module_value_persists_across_reads(login_as, test_settings) -> None:
    stack, _ = login_as("Administrateur")

    stack.parameters.set_rental_module_enabled(False)
    assert is_rental_module_enabled(test_settings) is False

    stack.parameters.set_rental_module_enabled(True)
    assert is_rental_module_enabled(test_settings) is True


# -- pied de reçu (Lot 21 — reçu unifié) ------------------------------------------------


def test_receipt_footer_default_when_unconfigured(login_as) -> None:
    from app.services.settings.company_settings_service import DEFAULT_RECEIPT_FOOTER

    stack, _ = login_as("Administrateur")

    config = stack.parameters.get_config()

    assert config.recu_pied_de_page == DEFAULT_RECEIPT_FOOTER


def test_set_receipt_footer_persists_and_is_readable(login_as) -> None:
    stack, _ = login_as("Administrateur")

    updated = stack.parameters.set_receipt_footer("À très vite !")

    assert updated.recu_pied_de_page == "À très vite !"
    assert stack.parameters.get_config().recu_pied_de_page == "À très vite !"


def test_set_receipt_footer_empty_disables_footer_not_default(login_as) -> None:
    """Une chaîne vide explicitement enregistrée doit rester vide à la
    lecture — jamais retomber sur la phrase par défaut (voir §7 du lot :
    « si la phrase est vide, aucun texte de fin n'est imprimé »)."""
    stack, _ = login_as("Administrateur")
    stack.parameters.set_receipt_footer("Une phrase quelconque")

    updated = stack.parameters.set_receipt_footer("")

    assert updated.recu_pied_de_page == ""
    assert stack.parameters.get_config().recu_pied_de_page == ""


def test_set_receipt_footer_strips_whitespace_only_to_empty(login_as) -> None:
    stack, _ = login_as("Administrateur")

    updated = stack.parameters.set_receipt_footer("   ")

    assert updated.recu_pied_de_page == ""


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_set_receipt_footer_denied_without_settings_update(login_as, role_name) -> None:
    stack, _ = login_as(role_name)

    with pytest.raises(PermissionDeniedError):
        stack.parameters.set_receipt_footer("Une phrase")


def test_set_receipt_footer_rejects_too_long_phrase(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.parameters.set_receipt_footer("x" * 201)


def test_set_receipt_footer_accepts_phrase_at_exact_max_length(login_as) -> None:
    stack, _ = login_as("Administrateur")

    updated = stack.parameters.set_receipt_footer("x" * 200)

    assert updated.recu_pied_de_page == "x" * 200


def test_update_config_never_touches_receipt_footer(login_as) -> None:
    """``update_config`` (profil/devise) ne doit jamais écraser le pied de
    reçu — c'est ``set_receipt_footer`` qui en a la responsabilité exclusive,
    pour ne jamais risquer de régression sur les nombreux appelants
    existants de ``update_config``."""
    stack, _ = login_as("Administrateur")
    stack.parameters.set_receipt_footer("Phrase personnalisée")

    stack.parameters.update_config(nom="Société", adresse=None, telephone=None, email=None, devise="EUR")

    assert stack.parameters.get_config().recu_pied_de_page == "Phrase personnalisée"
