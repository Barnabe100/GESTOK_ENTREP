"""Dialogue « À propos » (Lot P)."""
import pytest

from app.version import APP_NAME, __version__
from app.views.about_dialog import AboutDialog


def _build_dialog(stack) -> AboutDialog:
    return AboutDialog(stack.licenses, stack.permissions)


def test_shows_product_name(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QLabel

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    all_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert APP_NAME in all_text


def test_shows_version(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QLabel

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    all_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert __version__ in all_text


def test_shows_icon(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QLabel

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    icon_labels = [label for label in dialog.findChildren(QLabel) if not label.pixmap().isNull()]
    assert len(icon_labels) == 1


def test_logo_is_displayed_without_distorting_proportions(qtbot, login_as) -> None:
    """§ Identité visuelle : le logo officiel complet (symbole + texte +
    slogan) doit être affiché sans jamais déformer ses proportions — la
    mise à l'échelle est faite par largeur (scaledToWidth), donc le ratio
    largeur/hauteur affiché doit rester celui du fichier source."""
    from PIL import Image
    from PySide6.QtWidgets import QLabel

    from app.resources import APP_LOGO_FULL_PATH

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    icon_labels = [label for label in dialog.findChildren(QLabel) if not label.pixmap().isNull()]
    assert len(icon_labels) == 1
    displayed_pixmap = icon_labels[0].pixmap()

    with Image.open(APP_LOGO_FULL_PATH) as source_image:
        source_ratio = source_image.width / source_image.height
    displayed_ratio = displayed_pixmap.width() / displayed_pixmap.height()

    assert abs(displayed_ratio - source_ratio) < 0.01


def test_shows_publisher(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QLabel

    from app.version import PUBLISHER_NAME

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    all_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert PUBLISHER_NAME in all_text
    assert "TechNova" in all_text
    # Le produit reste StockManager, distinct de l'éditeur.
    assert APP_NAME in all_text


def test_shows_generic_support_text_without_fabricated_contact_details(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QLabel

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    all_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "documentation utilisateur" in all_text
    assert "diagnostic" in all_text or "log" in all_text
    # Aucune coordonnée fictive ne doit jamais apparaître.
    assert "@" not in all_text
    assert "http" not in all_text.lower()


# -- section licence : uniquement pour LICENSE_VIEW -----------------------------------


def test_license_section_shown_for_administrateur(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QGroupBox

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    titles = [group.title() for group in dialog.findChildren(QGroupBox)]
    assert "Licence" in titles


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_license_section_hidden_for_roles_without_license_view(qtbot, login_as, role_name: str) -> None:
    from PySide6.QtWidgets import QGroupBox

    stack, _ = login_as(role_name)
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    titles = [group.title() for group in dialog.findChildren(QGroupBox)]
    assert "Licence" not in titles


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_get_info_never_called_without_license_view(qtbot, login_as, monkeypatch, role_name: str) -> None:
    """Preuve directe que le dialogue n'appelle jamais une méthode gardée
    par une permission que l'utilisateur n'a pas (pas seulement que le
    résultat visuel est correct)."""
    from app.services.licensing.license_service import LicenseService

    calls: list[object] = []
    original_get_info = LicenseService.get_info

    def _spy_get_info(self):
        calls.append(self)
        return original_get_info(self)

    monkeypatch.setattr(LicenseService, "get_info", _spy_get_info)

    stack, _ = login_as(role_name)
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert calls == []


def test_dialog_can_be_closed(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert dialog.close() is True


def test_get_info_called_for_administrateur(qtbot, login_as, monkeypatch) -> None:
    from app.services.licensing.license_service import LicenseService

    calls: list[object] = []
    original_get_info = LicenseService.get_info

    def _spy_get_info(self):
        calls.append(self)
        return original_get_info(self)

    monkeypatch.setattr(LicenseService, "get_info", _spy_get_info)

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert len(calls) == 1
