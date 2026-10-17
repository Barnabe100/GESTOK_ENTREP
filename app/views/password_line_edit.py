"""Champ de saisie de mot de passe réutilisable, avec bouton intégré
« afficher/masquer » (Lot visibilité des mots de passe).

Sous-classe directe de ``QLineEdit`` (plutôt qu'un widget composite comme
:class:`app.views.optional_date_edit.OptionalDateEdit`) : tous les appelants
existants n'utilisent que l'API native de ``QLineEdit`` (``text()``,
``clear()``, ``setPlaceholderText()``, le signal ``returnPressed``) — en
sous-classant directement, ``PasswordLineEdit`` est un remplacement direct
de ``QLineEdit(parent)`` sans aucune adaptation de cette API ailleurs.

Masquage automatique uniquement à la fermeture du widget (``hideEvent``,
déclenché quand le dialogue parent se ferme via ``accept()``/``reject()``/
``close()``) — jamais sur un simple changement de focus : aucun
``focusOutEvent`` n'est surchargé ici, pour ne pas remasquer le mot de
passe simplement parce que l'utilisateur a cliqué ailleurs dans la fenêtre
pendant qu'il le relit.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QStyle, QToolButton, QWidget


class PasswordLineEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)

        self._toggle_button = QToolButton(self)
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.setStyleSheet("QToolButton { border: none; padding: 0 4px; }")
        self._toggle_button.setCheckable(True)
        self._toggle_button.setText("\U0001F441")  # 👁 — pas d'icône externe, aucune dépendance d'asset.
        self._toggle_button.setToolTip("Afficher le mot de passe")
        self._toggle_button.toggled.connect(self._on_toggled)

        self.setTextMargins(0, 0, 28, 0)

    def _on_toggled(self, visible: bool) -> None:
        self.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        self._toggle_button.setToolTip("Masquer le mot de passe" if visible else "Afficher le mot de passe")

    def is_password_visible(self) -> bool:
        return self._toggle_button.isChecked()

    def resizeEvent(self, event) -> None:  # noqa: N802 (nom imposé par Qt)
        super().resizeEvent(event)
        size = self._toggle_button.sizeHint()
        frame_width = self.style().pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth)
        self._toggle_button.move(
            self.rect().right() - size.width() - frame_width - 2,
            (self.rect().height() - size.height()) // 2,
        )

    def hideEvent(self, event) -> None:  # noqa: N802 (nom imposé par Qt)
        if self._toggle_button.isChecked():
            self._toggle_button.setChecked(False)
        super().hideEvent(event)
