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


def test_shows_publisher(qtbot, login_as) -> None:
    from PySide6.QtWidgets import QLabel

    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    all_text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "StockManager" in all_text


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
