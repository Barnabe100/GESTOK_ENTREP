"""Métadonnées versionnées d'une archive de sauvegarde — fichier sidecar
``<archive>.manifest.json``, toujours à côté de l'archive elle-même (jamais
embarqué dans le fichier ``.db``/``.dump``, pour rester lisible sans ouvrir
ni interpréter le format propre à chaque moteur).

Mission « Sauvegarde automatique et restauration », §5 du mandat : chaque
archive doit porter la date de création, la version de StockManager, le
moteur de base de données, la version de schéma (Alembic), le type de
sauvegarde, la taille, et une empreinte cryptographique permettant de
détecter toute altération après coup (copie partielle, support
défaillant) — indépendamment de la vérification structurelle propre à
chaque moteur (``backup_engine``/``postgresql_backup_engine``, qui vérifie
que le contenu est une base/archive exploitable, pas que les octets n'ont
pas changé depuis la création).

Format documenté et versionné (``FORMAT_VERSION``) : un futur changement de
forme ajoute un champ ou incrémente la version, ne retire jamais un champ
existant ni n'en change le sens — une version future de StockManager doit
toujours pouvoir lire un manifeste plus ancien. Jamais aucun secret ici
(mot de passe, clé de chiffrement) : seule la présence d'un chiffrement est
signalée (``encrypted``), jamais la clé elle-même (voir
``archive_encryption.py``, qui résout la clé séparément via le coffre
d'identifiants).

L'empreinte (``sha256``) est toujours calculée sur le fichier tel qu'il se
trouve réellement sur le disque au moment de l'écriture du manifeste —
après un éventuel chiffrement, jamais avant : elle doit toujours
correspondre exactement aux octets qui seront relus plus tard (par
``verify_manifest_for``, une copie externe, ou une restauration), quel que
soit l'ordre des transformations appliquées par l'appelant.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.version import __version__

FORMAT_VERSION = 1

BACKUP_TYPE_LOCAL = "locale"
BACKUP_TYPE_EXTERNAL = "externe"
BACKUP_TYPE_SECURITY = "securite"

_HASH_CHUNK_SIZE = 1024 * 1024
_MANIFEST_SUFFIX = ".manifest.json"


def manifest_path_for(archive_path: Path) -> Path:
    """Chemin du manifeste associé à ``archive_path`` — toujours le même
    nom de fichier avec ``.manifest.json`` ajouté, jamais un emplacement
    séparé (pour qu'une copie manuelle de l'archive qui emporterait aussi ce
    fichier reste cohérente sans configuration supplémentaire)."""
    return archive_path.with_name(archive_path.name + _MANIFEST_SUFFIX)


def compute_sha256(file_path: Path) -> str:
    """Empreinte SHA-256 de ``file_path``, lue par blocs pour rester
    utilisable sur une base volumineuse sans en charger l'intégralité en
    mémoire."""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ArchiveManifest:
    """Métadonnées d'une archive — voir la docstring de module pour le
    contrat de compatibilité ascendante de ces champs."""

    format_version: int
    created_at: str  # ISO 8601, toujours UTC.
    stockmanager_version: str
    db_engine: str  # "sqlite" | "postgresql"
    schema_version: Optional[str]  # version Alembic (alembic_version.version_num), None si illisible.
    backup_type: str  # BACKUP_TYPE_LOCAL | BACKUP_TYPE_EXTERNAL | BACKUP_TYPE_SECURITY
    size_bytes: int
    sha256: str
    encrypted: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def from_json(text: str) -> "ArchiveManifest":
        data = json.loads(text)
        # Accepte un manifeste de format futur portant des champs
        # supplémentaires inconnus de cette version (compatibilité
        # descendante volontaire) : ne retient que les champs reconnus ici.
        known_fields = {f.name for f in ArchiveManifest.__dataclass_fields__.values()}
        filtered = {key: value for key, value in data.items() if key in known_fields}
        return ArchiveManifest(**filtered)


def build_manifest(
    archive_path: Path, *, db_engine: str, schema_version: Optional[str], backup_type: str, encrypted: bool = False,
) -> ArchiveManifest:
    """Construit le manifeste de ``archive_path`` à partir de son état
    actuel sur le disque — jamais une valeur devinée pour ``size_bytes``/
    ``sha256``, toujours relue au moment de l'appel."""
    return ArchiveManifest(
        format_version=FORMAT_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(),
        stockmanager_version=__version__,
        db_engine=db_engine,
        schema_version=schema_version,
        backup_type=backup_type,
        size_bytes=archive_path.stat().st_size,
        sha256=compute_sha256(archive_path),
        encrypted=encrypted,
    )


def write_manifest_for(
    archive_path: Path, *, db_engine: str, schema_version: Optional[str], backup_type: str, encrypted: bool = False,
) -> ArchiveManifest:
    """Construit puis écrit le manifeste de ``archive_path`` — à appeler en
    tout dernier, après toute transformation du fichier d'archive
    (chiffrement compris, voir la docstring de module)."""
    manifest = build_manifest(
        archive_path, db_engine=db_engine, schema_version=schema_version,
        backup_type=backup_type, encrypted=encrypted,
    )
    manifest_path_for(archive_path).write_text(manifest.to_json(), encoding="utf-8")
    return manifest


def delete_manifest_for(archive_path: Path) -> None:
    """Supprime le manifeste associé à ``archive_path``, s'il existe —
    jamais une erreur si déjà absent. À appeler chaque fois que l'archive
    elle-même est supprimée (rotation, voir ``BackupService``) : un
    manifeste orphelin (sans archive associée) n'a aucune utilité et ne
    doit jamais s'accumuler indéfiniment dans le dossier de destination."""
    manifest_path_for(archive_path).unlink(missing_ok=True)


def read_manifest_for(archive_path: Path) -> Optional[ArchiveManifest]:
    """Lit le manifeste associé à ``archive_path``, ou ``None`` s'il est
    absent ou illisible (jamais une exception : une archive plus ancienne
    que l'introduction de ce mécanisme, ou copiée sans son manifeste, reste
    utilisable — seulement sans cette vérification supplémentaire)."""
    path = manifest_path_for(archive_path)
    if not path.is_file():
        return None
    try:
        return ArchiveManifest.from_json(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, KeyError):
        return None


@dataclass(frozen=True)
class ManifestVerification:
    """Résultat de la vérification d'intégrité par empreinte — jamais la
    seule vérification effectuée avant une restauration : toujours combinée
    à la vérification structurelle du moteur concerné (voir
    ``backup_engine.verify_backup_file``/``postgresql_backup_engine.verify_backup_file``)."""

    present: bool
    hash_matches: bool
    errors: list[str] = field(default_factory=list)


def verify_manifest_for(archive_path: Path) -> ManifestVerification:
    """Vérifie que l'empreinte enregistrée correspond toujours au contenu
    actuel de l'archive — détecte une corruption/altération après coup
    (copie partielle, support défaillant) qu'une vérification structurelle
    seule ne détecterait pas forcément."""
    manifest = read_manifest_for(archive_path)
    if manifest is None:
        return ManifestVerification(
            present=False, hash_matches=False,
            errors=["Aucun manifeste associé à cette archive (sauvegarde antérieure à ce mécanisme, ou copiée sans lui)."],
        )
    if not archive_path.is_file():
        return ManifestVerification(present=True, hash_matches=False, errors=["Archive introuvable."])
    actual_hash = compute_sha256(archive_path)
    if actual_hash != manifest.sha256:
        return ManifestVerification(
            present=True, hash_matches=False,
            errors=[
                f"Empreinte invalide (attendue {manifest.sha256[:12]}…, obtenue {actual_hash[:12]}…) "
                "— fichier modifié ou corrompu depuis sa création."
            ],
        )
    return ManifestVerification(present=True, hash_matches=True, errors=[])
