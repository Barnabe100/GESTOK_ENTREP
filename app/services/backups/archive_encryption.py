"""Chiffrement optionnel des archives de sauvegarde (Mission « Sauvegarde
automatique et restauration », §5 : « étudier la possibilité de chiffrer
les archives... la gestion et la récupération des clés doivent être
conçues sérieusement »).

Décision retenue : chiffrement symétrique via ``cryptography.fernet.Fernet``
(AES-128-CBC + HMAC-SHA256, authentifié — une archive altérée après
chiffrement est détectée au déchiffrement, pas seulement par l'empreinte du
manifeste) — ``cryptography`` est déjà une dépendance du projet (voir
requirements.txt), aucune bibliothèque supplémentaire. Désactivé par
défaut (voir ``BackupConfig.encryption_enabled``) : change un comportement
établi (les archives étaient jusqu'ici en clair), activé explicitement par
l'utilisateur depuis l'écran Sauvegardes, avec un avertissement explicite
sur la conséquence d'une perte de la clé.

Gestion de la clé — jamais en clair dans la configuration applicative,
jamais dans la base de données, jamais journalisée : stockée exclusivement
dans le coffre d'identifiants Windows
(:func:`app.security.credential_vault.get_backup_encryption_vault`, un
domaine de secret dédié), exactement la même convention que le mot de
passe PostgreSQL. Une seule clé par poste, générée une fois
(:func:`ensure_encryption_key`), jamais régénérée automatiquement — une
rotation de clé relèverait d'une action explicite distincte, hors périmètre
de cette mission.

Limite assumée et documentée (voir la documentation utilisateur) : une clé
perdue (coffre vidé, changement d'ordinateur sans migration du coffre) rend
TOUTE archive chiffrée définitivement illisible — ce module ne tente
jamais de la retrouver ni de la deviner. C'est pourquoi le chiffrement
reste désactivé par défaut et nécessite une action explicite et avertie de
l'utilisateur.

``vault`` est toujours un paramètre injectable (jamais uniquement résolu en
interne) : seul moyen de couvrir la logique de chiffrement/déchiffrement
par des tests qui n'ont jamais accès à Windows Credential Manager (voir
tests/test_archive_encryption.py, qui injecte un coffre en mémoire) — la
résolution réelle (:func:`get_backup_encryption_vault`, Windows uniquement)
reste le comportement par défaut en production."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.security.credential_vault import CredentialVault, get_backup_encryption_vault
from app.utils.exceptions import ConfigurationError

_KEY_PROFILE_ID = "archive-encryption-key"


class ArchiveEncryptionError(ConfigurationError):
    """Échec de chiffrement/déchiffrement — clé absente, invalide, ou
    archive corrompue/altérée (jeton Fernet non authentifiable)."""


def _resolve_vault(vault: Optional[CredentialVault]) -> CredentialVault:
    return vault if vault is not None else get_backup_encryption_vault()


def ensure_encryption_key(vault: Optional[CredentialVault] = None) -> bytes:
    """Retourne la clé de chiffrement des archives, la générant une seule
    fois si elle n'existe pas encore dans le coffre — jamais régénérée si
    déjà présente (une rotation changerait silencieusement l'accès à
    toutes les archives déjà chiffrées)."""
    resolved_vault = _resolve_vault(vault)
    existing = resolved_vault.get_password(_KEY_PROFILE_ID)
    if existing:
        return existing.encode("ascii")
    new_key = Fernet.generate_key()
    resolved_vault.set_password(_KEY_PROFILE_ID, new_key.decode("ascii"))
    return new_key


def encrypt_file_in_place(path: Path, *, vault: Optional[CredentialVault] = None) -> None:
    """Chiffre ``path`` sur place — écrit d'abord dans un fichier
    temporaire du même répertoire, ne remplace l'original (``os.replace``,
    atomique) qu'une fois le chiffrement terminé avec succès : jamais de
    fichier partiellement chiffré laissé en place en cas d'échec (même
    convention que ``postgresql_backup_engine.create_backup_file``). À
    appeler seulement après la vérification structurelle de l'archive en
    clair (``backup_engine.verify_backup_file``/
    ``postgresql_backup_engine.verify_backup_file`` ne savent lire qu'une
    archive en clair) — jamais avant."""
    key = ensure_encryption_key(vault)
    fernet = Fernet(key)
    plaintext = path.read_bytes()
    token = fernet.encrypt(plaintext)

    fd, tmp_path_str = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}_", suffix=".enc.tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(token)
        os.replace(tmp_path_str, path)
    except BaseException:
        Path(tmp_path_str).unlink(missing_ok=True)
        raise


def decrypt_file_to_temp(path: Path, *, vault: Optional[CredentialVault] = None) -> Path:
    """Déchiffre ``path`` (archive chiffrée) vers un nouveau fichier
    temporaire, dont le chemin est retourné — l'original n'est jamais
    modifié ni supprimé ; l'appelant est responsable de supprimer le
    fichier temporaire une fois son usage terminé (restauration, test
    d'intégrité, etc.). Lève :class:`ArchiveEncryptionError` si le jeton
    n'est pas authentique (mauvaise clé, ou archive corrompue/modifiée
    depuis son chiffrement) — jamais une exception technique brute de
    ``cryptography``."""
    key = ensure_encryption_key(vault)
    fernet = Fernet(key)
    token = path.read_bytes()
    try:
        plaintext = fernet.decrypt(token)
    except InvalidToken as exc:
        raise ArchiveEncryptionError(
            "Impossible de déchiffrer l'archive : clé de chiffrement incorrecte, "
            "ou archive corrompue/modifiée depuis son chiffrement."
        ) from exc

    fd, tmp_path_str = tempfile.mkstemp(prefix=f".{path.name}_", suffix=".dec.tmp")
    with os.fdopen(fd, "wb") as handle:
        handle.write(plaintext)
    return Path(tmp_path_str)
