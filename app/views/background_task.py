"""Exécution d'une opération potentiellement longue hors du thread
graphique Qt (phase amélioration UX, point 3 — correctif suite à la revue
finale : le spinner de ``LoadingOverlay`` ne peut s'animer que si la
boucle d'évènements Qt continue de tourner ; un simple
``QApplication.processEvents()`` appelé une fois avant un appel bloquant
ne peint qu'une image figée pendant toute sa durée).

Réservé aux opérations qui ne construisent, ne modifient et n'affichent
**jamais** de widget Qt (``QMessageBox`` inclus) depuis le thread
d'arrière-plan — l'appelant doit faire tout l'affichage dans
``on_success``/``on_failure`` (exécutés sur le thread appelant, voir plus
bas), jamais dans ``func`` lui-même.

Accès SQLAlchemy depuis ``func`` : autorisé **uniquement** si ``func``
ouvre et referme sa propre session de façon autonome (ex. via
``app.db.session.session_scope``, qui crée une ``Session`` dédiée à
l'appel et la ferme avant de retourner) et ne renvoie jamais un objet
mappé ORM encore attaché à cette session — seulement des types simples ou
des structures détachées (ex. ``BackupResult``/``RestoreResult``,
dataclasses). Ceci n'est pas une exception au principe « ne jamais
déplacer arbitrairement une session existante dans un thread » : aucune
session n'est partagée entre threads ici, chaque appel crée et détruit la
sienne, exactement comme le ferait n'importe quel appel au même service
depuis le thread graphique. Ce n'est possible que parce que :

- le moteur SQLite de ce projet est explicitement créé avec
  ``connect_args={"check_same_thread": False}`` (voir
  ``app.db.session.create_db_engine``) — l'accès multi-thread au moteur
  est donc une configuration délibérée, pas un contournement ;
- le moteur PostgreSQL (``sqlalchemy.create_engine`` avec son pool de
  connexions) est, par construction, nativement conçu pour être partagé
  entre threads, chaque thread se voyant attribuer sa propre connexion du
  pool ;
- ``app.backup_cli`` appelle déjà ces mêmes services métier hors de toute
  application Qt (tâche planifiée Windows) : ils n'ont jamais eu de
  dépendance implicite au thread graphique.

À ce jour, utilisé par ``BackupsPage`` pour
``BackupService.create_manual_backup``/``restore_backup`` (l'opération la
plus longue de l'application — ``pg_dump``/``pg_restore`` sur une base
volumineuse peut prendre plusieurs minutes). Volontairement **pas**
utilisé pour la construction de ``MainWindow`` (qui doit créer des
``QWidget``, impossible hors du thread graphique) ni pour la génération de
rapports (voir la docstring de ``ReportsPage.refresh`` pour la limite
documentée et le choix délibéré de ne pas la threader)."""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal


class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(Exception)

    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self._func = func

    def run(self) -> None:
        try:
            result = self._func()
        except Exception as exc:  # noqa: BLE001 - toute exception doit remonter, jamais être avalée.
            self.failed.emit(exc)
        else:
            self.finished.emit(result)


class BackgroundTask(QObject):
    """Une instance par opération — jamais réutilisée pour une seconde
    exécution (créer une nouvelle instance à chaque appel de
    :meth:`start`), pour ne jamais mélanger l'état de deux opérations.

    Le callable fourni (``func``) s'exécute entièrement dans un
    ``QThread`` dédié ; son résultat ou son exception est remis sur le
    thread **appelant** (celui qui construit ``BackgroundTask``, toujours
    le thread graphique en pratique) via les signaux Qt usuels — une
    connexion entre threads différents est automatiquement mise en file
    (``Qt.ConnectionType.AutoConnection``), jamais un callback invoqué
    directement depuis le thread d'arrière-plan."""

    def __init__(self, func: Callable[[], Any], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _Worker(func)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._on_success: Optional[Callable[[Any], None]] = None
        self._on_failure: Optional[Callable[[Exception], None]] = None

    def start(
        self, on_success: Callable[[Any], None], on_failure: Callable[[Exception], None]
    ) -> None:
        """Démarre l'exécution — ``on_success``/``on_failure`` sont appelés
        exactement une fois, sur le thread appelant, jamais les deux pour
        la même exécution. C'est à ces deux callbacks, jamais à ``func``,
        de construire ou d'afficher le moindre widget Qt."""
        self._on_success = on_success
        self._on_failure = on_failure
        self._thread.start()

    def _on_finished(self, result: Any) -> None:
        self._cleanup()
        if self._on_success is not None:
            self._on_success(result)

    def _on_failed(self, exc: Exception) -> None:
        self._cleanup()
        if self._on_failure is not None:
            self._on_failure(exc)

    def _cleanup(self) -> None:
        self._thread.quit()
        self._thread.wait()
