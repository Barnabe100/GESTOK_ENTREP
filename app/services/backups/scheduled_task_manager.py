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

Tâche créée pour l'utilisateur courant (``LogonType=InteractiveToken`` dans
la définition XML ci-dessous, jamais ``/ru``/``/rp``) : s'exécute dans le
contexte de la session Windows actuelle, sans jamais nécessiter d'élévation
ni d'identifiants supplémentaires stockés (§4 du mandat : « éviter les
privilèges administrateur permanents lorsque ce n'est pas nécessaire »).

Garanties réelles selon l'état du poste au moment de l'heure programmée —
jamais mélangées entre elles, chacune ayant une conséquence différente
(mission corrective « Correction et validation du module de sauvegarde sous
Windows », §4/Point 3 ; voir aussi le manuel utilisateur, chapitre
Sauvegardes) :

1. **StockManager fermé, mais une session Windows de l'utilisateur courant
   est ouverte** : le déclencheur quotidien s'exécute normalement à l'heure
   prévue (``LogonType=InteractiveToken`` autorise cette exécution sans
   qu'aucune fenêtre StockManager ne soit visible — l'agent auxiliaire tourne
   en arrière-plan, voir ``app/backup_external_agent_cli.py``).
2. **Aucune session Windows de cet utilisateur n'est ouverte à l'heure
   prévue** (ordinateur allumé mais utilisateur déconnecté/écran de
   verrouillage avant une bascule de session, ou un autre utilisateur est
   connecté) : le Planificateur de tâches Windows N'EXÉCUTE PAS une tâche
   ``InteractiveToken`` dans ce cas — comportement documenté de Windows,
   pas une limitation de ce code. ``StartWhenAvailable=true`` (voir
   :func:`_build_task_xml`) permet un rattrapage dès qu'une session de cet
   utilisateur s'ouvre à nouveau, MAIS c'est surtout le second déclencheur
   ``onlogon`` (voir :data:`SCHEDULE_ONLOGON`) qui garantit ce rattrapage de
   façon fiable et immédiate à la prochaine ouverture de session — jamais
   une attente indéfinie jusqu'à la prochaine heure programmée identique.
3. **L'ordinateur est complètement éteint à l'heure prévue** : aucune tâche
   planifiée Windows, quelle que soit sa configuration, ne peut s'exécuter
   sur un poste éteint. Le rattrapage n'a lieu qu'au redémarrage ET à
   l'ouverture de session suivante (déclencheur ``onlogon``), jamais avant —
   à documenter explicitement pour l'utilisateur (voir le manuel, qui
   détaille ce même point).

Dans les trois cas, c'est toujours ``BackupService._is_due``/
``_is_due_as_of`` (rattrapage §3.4/§3.8 de la mission corrective précédente)
qui décide si une sauvegarde est réellement due au moment où l'agent
s'exécute enfin — jamais une hypothèse de ce module sur le moment exact où
cela se produit.

Construction de la tâche via un fichier de définition XML temporaire
(``schtasks /create /xml``), jamais via l'option ``/tr`` en ligne de
commande : une valeur ``/tr`` contenant à la fois des espaces et des
guillemets (toujours le cas ici, l'exécutable étant toujours cité) est
ré-échappée par ``subprocess``/``list2cmdline`` lors du passage en liste
d'arguments à ``schtasks.exe``, produisant une valeur avec guillemets
échappés imbriqués que l'analyseur de ligne de commande de ``schtasks.exe``
ne traite pas de façon fiable (confirmé par simulation directe de
``subprocess.list2cmdline`` sur la valeur produite par l'ancienne
implémentation — échec reproductible à 100%, pas seulement sur les chemins
contenant un espace). La définition XML sépare l'exécutable
(``<Command>``) et les arguments (``<Arguments>``) en éléments XML distincts
— aucune citation de ligne de commande n'est alors nécessaire pour cette
valeur, le problème est éliminé à la racine plutôt que contourné par un
échappement différent. Le fichier XML est systématiquement encodé en
UTF-16 avec indicateur d'ordre des octets (BOM) : ``schtasks /create /xml``
exige cet encodage précis, un fichier UTF-8 pouvant être rejeté ou mal
interprété selon la version de Windows (comportement documenté de cet
outil)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.utils.exceptions import UnsupportedPlatformError
from app.utils.logging_config import get_logger
from app.utils.subprocess_windows import no_console_window_kwargs

logger = get_logger("services.backups.scheduled_task")

_TIMEOUT_SECONDS = 30
_TASK_XML_NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
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


_MAX_LOGGED_STDERR_CHARS = 2000


def _sanitized_stderr_excerpt(stderr: Optional[str]) -> str:
    """Tronque la sortie d'erreur de ``schtasks.exe`` — destinée ici À
    L'UTILISATEUR autant qu'au journal (contrairement à la convention
    équivalente de ``postgresql_backup_engine``, voir sa docstring) :
    ``schtasks.exe`` ne transmet jamais de secret dans sa sortie (aucun mot
    de passe, aucun identifiant — cette tâche est toujours créée pour
    l'utilisateur courant, jamais via ``/rp``), ses messages sont de courtes
    phrases explicites (ex. « ERROR: Le nom de fichier, de répertoire ou de
    volume est incorrect. ») directement utiles à l'utilisateur pour
    diagnostiquer la cause réelle d'un échec — jamais le seul code retour
    numérique."""
    text = (stderr or "").strip()
    if not text:
        return "(aucune sortie d'erreur disponible)"
    if len(text) > _MAX_LOGGED_STDERR_CHARS:
        return text[:_MAX_LOGGED_STDERR_CHARS] + " […tronqué…]"
    return text


def _build_task_xml(executable: str, arguments: list[str], *, schedule: str, time_of_day: str) -> bytes:
    """Construit une définition de tâche Planificateur Windows au format
    XML (``schtasks /create /xml``), encodée en UTF-16 avec BOM (exigée par
    cet outil — voir la docstring de module). Jamais de citation de ligne de
    commande : ``executable``/``arguments`` sont placés dans des éléments
    XML distincts (``<Command>``/``<Arguments>``), échappés automatiquement
    par :mod:`xml.etree.ElementTree` selon les règles XML (``&``/``<``/``>``)
    — jamais une concaténation en une seule chaîne qui nécessiterait des
    guillemets imbriqués (voir la docstring de module pour le défaut que
    cela corrige). Pure, testable sans Windows (ne fait qu'assembler du
    texte — aucun appel à ``schtasks.exe`` ici)."""
    ET.register_namespace("", _TASK_XML_NS)
    root = ET.Element(f"{{{_TASK_XML_NS}}}Task", attrib={"version": "1.2"})

    principals = ET.SubElement(root, f"{{{_TASK_XML_NS}}}Principals")
    principal = ET.SubElement(principals, f"{{{_TASK_XML_NS}}}Principal", attrib={"id": "Author"})
    # ``InteractiveToken`` : la tâche s'exécute avec le jeton de la session
    # Windows interactive de l'utilisateur courant — jamais stockée nulle
    # part, jamais ``/ru``/``/rp`` (voir la docstring de module, les trois
    # garanties réelles selon l'état du poste). ``LeastPrivilege`` : jamais
    # d'élévation, cohérent avec le reste du mandat.
    ET.SubElement(principal, f"{{{_TASK_XML_NS}}}LogonType").text = "InteractiveToken"
    ET.SubElement(principal, f"{{{_TASK_XML_NS}}}RunLevel").text = "LeastPrivilege"

    settings = ET.SubElement(root, f"{{{_TASK_XML_NS}}}Settings")
    ET.SubElement(settings, f"{{{_TASK_XML_NS}}}Enabled").text = "true"
    # Rattrapage complémentaire au déclencheur ``onlogon`` (mission
    # corrective précédente, §3.5) : si l'heure programmée a été manquée
    # (poste éteint, ou session pas encore ouverte), Windows lance la tâche
    # dès que les conditions redeviennent réunies plutôt que d'attendre la
    # prochaine échéance identique — jamais un remplacement du déclencheur
    # ``onlogon`` dédié, un mécanisme de plus, jamais de moins.
    ET.SubElement(settings, f"{{{_TASK_XML_NS}}}StartWhenAvailable").text = "true"
    # Une sauvegarde ne doit jamais être silencieusement sautée sur un
    # poste portable simplement parce qu'il fonctionne sur batterie à
    # l'heure programmée — contrairement au réglage par défaut proposé par
    # l'interface graphique du Planificateur de tâches.
    ET.SubElement(settings, f"{{{_TASK_XML_NS}}}DisallowStartIfOnBatteries").text = "false"
    ET.SubElement(settings, f"{{{_TASK_XML_NS}}}StopIfGoingOnBatteries").text = "false"
    # Jamais une seconde exécution superposée côté Planificateur lui-même —
    # défense en profondeur complémentaire au verrou partagé applicatif
    # (``app.utils.process_lock``, §3.7 de la mission corrective
    # précédente), jamais un remplacement de celui-ci.
    ET.SubElement(settings, f"{{{_TASK_XML_NS}}}MultipleInstancesPolicy").text = "IgnoreNew"

    triggers = ET.SubElement(root, f"{{{_TASK_XML_NS}}}Triggers")
    if schedule == SCHEDULE_ONLOGON:
        trigger = ET.SubElement(triggers, f"{{{_TASK_XML_NS}}}LogonTrigger")
        ET.SubElement(trigger, f"{{{_TASK_XML_NS}}}Enabled").text = "true"
    else:
        _validate_time_of_day(time_of_day)
        trigger = ET.SubElement(triggers, f"{{{_TASK_XML_NS}}}CalendarTrigger")
        # Date arbitraire dans le passé (jamais significative en elle-même,
        # seule l'heure l'est) : une ``CalendarTrigger`` quotidienne exige
        # malgré tout une ``StartBoundary`` complète (date + heure) — la
        # répétition quotidienne vient de ``ScheduleByDay``/``DaysInterval``
        # ci-dessous, jamais de cette date de départ.
        ET.SubElement(trigger, f"{{{_TASK_XML_NS}}}StartBoundary").text = f"2024-01-01T{time_of_day}:00"
        ET.SubElement(trigger, f"{{{_TASK_XML_NS}}}Enabled").text = "true"
        schedule_by_day = ET.SubElement(trigger, f"{{{_TASK_XML_NS}}}ScheduleByDay")
        ET.SubElement(schedule_by_day, f"{{{_TASK_XML_NS}}}DaysInterval").text = "1"

    actions = ET.SubElement(root, f"{{{_TASK_XML_NS}}}Actions", attrib={"Context": "Author"})
    exec_action = ET.SubElement(actions, f"{{{_TASK_XML_NS}}}Exec")
    ET.SubElement(exec_action, f"{{{_TASK_XML_NS}}}Command").text = executable
    if arguments:
        ET.SubElement(exec_action, f"{{{_TASK_XML_NS}}}Arguments").text = " ".join(arguments)

    return ET.tostring(root, encoding="utf-16", xml_declaration=True)


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
    xml_bytes = _build_task_xml(executable, arguments, schedule=schedule, time_of_day=time_of_day)
    schedule_description = "à l'ouverture de session" if schedule == SCHEDULE_ONLOGON else f"quotidienne, {time_of_day}"

    fd, tmp_path_str = tempfile.mkstemp(prefix=".stockmanager_task_", suffix=".xml")
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(xml_bytes)
        result = _run_schtasks(["/create", "/tn", task_name, "/xml", str(tmp_path), "/f"])
    finally:
        tmp_path.unlink(missing_ok=True)

    if result.returncode != 0:
        stderr_excerpt = _sanitized_stderr_excerpt(result.stderr)
        logger.error("Échec de création de la tâche planifiée %r : %s", task_name, stderr_excerpt)
        raise ScheduledTaskError(
            f"La création de la tâche planifiée Windows « {task_name} » a échoué (code "
            f"{result.returncode}). Détail Windows : {stderr_excerpt}"
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
        stderr_excerpt = _sanitized_stderr_excerpt(result.stderr)
        logger.error("Échec de suppression de la tâche planifiée %r : %s", task_name, stderr_excerpt)
        raise ScheduledTaskError(
            f"La suppression de la tâche planifiée Windows « {task_name} » a échoué (code "
            f"{result.returncode}). Détail Windows : {stderr_excerpt}"
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
