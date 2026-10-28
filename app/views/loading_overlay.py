"""Indicateur de chargement réutilisable (spinner animé + message explicite)
— phase amélioration UX, point 3.

Un seul composant pour tout l'écran concerné : superposé au widget parent
(jamais une fenêtre séparée), il bloque les clics sur tout ce qu'il
recouvre pendant qu'il est visible — ceci empêche les doubles-soumissions
sans qu'aucun appelant n'ait à désactiver chaque bouton individuellement
(un appelant peut en plus désactiver explicitement son propre bouton, les
deux protections sont complémentaires, voir ``BackupsPage``).

Ne masque jamais une erreur : :meth:`LoadingOverlay.hide_overlay` doit être
appelé dans tous les cas (succès ou échec) avant d'afficher le message
d'erreur à l'utilisateur — c'est à l'appelant de décider du message, ce
composant ne fait que montrer/cacher le spinner et un texte."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget


class _Spinner(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    def start(self) -> None:
        self._angle = 0
        self._timer.start(60)

    def stop(self) -> None:
        self._timer.stop()

    def _advance(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - signature imposée par Qt.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(Qt.GlobalColor.darkGray)
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = self.rect().adjusted(6, 6, -6, -6)
        painter.drawArc(rect, self._angle * 16, 270 * 16)


class LoadingOverlay(QWidget):
    """À créer une fois par écran (ou par fenêtre), avec cet écran comme
    parent — se redimensionne automatiquement pour le recouvrir entièrement
    et reste caché jusqu'au premier appel de :meth:`show_with_message`."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(255, 255, 255, 220);")
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._spinner = _Spinner(self)
        layout.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._message_label = QLabel("", self)
        self._message_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._message_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        layout.addWidget(self._message_label)

        parent.installEventFilter(self)

    def show_with_message(self, message: str) -> None:
        """Affiche le voile, le spinner animé et ``message`` — bloque les
        clics sur le widget parent pendant que le voile est visible
        (widget plein écran au-dessus de tout le reste, ``raise_()``)."""
        self._message_label.setText(message)
        self._resize_to_parent()
        self._spinner.start()
        self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        """À appeler systématiquement une fois l'opération terminée, que
        ce soit un succès ou un échec, avant d'afficher le résultat."""
        self._spinner.stop()
        self.hide()

    def is_visible(self) -> bool:
        return self.isVisible()

    def _resize_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())

    def eventFilter(self, watched, event):  # noqa: N802 - signature imposée par Qt.
        if watched is self.parentWidget() and event.type() == event.Type.Resize:
            self._resize_to_parent()
        return super().eventFilter(watched, event)


class StartupSplash(QDialog):
    """Fenêtre indépendante, sans parent, affichée entre la fermeture de la
    fenêtre de connexion et l'affichage de la fenêtre principale (voir
    ``app/main.py:run_session``) : aucun widget visible n'existe alors sur
    lequel superposer un :class:`LoadingOverlay` classique, d'où cette
    petite fenêtre autonome avec le même spinner."""

    def __init__(self, message: str) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(False)
        self.setFixedSize(280, 140)

        layout = QVBoxLayout(self)
        self._spinner = _Spinner(self)
        layout.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignHCenter)

        label = QLabel(message, self)
        label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        label.setStyleSheet("font-weight: 600;")
        layout.addWidget(label)

        self._spinner.start()

    def closeEvent(self, event) -> None:  # noqa: N802 - signature imposée par Qt.
        self._spinner.stop()
        super().closeEvent(event)
