"""Mécanique pure des sauvegardes/restaurations PostgreSQL : création,
vérification, restauration — pendant symétrique de
:mod:`app.services.backups.backup_engine` (SQLite), réutilisé à l'identique
par :class:`~app.services.backups.backup_service.BackupService`.

Méthode retenue (Lot E, §E.2.1) : les outils officiels PostgreSQL
``pg_dump``/``pg_restore`` (format personnalisé ``-Fc``), invoqués comme
processus externes — jamais réimplémentés, jamais une bibliothèque Python
tierce de dump/restore. Ces outils ne sont **jamais embarqués** dans
l'application : leur présence sur le poste (généralement installés avec le
client PostgreSQL, ou récupérables séparément auprès de postgresql.org)
est un prérequis documenté (voir ``docs/postgresql-configuration.md``),
vérifié explicitement (:func:`ensure_tools_available`) plutôt que supposé —
jamais d'échec confus si l'un des deux manque. Conséquences acceptées de ce
choix (détaillées dans le rapport de phase) : pas de dépendance de licence
ou de maintenance supplémentaire pour StockManager, mais une installation
cliente doit disposer de ces outils pour utiliser la sauvegarde/restauration
PostgreSQL (le mode SQLite, par défaut, n'en a jamais besoin).

Correctif (incident « détection pg_dump/pg_restore introuvables sous
Windows ») : la détection se limitait jusqu'ici au ``PATH`` du processus
(``shutil.which``) — or l'installeur officiel PostgreSQL pour Windows
n'ajoute pas toujours « ...PostgreSQL/<version>/bin » au ``PATH`` (selon
les options choisies à l'installation, ou le contexte d'exécution du
service), même quand les deux exécutables sont réellement présents et
utilisables à cet emplacement standard. :func:`_locate_tool` cherche
désormais, uniquement sous Windows et seulement si le ``PATH`` échoue,
dans tous les répertoires ``bin`` standards de toutes les versions
installées (jamais une seule version codée en dur, voir
:func:`_windows_pg_bin_candidates` — triés version décroissante en
l'absence de tout autre indice disponible côté client) ; le chemin ainsi
résolu (et non plus le seul nom nu de la commande) est celui réellement
transmis à chaque appel de sous-processus, afin qu'un outil trouvé hors du
``PATH`` soit aussi celui qui s'exécute, pas seulement celui dont la
présence est signalée.

Limite documentée, délibérée (Lot E.7, §E.7.3) : ce module ne tente
**jamais** de déterminer par avance si la version locale de
``pg_dump``/``pg_restore`` est compatible avec le serveur ou avec une
archive donnée — une telle détection côté client serait nécessairement
fragile (format des messages d'erreur PostgreSQL non garanti stable
entre versions, matrice de compatibilité qui évolue). PostgreSQL
détecte et signale déjà lui-même une incompatibilité réelle (message
d'erreur explicite, ex. « server version mismatch », « unsupported
version … in file header ») ; ce message est désormais journalisé (voir
:func:`_log_subprocess_failure`), avec la version locale de l'outil pour
en faciliter le diagnostic — jamais une garantie de compatibilité, jamais
un blocage préalable à la tentative elle-même.

Le mot de passe n'est **jamais** passé en argument de ligne de commande
(visible via la liste des processus du système) ni journalisé : il est
fourni au seul sous-processus concerné via la variable d'environnement
``PGPASSWORD`` d'un dictionnaire d'environnement dédié (jamais une mutation
de ``os.environ`` du processus courant). ``--no-password`` interdit tout
retour silencieux vers une invite interactive qui bloquerait indéfiniment.

Diagnostic (Lot E.7, §E.7.1) : la sortie d'erreur (``stderr``) de
``pg_dump``/``pg_restore`` est journalisée (``logger.error``, jamais
affichée à l'utilisateur) à chaque échec — tronquée à une longueur
raisonnable par prudence, jamais le mot de passe ni aucune variable
d'environnement, qui n'y figurent de toute façon jamais (voir
ci-dessus : ``PGPASSWORD`` n'est transmis que par l'environnement du
sous-processus, jamais en argument ni par une invite interactive dont la
sortie serait capturée). Le message remonté à l'appelant (donc
potentiellement à l'utilisateur) reste volontairement générique, sans
aucun détail technique brut — voir :class:`PostgreSQLBackupError`.

Restauration (§E.2.3) : ``--single-transaction`` fait exécuter l'ensemble
du script de restauration (y compris les ``DROP``/``CREATE`` de
``--clean --if-exists``) dans une seule transaction SQL — tout échec en
cours d'opération annule l'intégralité de la transaction côté serveur,
jamais un état partiellement restauré. ``--no-owner --no-privileges``
évite toute modification de rôle ou de permission serveur (jamais de
création automatique de rôle, voir le mandat). La restauration cible
toujours la base déjà désignée par la configuration active — jamais une
base créée automatiquement : elle doit déjà exister, préparée par un
administrateur PostgreSQL (même invariant que pour la configuration de
connexion, voir ``app.services.database_admin``).
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models import Base
from app.services.backups.backup_engine import BackupFileInfo
from app.utils.logging_config import get_logger
from app.utils.subprocess_windows import no_console_window_kwargs

logger = get_logger("services.backups.postgresql")

BACKUP_PREFIX = "stockmanager_backup_pg"
PRERESTORE_PREFIX = "stockmanager_prerestore_pg"

# Borne de prudence (§E.7.1) : évite de journaliser une sortie d'erreur
# démesurée (ex. pg_dump/pg_restore très verbeux) — n'affecte jamais le
# message remonté à l'utilisateur, uniquement le journal applicatif.
_MAX_LOGGED_STDERR_CHARS = 4000

# Format personnalisé pg_dump (-Fc) : l'extension distingue sans ambiguïté
# une sauvegarde PostgreSQL d'un fichier ``.db`` SQLite — jamais le même
# motif de nommage pour les deux moteurs (§E.3 : ne jamais présenter l'un
# comme l'autre).
_FILENAME_RE_TEMPLATE = r"^{prefix}_\d{{8}}_\d{{6}}(?:_\d+)?\.dump$"

# Bornes larges mais finies : un pg_dump/pg_restore sur une base volumineuse
# peut prendre plusieurs minutes — jamais une boucle d'attente infinie pour
# autant (§E.1 du mandat global : éviter les attentes non bornées).
DEFAULT_DUMP_RESTORE_TIMEOUT_SECONDS = 1800
DEFAULT_PROBE_TIMEOUT_SECONDS = 10


class PostgreSQLToolNotFoundError(Exception):
    """``pg_dump``/``pg_restore`` introuvables sur ce poste — jamais
    supposés présents (§E.2.1 du mandat) : message explicite plutôt qu'un
    échec confus de sous-processus."""


class PostgreSQLBackupError(Exception):
    """Échec d'une opération ``pg_dump``/``pg_restore``. Le message porté
    par cette exception (donc potentiellement affiché à l'utilisateur)
    reste volontairement générique, jamais de secret ni de sortie
    technique brute. Les détails techniques complets (``stderr``, jamais
    le mot de passe) sont journalisés séparément, **avant** la levée de
    cette exception, par :func:`_log_subprocess_failure` — jamais portés
    par l'exception elle-même."""


@dataclass(frozen=True)
class PostgreSQLTarget:
    """Paramètres de connexion non sensibles d'une base PostgreSQL cible —
    jamais le mot de passe, toujours fourni séparément à chaque appel (même
    convention que ``PostgreSQLConnectionConfig.resolve_password`` :
    jamais mis en cache, jamais stocké sur une instance)."""

    host: str
    port: int
    database: str
    username: str

    def label(self) -> str:
        """Identification compréhensible de la cible pour les messages à
        l'utilisateur (§E.2.3 : « identifier clairement la base cible ») —
        jamais le mot de passe."""
        return f"{self.host}:{self.port}/{self.database} (utilisateur « {self.username} »)"


# Emplacements Windows standards de l'installeur officiel PostgreSQL (EDB) —
# module-level pour rester substituable en test (voir
# tests/test_postgresql_backup_engine.py) sans dépendre d'un vrai système
# de fichiers Windows.
_WINDOWS_PG_BASE_DIRS: tuple[str, ...] = (
    r"C:\Program Files\PostgreSQL",
    r"C:\Program Files (x86)\PostgreSQL",
)


def _windows_pg_bin_candidates() -> list[Path]:
    """Répertoires ``bin`` standards d'installation du client PostgreSQL
    sous Windows (installeur officiel EDB), toutes versions confondues —
    jamais une seule version codée en dur (incident « détection pg_dump/
    pg_restore introuvables »). Triés version décroissante : à défaut de
    tout autre indice disponible côté client sur la version du serveur
    réellement utilisée (hors périmètre de ce module, voir la docstring),
    c'est la meilleure heuristique disponible lorsque plusieurs versions
    coexistent sur le même poste."""
    candidates: list[Path] = []
    for base in _WINDOWS_PG_BASE_DIRS:
        base_path = Path(base)
        if not base_path.is_dir():
            continue
        versions: list[tuple[float, Path]] = []
        for entry in base_path.iterdir():
            if not entry.is_dir():
                continue
            try:
                versions.append((float(entry.name), entry))
            except ValueError:
                continue  # dossier qui n'est pas un numéro de version -> ignoré.
        for _, version_dir in sorted(versions, reverse=True):
            bin_dir = version_dir / "bin"
            if bin_dir.is_dir():
                candidates.append(bin_dir)
    return candidates


def _locate_tool(tool_name: str) -> Optional[Path]:
    """Résout l'exécutable ``tool_name`` (``pg_dump``/``pg_restore``, sans
    extension) : d'abord le ``PATH`` (``shutil.which``, comportement déjà
    en place), puis — uniquement sous Windows et seulement si le ``PATH``
    n'a rien donné — les répertoires d'installation standards du client
    PostgreSQL. Retourne ``None`` si introuvable partout ; ne tente jamais
    d'exécuter l'outil ici, seulement de résoudre son chemin."""
    found = shutil.which(tool_name)
    if found:
        return Path(found)
    if platform.system() != "Windows":
        return None
    exe_name = f"{tool_name}.exe"
    for directory in _windows_pg_bin_candidates():
        candidate = directory / exe_name
        if candidate.is_file():
            return candidate
    return None


def ensure_tools_available() -> dict[str, str]:
    """Vérifie la présence de ``pg_dump`` et ``pg_restore`` sur ce poste —
    à appeler avant toute tentative de sauvegarde/restauration PostgreSQL,
    jamais supposée silencieusement (§E.2.1 du mandat). Retourne le chemin
    résolu de chaque outil (``{"pg_dump": ..., "pg_restore": ...}``) — voir
    :func:`_locate_tool` : jamais seulement le nom nu de la commande, pour
    qu'un outil trouvé hors du ``PATH`` soit bien celui effectivement
    invoqué par les fonctions ci-dessous."""
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for tool in ("pg_dump", "pg_restore"):
        path = _locate_tool(tool)
        if path is None:
            missing.append(tool)
        else:
            resolved[tool] = str(path)
    if missing:
        raise PostgreSQLToolNotFoundError(
            "Les outils PostgreSQL requis sont introuvables sur ce poste : "
            + ", ".join(missing)
            + ". Installez le client PostgreSQL (pg_dump/pg_restore) correspondant à la "
            "version du serveur avant d'utiliser la sauvegarde/restauration PostgreSQL."
        )
    return resolved


def _filename_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(_FILENAME_RE_TEMPLATE.format(prefix=re.escape(prefix)))


def generate_backup_filename(prefix: str = BACKUP_PREFIX, when: Optional[datetime] = None) -> str:
    when = when or datetime.now()
    return f"{prefix}_{when.strftime('%Y%m%d_%H%M%S')}.dump"


def _next_available_path(destination_dir: Path, filename: str) -> Path:
    candidate = destination_dir / filename
    if not candidate.exists():
        return candidate
    stem, suffix = filename[: -len(".dump")], 2
    while True:
        candidate = destination_dir / f"{stem}_{suffix}.dump"
        if not candidate.exists():
            return candidate
        suffix += 1


def _sanitized_stderr_excerpt(stderr: Optional[str]) -> str:
    """Tronque la sortie d'erreur pour la journalisation (§E.7.1) —
    jamais destinée à l'utilisateur, uniquement au journal applicatif. Le
    mot de passe n'y figure jamais (voir docstring de module : ``PGPASSWORD``
    n'est transmis que par l'environnement du sous-processus, jamais en
    argument ni par une invite interactive dont la sortie serait capturée
    ici), donc rien de plus n'est filtré que la longueur."""
    text = (stderr or "").strip()
    if not text:
        return "(aucune sortie d'erreur)"
    if len(text) > _MAX_LOGGED_STDERR_CHARS:
        return text[:_MAX_LOGGED_STDERR_CHARS] + " […tronqué…]"
    return text


def _local_tool_version(tool: str) -> str:
    """Version du client local ``pg_dump``/``pg_restore`` (``--version``,
    jamais de contact serveur, toujours rapide) — journalisée à côté de
    chaque échec (§E.7.3) pour fournir un indice de compatibilité de
    version sans que ce module ne tente lui-même de comparer/valider des
    numéros de version : voir la docstring de module pour la justification
    de cette limite délibérée (détection fiable de compatibilité non
    raisonnablement possible côté client seul — PostgreSQL ne garantit pas
    un format d'erreur stable entre versions, et les versions serveur
    supportées évoluent dans le temps)."""
    try:
        result = subprocess.run(
            [tool, "--version"], capture_output=True, text=True, timeout=5, check=False,
            **no_console_window_kwargs(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return "(version locale indisponible)"
    return (result.stdout or result.stderr or "").strip() or "(version locale indisponible)"


def _log_subprocess_failure(tool: str, returncode: Optional[int], stderr: Optional[str]) -> None:
    """Journalise les informations techniques utiles d'un échec
    ``pg_dump``/``pg_restore`` (§E.7.1 : corrige l'écart entre la docstring
    de :class:`PostgreSQLBackupError` et le comportement réel, qui ne
    journalisait jusqu'ici jamais ``stderr``). Jamais affiché à
    l'utilisateur — seul un message générique (voir les sites d'appel) lui
    est destiné.

    Inclut aussi la version locale de l'outil (§E.7.3) : une incompatibilité
    de version client/serveur ou client/archive se manifeste par un message
    d'erreur PostgreSQL déjà explicite (ex. « server version mismatch »,
    « unsupported version … in file header ») — visible dans le ``stderr``
    journalisé ci-dessous — la version locale aide seulement à corréler
    sans qu'aucune comparaison de version ne soit tentée par ce module."""
    logger.error(
        "%s a échoué (code %s) — version locale : %s. Sortie d'erreur technique "
        "(jamais le mot de passe ni aucune variable d'environnement, qui n'y "
        "figurent jamais) : %s",
        tool, returncode, _local_tool_version(tool), _sanitized_stderr_excerpt(stderr),
    )


def _run(
    args: list[str], *, password: str, timeout_seconds: int, tool_label: Optional[str] = None
) -> subprocess.CompletedProcess[str]:
    """Exécute ``pg_dump``/``pg_restore`` avec le mot de passe fourni
    uniquement via l'environnement du sous-processus (jamais en argument,
    jamais dans l'environnement du processus StockManager lui-même, jamais
    journalisé) — ``--no-password`` (déjà inclus par l'appelant) interdit
    toute invite interactive bloquante.

    ``args[0]`` peut désormais être un chemin résolu hors ``PATH`` (voir
    :func:`_locate_tool`), potentiellement long (ex. sous Windows) :
    ``tool_label`` (``"pg_dump"``/``"pg_restore"``) garde les messages
    journalisés/remontés courts et génériques, jamais ce chemin brut."""
    label = tool_label or args[0]
    env = dict(os.environ)
    env["PGPASSWORD"] = password
    try:
        return subprocess.run(
            args, env=env, capture_output=True, text=True, timeout=timeout_seconds, check=False,
            **no_console_window_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        # exc.stdout/exc.stderr peuvent porter une sortie partielle déjà
        # produite avant l'expiration du délai — journalisée pour le même
        # bénéfice diagnostique, jamais affichée à l'utilisateur.
        _log_subprocess_failure(label, None, exc.stderr if isinstance(exc.stderr, str) else None)
        raise PostgreSQLBackupError(
            f"Délai dépassé ({timeout_seconds} s) lors de l'exécution de {label}."
        ) from exc
    except OSError as exc:
        raise PostgreSQLBackupError(f"Impossible d'exécuter {label} : {exc}") from exc


def _expected_tables() -> set[str]:
    """Mêmes tables attendues que pour SQLite (voir
    ``backup_engine._expected_tables``) — dérivées du même mapping
    SQLAlchemy, jamais recopiées à la main."""
    return set(Base.metadata.tables.keys())


def create_backup_file(
    target: PostgreSQLTarget, password: str, destination_dir: Path, *,
    prefix: str = BACKUP_PREFIX, when: Optional[datetime] = None,
    timeout_seconds: int = DEFAULT_DUMP_RESTORE_TIMEOUT_SECONDS,
) -> Path:
    """Crée une sauvegarde ``pg_dump`` (format personnalisé) de ``target``
    dans ``destination_dir``. Écrit d'abord dans un fichier temporaire du
    même répertoire, ne renomme vers le nom final (``os.replace``,
    atomique) qu'après un code de retour nul ET un fichier non vide — ne
    prétend jamais un succès sur la seule existence d'un fichier (§E.2.2).
    Supprime le fichier temporaire en cas d'échec (§E.2.2 : jamais de
    fichier incomplet laissé en place)."""
    tools = ensure_tools_available()
    destination_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(dir=str(destination_dir), prefix=f".{prefix}_", suffix=".dump.tmp")
    os.close(fd)
    tmp_path = Path(tmp_path_str)
    try:
        result = _run(
            [
                tools["pg_dump"], f"--host={target.host}", f"--port={target.port}",
                f"--username={target.username}", f"--dbname={target.database}",
                "--format=custom", "--no-password", f"--file={tmp_path}",
            ],
            password=password, timeout_seconds=timeout_seconds, tool_label="pg_dump",
        )
        if result.returncode != 0:
            _log_subprocess_failure("pg_dump", result.returncode, result.stderr)
            raise PostgreSQLBackupError(
                f"pg_dump a échoué (code {result.returncode}) pour {target.label()}."
            )
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise PostgreSQLBackupError(
                f"pg_dump n'a produit aucun fichier exploitable pour {target.label()}."
            )

        final_path = _next_available_path(destination_dir, generate_backup_filename(prefix, when))
        os.replace(tmp_path, final_path)
        return final_path
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class BackupVerification:
    """Résultat de la vérification d'une archive ``pg_dump`` — même forme
    que ``backup_engine.BackupVerification`` (réutilisable sans adaptation
    par l'UI), ``integrity_ok`` signifiant ici « l'archive est structurellement
    lisible par pg_restore »."""

    valid: bool
    integrity_ok: bool
    tables_ok: bool
    alembic_version: Optional[str]
    errors: list[str] = field(default_factory=list)


_TOC_TABLE_RE = re.compile(r"^\d+;.*\bTABLE\b(?:\s+DATA)?\s+public\s+(\S+)\s", re.MULTILINE)


def verify_backup_file(
    file_path: Path, *, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS
) -> BackupVerification:
    """Vérifie qu'un fichier est une archive ``pg_dump`` structurellement
    valide (``pg_restore --list``, sans jamais se connecter à aucun
    serveur) et contient les tables attendues. Comme pour SQLite, ne
    vérifie pas ici la compatibilité de version avec la base active —
    c'est le rôle de l'appelant avant une restauration (voir
    ``get_embedded_alembic_version``/``get_live_alembic_version``)."""
    if not file_path.exists() or not file_path.is_file():
        return BackupVerification(False, False, False, None, ["Le fichier de sauvegarde est introuvable."])
    pg_restore_path = _locate_tool("pg_restore")
    if pg_restore_path is None:
        return BackupVerification(
            False, False, False, None,
            ["pg_restore est introuvable sur ce poste : impossible de vérifier l'archive."],
        )

    try:
        result = subprocess.run(
            [str(pg_restore_path), "--list", str(file_path)],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
            **no_console_window_kwargs(),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return BackupVerification(False, False, False, None, [f"Lecture de l'archive impossible : {exc}"])

    errors: list[str] = []
    integrity_ok = result.returncode == 0 and bool(result.stdout.strip())
    if not integrity_ok:
        errors.append("L'archive n'est pas un fichier pg_dump (format personnalisé) valide.")

    tables_ok = False
    if integrity_ok:
        actual_tables = set(_TOC_TABLE_RE.findall(result.stdout))
        missing = _expected_tables() - actual_tables
        tables_ok = not missing
        if not tables_ok:
            errors.append(f"Tables manquantes dans la sauvegarde : {', '.join(sorted(missing))}")

    alembic_version = get_embedded_alembic_version(file_path, timeout_seconds=timeout_seconds) if integrity_ok else None
    if integrity_ok and alembic_version is None:
        errors.append("Impossible de lire la version de schéma (table alembic_version) dans l'archive.")

    return BackupVerification(
        valid=integrity_ok and tables_ok, integrity_ok=integrity_ok, tables_ok=tables_ok,
        alembic_version=alembic_version, errors=errors,
    )


_COPY_ALEMBIC_RE = re.compile(r"^COPY\s+public\.alembic_version\b.*FROM stdin;\s*$", re.MULTILINE)


def get_embedded_alembic_version(
    file_path: Path, *, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS
) -> Optional[str]:
    """Lit la version de schéma embarquée dans une archive ``pg_dump``,
    sans jamais se connecter à aucun serveur ni rien restaurer : extrait
    uniquement les données de la table ``alembic_version`` en SQL brut
    (``pg_restore --data-only --table=alembic_version --file=-``), puis
    isole la ligne de données entre l'instruction ``COPY ... FROM stdin;``
    et son terminateur ``\\.`` — pendant, en lecture seule, de
    ``backup_engine.get_alembic_version`` (SQLite)."""
    pg_restore_path = _locate_tool("pg_restore")
    if pg_restore_path is None:
        return None
    try:
        result = subprocess.run(
            [str(pg_restore_path), "--data-only", "--table=alembic_version", "--file=-", str(file_path)],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
            **no_console_window_kwargs(),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None

    match = _COPY_ALEMBIC_RE.search(result.stdout)
    if not match:
        return None
    remainder = result.stdout[match.end():]
    for line in remainder.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "\\.":
            return None
        return stripped
    return None


def get_live_alembic_version(
    target: PostgreSQLTarget, password: str, *, timeout_seconds: int = DEFAULT_PROBE_TIMEOUT_SECONDS
) -> Optional[str]:
    """Lit la version de schéma de la base PostgreSQL active, par une
    connexion directe psycopg minimale — jamais via SQLAlchemy/le moteur
    mis en cache de l'application (même choix architectural que
    ``backup_engine.get_alembic_version``, qui évite toute dépendance à
    SQLAlchemy pour la mécanique pure de sauvegarde)."""
    import psycopg

    try:
        with psycopg.connect(
            host=target.host, port=target.port, dbname=target.database, user=target.username,
            password=password, connect_timeout=timeout_seconds,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version;")
                row = cursor.fetchone()
                return row[0] if row else None
    except psycopg.Error:
        return None


def restore_database_from_backup(
    target: PostgreSQLTarget, password: str, backup_path: Path, *,
    timeout_seconds: int = DEFAULT_DUMP_RESTORE_TIMEOUT_SECONDS,
) -> None:
    """Restaure ``target`` à partir de ``backup_path``. ``--single-transaction``
    garantit qu'un échec en cours de restauration annule l'intégralité de
    l'opération côté serveur (jamais un état partiellement restauré,
    §E.2.3) ; ``--clean --if-exists`` recrée le schéma depuis une table
    vide sans erreur si un objet n'existe pas encore ; ``--no-owner
    --no-privileges`` ne touche jamais aux rôles ni aux permissions
    serveur. Cible toujours ``target.database``, qui doit déjà exister —
    cette fonction ne crée jamais de base ni de rôle."""
    tools = ensure_tools_available()
    result = _run(
        [
            tools["pg_restore"], f"--host={target.host}", f"--port={target.port}",
            f"--username={target.username}", f"--dbname={target.database}",
            "--no-password", "--clean", "--if-exists", "--no-owner", "--no-privileges",
            "--exit-on-error", "--single-transaction", str(backup_path),
        ],
        password=password, timeout_seconds=timeout_seconds, tool_label="pg_restore",
    )
    if result.returncode != 0:
        _log_subprocess_failure("pg_restore", result.returncode, result.stderr)
        raise PostgreSQLBackupError(
            f"pg_restore a échoué (code {result.returncode}) pour {target.label()} — "
            "transaction annulée, la base cible n'a pas été modifiée."
        )


def list_backup_files(destination_dir: Path, *, prefix: str = BACKUP_PREFIX) -> list[BackupFileInfo]:
    """Sauvegardes PostgreSQL StockManager présentes dans
    ``destination_dir`` — même forme que
    ``backup_engine.list_backup_files``, jamais un fichier ne correspondant
    pas exactement au motif de nommage PostgreSQL (extension ``.dump``,
    jamais confondu avec une sauvegarde SQLite ``.db``, §E.3)."""
    if not destination_dir.exists():
        return []
    pattern = _filename_pattern(prefix)
    infos = []
    for entry in destination_dir.iterdir():
        if entry.is_file() and pattern.match(entry.name):
            stat = entry.stat()
            infos.append(
                BackupFileInfo(
                    path=entry, name=entry.name, size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                )
            )
    return sorted(infos, key=lambda info: info.name, reverse=True)


def apply_retention(destination_dir: Path, retention: int, *, prefix: str = BACKUP_PREFIX) -> list[Path]:
    """Même politique que ``backup_engine.apply_retention`` : ``retention
    <= 0`` ne supprime rien (choix sûr par défaut), jamais un fichier hors
    du motif de nommage PostgreSQL."""
    if retention <= 0:
        return []
    files = list_backup_files(destination_dir, prefix=prefix)
    deleted: list[Path] = []
    for info in files[retention:]:
        try:
            info.path.unlink()
            deleted.append(info.path)
        except OSError:
            continue
    return deleted
