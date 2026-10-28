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
documentée et le choix délibéré de ne pas la threader).

Correctif revue finale — défaut critique de cycle de vie : détruire un
``QThread`` encore actif est un arrêt brutal (``QThread: Destroyed while
thread is still running``, abandon du processus — reproduit et confirmé
lors de la revue de ce lot en fermant/en déconnectant pendant une
sauvegarde ou une restauration). La protection principale est côté
appelant (``MainWindow``/``BackupsPage`` refusent toute fermeture tant
qu'une opération est en cours — voir ``BackupsPage.has_active_background_task``
et ``MainWindow._on_logout_clicked``/``closeEvent``) : ce module ne peut
pas, lui, empêcher qu'on détruise la page qui le possède. Il ajoute
cependant une seconde protection, indépendante de la discipline de
l'appelant : chaque instance démarrée s'enregistre dans
:data:`_ACTIVE_TASKS` (un registre au niveau du module, jamais une
référence circulaire — l'instance ne référence jamais ce registre en
retour) tant qu'elle n'a pas reçu ``finished``/``failed`` ; même si
l'objet qui l'a créée (ex. ``BackupsPage``) disparaissait malgré tout, le
``QThread`` resterait référencé et donc vivant jusqu'à sa fin réelle,
jamais détruit en cours d'exécution. ``on_success``/``on_failure`` restent
néanmoins des fermetures sur l'appelant d'origine : si ce dernier a été
détruit entre-temps (ce que la protection principale ci-dessus doit
rendre impossible en pratique), l'appel est entouré d'un filet de
sécurité qui journalise l'incident sans jamais faire planter le
processus — voir :meth:`_invoke`."""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

from app.utils.logging_config import get_logger

logger = get_logger("views.background_task")

# Garde les instances en cours vivantes indépendamment de toute référence
# détenue par leur appelant (voir la docstring de module) — jamais une
# référence circulaire : BackgroundTask ne connaît pas ce registre.
_ACTIVE_TASKS: set["BackgroundTask"] = set()


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
        # Enregistré avant de démarrer le thread (jamais après : le signal
        # de fin pourrait théoriquement être traité avant que l'ajout au
        # registre ne soit visible) — voir la docstring de module.
        _ACTIVE_TASKS.add(self)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread.isRunning()

    def _on_finished(self, result: Any) -> None:
        self._cleanup()
        self._invoke(self._on_success, result)

    def _on_failed(self, exc: Exception) -> None:
        self._cleanup()
        self._invoke(self._on_failure, exc)

    def _invoke(self, callback: Optional[Callable[[Any], None]], value: Any) -> None:
        """Filet de sécurité (voir la docstring de module) : si l'objet
        appelant d'origine a malgré tout été détruit entre le démarrage de
        cette tâche et sa fin, ``callback`` (une méthode liée à cet objet,
        ex. ``self._finish_backup_task``) lève ``RuntimeError`` dès son
        premier accès à un widget Qt détruit — jamais un arrêt brutal du
        processus pour autant, seulement cette conséquence journalisée.
        Ne doit normalement jamais se produire : c'est la protection
        principale (``MainWindow``/``BackupsPage`` refusent toute
        fermeture tant qu'une opération est en cours) qui empêche cette
        situation en amont."""
        if callback is None:
            return
        try:
            callback(value)
        except RuntimeError as exc:
            logger.warning(
                "Résultat d'une opération d'arrière-plan ignoré : l'objet appelant d'origine "
                "semble avoir été détruit entre-temps (%s).", exc,
            )

    def _cleanup(self) -> None:
        self._thread.quit()
        self._thread.wait()
        _ACTIVE_TASKS.discard(self)
