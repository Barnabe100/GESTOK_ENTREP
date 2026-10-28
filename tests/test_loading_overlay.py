"""Tests de ``app.views.loading_overlay.LoadingOverlay`` (phase amélioration
UX, point 3)."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.views.loading_overlay import LoadingOverlay


def test_overlay_is_hidden_by_default(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    overlay = LoadingOverlay(parent)

    assert overlay.is_visible() is False


def test_show_with_message_displays_the_overlay_and_the_message(qtbot) -> None:
    parent = QWidget()
    parent.resize(300, 200)
    qtbot.addWidget(parent)
    parent.show()
    overlay = LoadingOverlay(parent)

    overlay.show_with_message("Connexion en cours…")

    assert overlay.is_visible() is True
    assert overlay._message_label.text() == "Connexion en cours…"


def test_hide_overlay_hides_it_again(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    overlay = LoadingOverlay(parent)

    overlay.show_with_message("Veuillez patienter…")
    overlay.hide_overlay()

    assert overlay.is_visible() is False


def test_overlay_resizes_to_cover_the_parent(qtbot) -> None:
    parent = QWidget()
    parent.resize(400, 300)
    qtbot.addWidget(parent)
    overlay = LoadingOverlay(parent)

    overlay.show_with_message("Chargement des données…")

    assert overlay.geometry() == parent.rect()


def test_overlay_follows_parent_resize_while_visible(qtbot) -> None:
    parent = QWidget()
    parent.resize(300, 200)
    qtbot.addWidget(parent)
    parent.show()
    overlay = LoadingOverlay(parent)
    overlay.show_with_message("Chargement…")

    parent.resize(500, 400)

    assert overlay.geometry() == parent.rect()
