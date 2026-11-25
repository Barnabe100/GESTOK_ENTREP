"""Identification fiable d'un support externe (clé USB, disque externe) —
jamais une seule lettre de lecteur Windows (elle peut changer d'un
branchement à l'autre, ou selon l'ordre de connexion d'autres
périphériques), toujours un marqueur StockManager écrit une fois à la
racine du support choisi, puis retrouvé en parcourant les lecteurs
disponibles à chaque utilisation (Mission « Sauvegarde automatique et
restauration », §4 : « ne pas dépendre uniquement d'une lettre de lecteur
fixe comme E: ou F: »).

Marqueur = un petit fichier JSON contenant un identifiant généré une seule
fois (UUID), un libellé humain, et la date de création — jamais aucune
donnée métier, jamais un secret. Il n'est pas cherché à le rendre invisible
par un attribut Windows spécifique : seule l'incohérence silencieuse d'une
lettre de lecteur qui change est le problème visé ici, pas une protection
contre une suppression délibérée par l'utilisateur.

Pas de dépendance à ``pywin32``/WMI pour cette première version : parcourir
les lettres de lecteur actuellement montées et lire un petit fichier
suffit à retrouver le marqueur de façon fiable, sans élévation ni
bibliothèque supplémentaire (cohérent avec le §4 du mandat : « éviter les
privilèges administrateur permanents lorsque ce n'est pas nécessaire »).
Toutes les fonctions qui manipulent un support restent testables
indépendamment de Windows : la racine du support est toujours un ``Path``
injecté par l'appelant (un répertoire temporaire en test) — seule
:func:`list_candidate_drive_roots` est spécifique à Windows (énumération
des lettres de lecteur), isolée pour rester simple à substituer en test.
"""
from __future__ import annotations

import json
import os
import re
import string
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

MARKER_DIRNAME = ".stockmanager_backup_target"
MARKER_FILENAME = "marker.json"

# Mission corrective « Correction et validation du module de sauvegarde sous
# Windows » : une lettre de lecteur seule (``"E:"``, sans barre) est, en
# pathlib/Windows, un chemin RELATIF à cette lettre (le répertoire courant
# de ce lecteur pour le processus), jamais sa racine absolue — un piège
# classique confirmé comme cause racine du défaut diagnostiqué (« support
# configuré avec succès » puis « inaccessible » juste après : le marqueur
# était écrit à un endroit différent de celui où `list_candidate_drive_roots`
# le cherche ensuite). Un simple motif par expression régulière sur le texte
# du chemin, jamais sur ``Path.drive`` (dont le comportement dépend de la
# classe concrète de ``Path`` — ``WindowsPath`` vs ``PosixPath`` — donc
# jamais fiable à tester hors Windows), rend cette normalisation testable
# indépendamment de la plateforme d'exécution.
_DRIVE_LETTER_RE = re.compile(r"^([A-Za-z]):[\\/]?")


def normalize_drive_root(path: "Path | str") -> Path:
    """Résout un chemin désignant un lecteur Windows (``E:``, ``E:/``,
    ``e:\\sous-dossier``...) vers la racine canonique de ce lecteur
    (``X:/``) — jamais un sous-dossier, jamais une forme sans barre finale
    ambiguë (cause racine confirmée du défaut diagnostiqué, voir la
    docstring de module).

    Un chemin qui ne correspond à aucune lettre de lecteur Windows (ex. un
    chemin POSIX, utilisé comme racine de test sur une plateforme sans
    notion de lettre de lecteur — voir les suites de tests de ce module)
    est retourné tel quel, jamais rejeté : la normalisation elle-même n'a
    de sens que pour une forme ``lettre:``, elle ne prétend jamais valider
    qu'un chemin constitue par ailleurs une destination appropriée (cette
    décision relève de :func:`list_drives_with_info`, voir sa docstring,
    §2.2 du mandat correctif : « éviter ... des destinations
    inappropriées »)."""
    match = _DRIVE_LETTER_RE.match(str(path))
    if match:
        return Path(f"{match.group(1).upper()}:/")
    return Path(path)


@dataclass(frozen=True)
class ExternalMediaMarker:
    """Identité stable d'un support externe choisi par l'utilisateur —
    ``marker_id`` est le seul champ réellement utilisé pour la
    reconnaissance (voir :func:`find_marker_drive`) ; ``label``/``created_at``
    sont uniquement informatifs (affichage à l'utilisateur, diagnostic)."""

    marker_id: str
    label: str
    created_at: str


def _marker_path(drive_root: Path) -> Path:
    return drive_root / MARKER_DIRNAME / MARKER_FILENAME


def create_marker(drive_root: Path, label: str) -> ExternalMediaMarker:
    """Écrit un nouveau marqueur à la racine de ``drive_root``. Remplace
    tout marqueur déjà présent (permet de ré-associer un support déjà
    utilisé, ex. après reformatage) : seule l'identification est écrasée,
    jamais les sauvegardes déjà présentes sur le support, que cette
    fonction ne touche jamais."""
    marker = ExternalMediaMarker(
        marker_id=str(uuid.uuid4()), label=label, created_at=datetime.now(timezone.utc).isoformat(),
    )
    path = _marker_path(drive_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(marker), indent=2, ensure_ascii=False), encoding="utf-8")
    return marker


def read_marker(drive_root: Path) -> Optional[ExternalMediaMarker]:
    """Lit le marqueur présent à la racine de ``drive_root``, ou ``None``
    s'il est absent/illisible — jamais une exception : un support non
    encore configuré, ou un lecteur sans rapport avec StockManager, est un
    cas normal, pas une erreur."""
    path = _marker_path(drive_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExternalMediaMarker(**data)
    except (OSError, json.JSONDecodeError, TypeError, KeyError):
        return None


def list_candidate_drive_roots() -> list[Path]:
    """Racines de lecteur Windows actuellement montées (``C:/`` à ``Z:/``)
    — liste vide hors Windows (aucune notion de lettre de lecteur
    ailleurs) ; l'appelant doit en tenir compte. Volontairement simple (pas
    de distinction amovible/fixe via WMI) : le marqueur StockManager est la
    seule source de vérité pour reconnaître LE support configuré parmi tous
    les lecteurs montés, qu'il s'agisse d'une clé USB ou d'un disque
    externe."""
    if sys.platform != "win32":
        return []
    roots = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:/")
        if root.exists():
            roots.append(root)
    return roots


def find_marker_drive(
    expected_marker_id: str, *, candidate_roots: Optional[list[Path]] = None
) -> Optional[Path]:
    """Cherche, parmi ``candidate_roots`` (les lecteurs Windows montés par
    défaut si omis), celui portant le marqueur StockManager dont
    l'identifiant correspond à ``expected_marker_id`` — jamais une
    correspondance sur le seul libellé ni la seule lettre de lecteur,
    toujours l'identifiant stable. Retourne ``None`` si aucun lecteur
    actuellement accessible ne porte ce marqueur (support débranché,
    lettre pas encore montée, etc.) — jamais considéré comme une réussite
    (voir le mandat, §4 : « si le support est absent, ne pas considérer
    l'opération comme réussie »)."""
    roots = candidate_roots if candidate_roots is not None else list_candidate_drive_roots()
    for root in roots:
        marker = read_marker(root)
        if marker is not None and marker.marker_id == expected_marker_id:
            return root
    return None


def is_media_accessible(expected_marker_id: str, *, candidate_roots: Optional[list[Path]] = None) -> bool:
    """Confort : équivalent booléen de :func:`find_marker_drive`, pour un
    simple test d'accessibilité (bouton « Tester l'accessibilité du
    support » de l'écran Sauvegardes) sans avoir besoin du chemin résolu."""
    return find_marker_drive(expected_marker_id, candidate_roots=candidate_roots) is not None


def check_root_accessible(root: Path) -> Optional[str]:
    """Vérifie que ``root`` existe et accepte réellement l'écriture (crée
    puis supprime immédiatement un petit fichier de test) — jamais
    seulement son existence, qui pourrait mentir (support présent mais en
    lecture seule, carte mémoire protégée). Retourne ``None`` si tout est
    en ordre, sinon un message prêt à afficher à l'utilisateur. Ne crée
    jamais le dossier lui-même s'il est absent (contrairement à
    ``BackupService.update_config`` pour le dossier de destination local) :
    un support externe absent ou dont la racine n'existe pas ne doit
    jamais être créé de toutes pièces par StockManager."""
    if not root.exists() or not root.is_dir():
        return f"« {root} » n'existe pas ou n'est pas accessible."
    try:
        fd, tmp_path_str = tempfile.mkstemp(dir=str(root), prefix=".stockmanager_test_ecriture_")
        os.close(fd)
        Path(tmp_path_str).unlink(missing_ok=True)
    except OSError as exc:
        return f"« {root} » n'est pas accessible en écriture : {exc}"
    return None


@dataclass(frozen=True)
class DriveInfo:
    """Un lecteur proposable comme support externe, avec assez
    d'informations pour que l'utilisateur l'identifie sans ambiguïté dans
    un sélecteur dédié (mission corrective, §2.4 : remplacer le sélecteur
    de dossier générique par une véritable sélection de lecteur) — jamais
    une simple lettre nue."""

    root: Path
    drive_type: str  # "removable" | "fixed"
    volume_label: str
    marker: Optional[ExternalMediaMarker]


_DRIVE_TYPE_CODES = {2: "removable", 3: "fixed"}


def _real_drive_type(root: Path) -> str:
    """``GetDriveTypeW`` (``ctypes``, jamais ``pywin32`` — même convention
    que le reste du module, voir sa docstring) — Windows uniquement,
    jamais appelée directement en test (voir ``drive_type_resolver``
    injectable de :func:`list_drives_with_info`)."""
    import ctypes

    code = ctypes.windll.kernel32.GetDriveTypeW(str(root))
    return _DRIVE_TYPE_CODES.get(code, "other")


def _real_volume_label(root: Path) -> str:
    """``GetVolumeInformationW`` (``ctypes``) — Windows uniquement, jamais
    appelée directement en test (voir ``volume_label_resolver``
    injectable). Chaîne vide si l'étiquette ne peut être lue (support sans
    étiquette, ou inaccessible) — jamais une exception pour cette seule
    information de confort."""
    import ctypes

    buffer = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(str(root), buffer, len(buffer), None, None, None, None, 0)
    return buffer.value if ok else ""


def list_drives_with_info(
    *, candidate_roots: Optional[list[Path]] = None,
    drive_type_resolver: Optional[Callable[[Path], str]] = None,
    volume_label_resolver: Optional[Callable[[Path], str]] = None,
) -> list[DriveInfo]:
    """Énumère les lecteurs proposables comme support externe — clés USB
    (``DRIVE_REMOVABLE``) ET disques durs externes USB (très souvent
    identifiés par Windows comme ``DRIVE_FIXED``, indiscernables d'un
    disque interne par ce seul indicateur — mission corrective, §2 : « ne
    pas filtrer exclusivement selon DRIVE_REMOVABLE »), à l'exclusion
    explicite :

    - du disque système (``SystemDrive``, ex. ``C:``) — jamais proposé,
      quel que soit son type apparent ;
    - des lecteurs réseau (``DRIVE_REMOTE``), optiques (``DRIVE_CDROM``),
      disques virtuels en mémoire (``DRIVE_RAMDISK``) et lecteurs non
      montés/inconnus (``DRIVE_NO_ROOT_DIR``/``DRIVE_UNKNOWN``) — jamais
      des destinations appropriées pour une protection externe physique
      (mandat, §2.2 : « éviter de proposer ... des destinations
      inappropriées »).

    ``candidate_roots``/``drive_type_resolver``/``volume_label_resolver``
    injectables (tests) — en production, toujours vide hors Windows (même
    convention que :func:`list_candidate_drive_roots`), et toujours les
    fonctions ``ctypes`` réelles ci-dessus."""
    if sys.platform != "win32" and candidate_roots is None:
        return []
    roots = candidate_roots if candidate_roots is not None else list_candidate_drive_roots()
    resolve_type = drive_type_resolver or _real_drive_type
    resolve_label = volume_label_resolver or _real_volume_label

    try:
        system_drive = normalize_drive_root(os.environ.get("SystemDrive", "C:") + "\\")
    except ValueError:
        system_drive = None

    infos = []
    for root in roots:
        try:
            if system_drive is not None and normalize_drive_root(root) == system_drive:
                continue
        except ValueError:
            pass
        drive_type = resolve_type(root)
        if drive_type not in ("removable", "fixed"):
            continue
        infos.append(
            DriveInfo(root=root, drive_type=drive_type, volume_label=resolve_label(root), marker=read_marker(root))
        )
    return infos
