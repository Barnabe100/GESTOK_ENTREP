"""Gestion de la tâche planifiée Windows pour l'agent auxiliaire de
sauvegarde (Mission « Sauvegarde automatique et restauration », §4) — créée
et administrée depuis StockManager, mais ne dépend jamais de l'application
graphique pour s'exécuter : c'est tout l'intérêt du Planificateur de
tâches Windows, qui continue d'exécuter la tâche même StockManager fermé.

Implémentation volontairement via ``schtasks.exe`` (outil système Windows
natif, invoqué en sous-processus, même convention que
``postgresql_backup_engine`` pour ``pg_dump``/``pg_restore``) plutôt que
``pywin32``/l'API COM ``ITaskService`` : aucune dépendance supplémentaire à
empaqueter, un seul exécutable déjà présent sur tout poste Windows,
suffisant pour les opérations couvertes ici (créer/interroger/supprimer une
tâche quotidienne simple).

Tâche créée pour l'utilisateur courant (aucune option ``/ru``/``/rp``) :
s'exécute dans le contexte de la session Windows actuelle, sans jamais
nécessiter d'élévation ni d'identifiants supplémentaires stockés —
limitation documentée et assumée (§4 du mandat : « éviter les privilèges
administrateur permanents lorsque ce n'est pas nécessaire ») : la tâche ne
s'exécute que si une session Windows de cet utilisateur existe au moment
prévu (même limitation que tout programme planifié non-service), jamais
lorsque l'ordinateur est complètement éteint ou l'utilisateur déconnecté —
à documenter explicitement pour l'utilisateur (voir la documentation de
cette mission).
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from app.utils.exceptions import UnsupportedPlatformError
from app.utils.logging_config import get_logger
from app.utils.subprocess_windows import no_console_window_kwargs

logger = get_logger("services.backups.scheduled_task")

_TIMEOUT_SECONDS = 30
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Mappe les libellés de ``schtasks /query ... /fo list /v`` (anglais,
# indépendant de la langue d'affichage Windows — confirmé par la
# documentation Microsoft : ces clés restent en anglais quelle que soit la
# langue du système) vers les champs de :class:`ScheduledTaskStatus`.
_FIELD_MAP = {
    "status": "status",
    "last run time": "last_run_time",
    "last result": "last_result",
    "next run time": "next_run_time",
}


class ScheduledTaskError(Exception):
    """Échec d'une opération sur la tâche planifiée — message
    volontairement générique côté utilisateur ; les détails techniques
    complets (``stderr``) sont journalisés séparément (même convention que
    ``PostgreSQLBackupError``)."""


def _ensure_windows() -> None:
    if sys.platform != "win32":
        raise UnsupportedPlatformError(
            "La gestion de la tâche planifiée Windows n'est prise en charge que sous Windows."
        )


def _validate_time_of_day(time_of_day: str) -> None:
    """Pure, testable sans Windows — isolée de ``create_or_repair_task``
    pour que sa logique de validation soit vérifiée indépendamment de
    ``schtasks.exe`` lui-même (voir §8 du mandat : séparer unitaire et
    intégration réellement Windows)."""
    if not _TIME_RE.match(time_of_day):
        raise ScheduledTaskError(f"Heure invalide : « {time_of_day} » (format attendu HH:MM, 00-23:00-59).")


def _build_task_run_value(executable: str, arguments: list[str]) -> str:
    """Construit la valeur ``/tr`` (ligne de commande exécutée par la
    tâche) — l'exécutable est toujours entre guillemets (chemin pouvant
    contenir des espaces, ex. ``Program Files``), jamais les arguments
    (simples indicateurs sans espace dans cet usage, voir
    ``backup_external_agent_cli.py``). Pure, testable sans Windows."""
    return " ".join([f'"{executable}"', *arguments])


def _parse_schtasks_verbose_list(output: str) -> dict[str, str]:
    """Analyse la sortie de ``schtasks /query ... /fo list /v`` (paires
    ``Clé:   Valeur``, une par ligne) — pure, testable sans Windows à
    partir d'un exemple de sortie figé. Ignore silencieusement toute ligne
    sans correspondance connue (``_FIELD_MAP``) : une sortie plus riche
    qu'attendu (version Windows différente) ne doit jamais faire échouer
    l'analyse, seulement ignorer les champs non reconnus ici."""
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        attr = _FIELD_MAP.get(key.strip().lower())
        if attr is not None:
            fields[attr] = value.strip()
    return fields


def _run_schtasks(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["schtasks", *args], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
            check=False, **no_console_window_kwargs(),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ScheduledTaskError(f"Impossible d'exécuter schtasks.exe : {exc}") from exc


def task_exists(task_name: str) -> bool:
    """Intégration réelle Windows — voir
    ``tests/test_scheduled_task_manager_windows_integration.py``, exécutée
    uniquement sous Windows."""
    _ensure_windows()
    result = _run_schtasks(["/query", "/tn", task_name])
    return result.returncode == 0


SCHEDULE_DAILY = "daily"
SCHEDULE_ONLOGON = "onlogon"


def create_or_repair_task(
    task_name: str, executable: str, arguments: list[str], time_of_day: str, *, schedule: str = SCHEDULE_DAILY,
) -> None:
    """Crée la tâche si absente, ou la recrée à l'identique si déjà
    présente (``/f``, « force ») — un seul chemin de code pour la création
    ET la réparation d'une tâche supprimée ou endommagée manuellement (§4
    du mandat), jamais deux mécanismes distincts à maintenir en parallèle.

    ``schedule="daily"`` (défaut, comportement historique) : déclenchement
    quotidien à l'heure exacte ``time_of_day``. ``schedule="onlogon"``
    (mission corrective, §3.5) : déclenchement à chaque ouverture de
    session de l'utilisateur courant — ``time_of_day`` est alors ignoré
    (jamais validé ni transmis, ``schtasks`` ne l'accepte pas pour ce type
    de déclencheur) ; sert exclusivement de rattrapage (voir
    ``ExternalBackupService.configure_scheduled_task`` et §3.4/§3.6 du
    mandat correctif) en complément de la tâche quotidienne, jamais à sa
    place."""
    _ensure_windows()
    tr_value = _build_task_run_value(executable, arguments)

    if schedule == SCHEDULE_ONLOGON:
        args = ["/create", "/tn", task_name, "/tr", tr_value, "/sc", "onlogon", "/f"]
        schedule_description = "à l'ouverture de session"
    else:
        _validate_time_of_day(time_of_day)
        args = ["/create", "/tn", task_name, "/tr", tr_value, "/sc", "daily", "/st", time_of_day, "/f"]
        schedule_description = f"quotidienne, {time_of_day}"

    result = _run_schtasks(args)
    if result.returncode != 0:
        logger.error(
            "Échec de création de la tâche planifiée %r : %s", task_name, (result.stderr or "").strip()
        )
        raise ScheduledTaskError(
            f"La création de la tâche planifiée Windows a échoué (code {result.returncode})."
        )
    logger.info("Tâche planifiée %r créée/réparée (%s).", task_name, schedule_description)


def delete_task(task_name: str) -> None:
    """Supprime la tâche si présente — idempotent : déjà absente est
    considéré comme un succès, jamais une erreur pour un état déjà
    atteint."""
    _ensure_windows()
    if not task_exists(task_name):
        return
    result = _run_schtasks(["/delete", "/tn", task_name, "/f"])
    if result.returncode != 0:
        logger.error(
            "Échec de suppression de la tâche planifiée %r : %s", task_name, (result.stderr or "").strip()
        )
        raise ScheduledTaskError(
            f"La suppression de la tâche planifiée Windows a échoué (code {result.returncode})."
        )
    logger.info("Tâche planifiée %r supprimée.", task_name)


@dataclass(frozen=True)
class ScheduledTaskStatus:
    """État de la tâche planifiée tel que rapporté par
    ``schtasks /query`` — ``None`` pour un champ non trouvé dans la sortie
    (tâche jamais encore exécutée : ``last_run_time``/``last_result``
    absents, jamais une valeur devinée)."""

    exists: bool
    status: Optional[str] = None  # "Ready" | "Running" | "Disabled" | ...
    last_run_time: Optional[str] = None
    last_result: Optional[str] = None
    next_run_time: Optional[str] = None


def query_task_status(task_name: str) -> ScheduledTaskStatus:
    _ensure_windows()
    result = _run_schtasks(["/query", "/tn", task_name, "/fo", "list", "/v"])
    if result.returncode != 0:
        return ScheduledTaskStatus(exists=False)
    fields = _parse_schtasks_verbose_list(result.stdout or "")
    return ScheduledTaskStatus(exists=True, **fields)
