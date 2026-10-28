"""Détection d'inactivité pour la déconnexion automatique (phase accès
réseau/déconnexion auto/permissions Consultant, point 2).

Posé comme ``eventFilter`` sur ``QApplication.instance()`` — jamais sur un
widget précis : c'est le seul mécanisme qui capte aussi les évènements des
fenêtres secondaires et boîtes de dialogue modales (``QDialog.exec()``
garde la boucle d'évènements de l'application active pendant toute sa
durée), condition explicite du mandat (« gérer correctement les fenêtres
de dialogue et les interactions avec les fenêtres secondaires »). Un
filtre posé sur un seul widget manquerait tout évènement reçu par un
``QDialog`` ouvert en modal.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer, Signal

# Délai par défaut avant déconnexion automatique, en minutes — valeur
# demandée par le mandat (5-10 minutes, défaut 10), modifiable uniquement
# en code (aucune exigence de configuration utilisateur dans ce lot).
DEFAULT_INACTIVITY_TIMEOUT_MINUTES = 10

# Clic, frappe clavier ou molette : suffisant pour détecter une interaction
# réelle. Volontairement pas ``MouseMove`` (déclenché en continu au moindre
# survol, sans rapport avec une interaction effective, et coûteux à traiter
# à chaque évènement de l'application entière).
_ACTIVITY_EVENT_TYPES = frozenset(
    {QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress, QEvent.Type.Wheel}
)


class InactivityMonitor(QObject):
    """Émet :attr:`timed_out` lorsqu'aucune activité utilisateur (clic,
    touche, molette, y compris dans une boîte de dialogue modale) n'a été
    captée pendant ``timeout_minutes`` minutes. Ne se redéclenche jamais
    après :meth:`stop` — c'est à l'appelant de retirer ce filtre
    d'évènements (``QApplication.instance().removeEventFilter(...)``) et
    d'appeler :meth:`stop` à la déconnexion/fermeture, pour qu'aucun
    déclenchement tardif ne puisse plus jamais se produire."""

    timed_out = Signal()

    def __init__(
        self, timeout_minutes: int = DEFAULT_INACTIVITY_TIMEOUT_MINUTES, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(timeout_minutes * 60_000)
        self._timer.timeout.connect(self.timed_out.emit)

    def start(self) -> None:
        """Démarre — ou réarme depuis zéro, si déjà démarré — le délai
        avant déconnexion. Utilisé aussi bien pour l'armement initial que
        pour reporter l'échéance (ex. une opération d'arrière-plan
        protégée est en cours au moment du déclenchement, voir
        ``MainWindow._perform_logout``)."""
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - signature imposée par Qt
        if event.type() in _ACTIVITY_EVENT_TYPES:
            self._timer.start()
        return False  # ne consomme jamais l'évènement : simple observateur
