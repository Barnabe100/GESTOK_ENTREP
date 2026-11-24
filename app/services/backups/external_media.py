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
import string
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MARKER_DIRNAME = ".stockmanager_backup_target"
MARKER_FILENAME = "marker.json"


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
