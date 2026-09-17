"""§17 : vérifie qu'aucune clé privée de signature ne se trouve nulle part
dans le projet client (app/, tests/, ressources, configuration) — la
contrainte non négociable de cette phase. La clé privée ne doit exister que
sur le poste de l'éditeur, produite par ``license_generator/generate_keypair.py``
dans ``license_generator/keys/`` (répertoire gitignoré, jamais suivi par git).
"""
import subprocess
from pathlib import Path

import pytest

from app.services.licensing.public_key import PRODUCTION_PUBLIC_KEY_BYTES

REPO_ROOT = Path(__file__).resolve().parent.parent

# Marqueurs caractéristiques d'une clé privée PEM (PKCS8/Ed25519), sous
# toutes les variantes usuelles d'en-tête.
_PRIVATE_KEY_MARKERS = ("BEGIN PRIVATE KEY", "BEGIN EC PRIVATE KEY", "BEGIN RSA PRIVATE KEY", "PRIVATE_KEY_PEM")

# Répertoires du dépôt appartenant au projet CLIENT (jamais le générateur,
# jamais les clés locales générées par generate_keypair.py).
_CLIENT_DIRECTORIES = ["app", "tests", "migrations"]


_SELF_PATH = Path(__file__).resolve()


def _iter_text_files(directory: Path):
    for path in directory.rglob("*"):
        # Exclut ce fichier lui-même : il cite les marqueurs recherchés dans
        # son propre code (_PRIVATE_KEY_MARKERS), ce qui produirait un faux
        # positif si on le scannait.
        if path.is_file() and path.suffix in {".py", ".ini", ".cfg", ".toml", ".txt", ".md", ".json"} and path != _SELF_PATH:
            yield path


def test_production_public_key_has_the_size_of_an_ed25519_public_key() -> None:
    """32 octets : la taille d'une clé PUBLIQUE Ed25519 brute — une taille
    différente indiquerait un format inattendu (ou, par erreur, une paire
    de clés complète) embarqué côté client."""
    assert len(PRODUCTION_PUBLIC_KEY_BYTES) == 32


@pytest.mark.parametrize("directory_name", _CLIENT_DIRECTORIES)
def test_no_private_key_marker_in_client_source(directory_name: str) -> None:
    directory = REPO_ROOT / directory_name
    offenders = []
    for path in _iter_text_files(directory):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(marker in content for marker in _PRIVATE_KEY_MARKERS):
            offenders.append(str(path))
    assert offenders == [], f"Marqueur de clé privée trouvé dans le projet client : {offenders}"


def test_license_generator_keys_directory_is_gitignored() -> None:
    gitignore_content = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "license_generator/keys/" in gitignore_content


def test_license_generator_private_key_file_is_not_tracked_by_git() -> None:
    """Interroge git directement : même si la clé existe sur ce poste
    (générée pour produire la clé publique de production embarquée), elle ne
    doit jamais apparaître dans les fichiers suivis par le dépôt."""
    result = subprocess.run(
        ["git", "ls-files", "license_generator/keys"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == ""


def test_no_file_tracked_by_git_contains_a_pem_private_key_marker() -> None:
    """Balayage de l'ensemble des fichiers suivis par git (donc de ce qui
    serait réellement publié/distribué), pas seulement de app/tests/ —
    filet de sécurité final avant commit."""
    tracked_files = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    offenders = []
    for relative_path in tracked_files:
        path = REPO_ROOT / relative_path
        if not path.is_file() or path == _SELF_PATH:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(marker in content for marker in _PRIVATE_KEY_MARKERS):
            offenders.append(relative_path)

    assert offenders == [], f"Marqueur de clé privée trouvé dans un fichier suivi par git : {offenders}"
