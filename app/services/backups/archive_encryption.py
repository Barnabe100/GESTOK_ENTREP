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

import base64
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.security.credential_vault import CredentialVault, get_backup_encryption_vault
from app.utils.exceptions import ConfigurationError

_KEY_PROFILE_ID = "archive-encryption-key"

# Mission corrective « Fiabilisation du module de sauvegarde », §3.1 :
# format du fichier de transfert de clé (JSON, versionné — même esprit que
# archive_manifest.py) et paramètres de dérivation du mot de passe de
# protection. 600 000 itérations PBKDF2-HMAC-SHA256 : recommandation OWASP
# courante pour ce choix d'algorithme, négligeable en durée pour une
# opération réalisée à la demande, jamais dans un chemin critique.
_TRANSFER_FORMAT_VERSION = 1
_TRANSFER_KDF_ITERATIONS = 600_000
_TRANSFER_SALT_BYTES = 16


class ArchiveEncryptionError(ConfigurationError):
    """Échec de chiffrement/déchiffrement — clé absente, invalide, ou
    archive corrompue/altérée (jeton Fernet non authentifiable)."""


class NoEncryptionKeyConfiguredError(ArchiveEncryptionError):
    """Aucune clé de chiffrement n'existe encore sur ce poste. Contrairement
    au chiffrement (première utilisation, voir :func:`ensure_encryption_key`),
    ceci n'est jamais traité en générant une nouvelle clé aléatoire à sa
    place (mission corrective, §3.12) : une tentative de déchiffrement ou
    d'export sans clé locale signifie presque toujours que la bonne clé n'a
    jamais été importée sur ce poste — typiquement après un changement
    d'ordinateur — et générer une clé de remplacement mènerait
    systématiquement à un échec trompeur (« mauvaise clé »), jamais à un
    diagnostic clair pour l'utilisateur."""


class KeyTransferError(ArchiveEncryptionError):
    """Échec d'export ou d'import de la clé de chiffrement — mot de passe
    incorrect, fichier de transfert absent/corrompu/dans un format non
    reconnu, ou destination d'export refusée."""


class EncryptionKeyAlreadyConfiguredError(ArchiveEncryptionError):
    """Une clé de chiffrement existe déjà sur ce poste — jamais remplacée
    silencieusement par un import (mission corrective, §3.1 : « ne jamais
    remplacer silencieusement une clé déjà présente »). L'appelant doit
    fournir une confirmation explicite (``overwrite=True`` sur
    :func:`import_encryption_key`), obtenue après avertissement clair côté
    interface."""


def _resolve_vault(vault: Optional[CredentialVault]) -> CredentialVault:
    return vault if vault is not None else get_backup_encryption_vault()


def _derive_wrapping_key(password: str, salt: bytes) -> bytes:
    """Dérive, à partir du mot de passe choisi par l'utilisateur, une clé
    Fernet valide (32 octets encodés base64 URL-safe) — jamais le mot de
    passe lui-même conservé où que ce soit, uniquement utilisé ici de façon
    transitoire pour cette dérivation."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_TRANSFER_KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def fingerprint_of(key: bytes) -> str:
    """Empreinte SHA-256 (hexadécimale) d'une clé de chiffrement — jamais
    la clé elle-même, jamais réversible, jamais exploitable pour déchiffrer
    quoi que ce soit (mission corrective « Correction et validation du
    module de sauvegarde sous Windows », point d'ajustement n°1 : détecter
    de façon fiable qu'une clé de chiffrement a déjà existé sur ce poste,
    même si les archives qu'elle protège ont depuis été déplacées vers un
    support externe ou un autre ordinateur — jamais limité à une recherche
    dans le seul dossier de destination actuellement configuré). Une clé
    Fernet est 256 bits d'aléa uniforme : son empreinte ne réduit en rien
    l'espace de recherche d'une attaque par force brute, jamais un risque
    de sécurité à la conserver dans la base de données applicative
    (contrairement à la clé elle-même, qui n'y est et n'y sera jamais)."""
    return hashlib.sha256(key).hexdigest()


def ensure_encryption_key(vault: Optional[CredentialVault] = None) -> bytes:
    """Retourne la clé de chiffrement des archives, la générant une seule
    fois si elle n'existe pas encore dans le coffre — jamais régénérée si
    déjà présente (une rotation changerait silencieusement l'accès à
    toutes les archives déjà chiffrées). Réservée au CHIFFREMENT (première
    utilisation légitime d'une absence de clé) — voir
    :func:`require_existing_encryption_key` pour le déchiffrement, où ce
    comportement serait trompeur (mission corrective, §3.12)."""
    resolved_vault = _resolve_vault(vault)
    existing = resolved_vault.get_password(_KEY_PROFILE_ID)
    if existing:
        return existing.encode("ascii")
    new_key = Fernet.generate_key()
    resolved_vault.set_password(_KEY_PROFILE_ID, new_key.decode("ascii"))
    return new_key


def require_existing_encryption_key(vault: Optional[CredentialVault] = None) -> bytes:
    """Retourne la clé déjà configurée sur ce poste — ne la génère JAMAIS
    si elle est absente, contrairement à :func:`ensure_encryption_key` :
    lève :class:`NoEncryptionKeyConfiguredError` dans ce cas, avec un
    message orientant explicitement vers l'import de la clé de transfert
    (mission corrective, §3.12). À utiliser pour tout déchiffrement et pour
    tout export de clé — jamais pour un chiffrement, qui doit pouvoir
    générer une première clé légitimement."""
    resolved_vault = _resolve_vault(vault)
    existing = resolved_vault.get_password(_KEY_PROFILE_ID)
    if not existing:
        raise NoEncryptionKeyConfiguredError(
            "Aucune clé de chiffrement n'est configurée sur ce poste. Si cette archive provient "
            "d'un autre ordinateur, importez d'abord sa clé de chiffrement (« Importer la clé de "
            "chiffrement… », écran Sauvegardes) avant de poursuivre."
        )
    return existing.encode("ascii")


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


# -- transfert de la clé vers un autre ordinateur (mission corrective, §3.1) -------
#
# Exigence du mandat initial (§5) restée sans réponse jusqu'ici : « étudier
# la possibilité de chiffrer les archives... la gestion et la récupération
# des clés doit être pensée sérieusement... une sauvegarde dont la clé est
# perdue devient inutilisable ». Les fonctions ci-dessous permettent de
# déplacer la clé elle-même, jamais en clair, d'un poste à l'autre —
# indépendamment des archives qu'elle protège (jamais dans le même dossier
# qu'elles, voir ``export_encryption_key``).


def export_encryption_key(
    destination_path: Path, password: str, *, vault: Optional[CredentialVault] = None,
    backup_destination: Optional[Path] = None,
) -> None:
    """Exporte la clé de chiffrement actuellement configurée sur ce poste
    vers ``destination_path``, protégée par ``password`` (jamais conservé
    nulle part, utilisé uniquement pour dériver une clé d'enveloppe
    PBKDF2-HMAC-SHA256/Fernet — voir :func:`_derive_wrapping_key`).

    N'exporte jamais une clé inexistante : lève
    :class:`NoEncryptionKeyConfiguredError` si aucune clé n'a encore été
    générée sur ce poste (jamais généré une nouvelle clé pour l'occasion,
    voir :func:`require_existing_encryption_key` — exporter une clé que
    personne n'a jamais utilisée pour chiffrer quoi que ce soit n'aurait
    aucun sens).

    Si ``backup_destination`` est fourni (le dossier de sauvegardes
    actuellement configuré), refuse explicitement d'y exporter directement
    (§3.1 du mandat correctif : « l'export ne doit jamais être réalisé
    automatiquement dans le dossier contenant les sauvegardes ») — la clé
    ne doit jamais se retrouver sur le même support que les archives
    qu'elle protège, sans quoi la perte de ce support emporterait les deux
    à la fois."""
    if not password:
        raise KeyTransferError("Le mot de passe de protection du fichier de transfert est obligatoire.")

    resolved_vault = _resolve_vault(vault)
    raw_key = require_existing_encryption_key(resolved_vault)

    destination_path = Path(destination_path)
    if backup_destination is not None:
        try:
            exports_into_backup_folder = destination_path.resolve().parent == Path(backup_destination).resolve()
        except OSError:
            exports_into_backup_folder = False
        if exports_into_backup_folder:
            raise KeyTransferError(
                "La clé de chiffrement ne doit jamais être exportée dans le dossier des sauvegardes "
                "lui-même — choisissez un autre emplacement, conservé séparément de vos archives "
                "(ex. une clé USB différente, un coffre-fort numérique de l'entreprise)."
            )

    salt = os.urandom(_TRANSFER_SALT_BYTES)
    wrapping_key = _derive_wrapping_key(password, salt)
    wrapped_token = Fernet(wrapping_key).encrypt(raw_key)

    payload = {
        "format_version": _TRANSFER_FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kdf": "PBKDF2HMAC-SHA256",
        "kdf_iterations": _TRANSFER_KDF_ITERATIONS,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "wrapped_key_b64": wrapped_token.decode("ascii"),
    }

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(destination_path.parent), prefix=f".{destination_path.name}_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp_path_str, destination_path)
    except BaseException:
        Path(tmp_path_str).unlink(missing_ok=True)
        raise


def import_encryption_key(
    source_path: Path, password: str, *, vault: Optional[CredentialVault] = None, overwrite: bool = False,
) -> None:
    """Importe une clé de chiffrement depuis un fichier produit par
    :func:`export_encryption_key`. Vérifie le mot de passe (et donc
    l'authenticité du fichier) avant toute écriture dans le coffre — un mot
    de passe incorrect ou un fichier altéré lève :class:`KeyTransferError`,
    jamais une clé invalide écrite silencieusement.

    Ne remplace JAMAIS une clé déjà présente sur ce poste sans
    confirmation explicite : lève :class:`EncryptionKeyAlreadyConfiguredError`
    si ``overwrite`` n'est pas explicitement ``True`` (mission corrective,
    §3.1) — à l'appelant (interface) de l'obtenir auprès de l'utilisateur
    avant de rappeler cette fonction avec ``overwrite=True``."""
    resolved_vault = _resolve_vault(vault)
    try:
        raw_payload = Path(source_path).read_text(encoding="utf-8")
        data = json.loads(raw_payload)
        salt = base64.b64decode(data["salt_b64"])
        wrapped_token = data["wrapped_key_b64"].encode("ascii")
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise KeyTransferError(
            f"Fichier de transfert de clé illisible ou dans un format non reconnu : {exc}"
        ) from exc

    wrapping_key = _derive_wrapping_key(password, salt)
    try:
        candidate_key = Fernet(wrapping_key).decrypt(wrapped_token)
    except InvalidToken as exc:
        raise KeyTransferError(
            "Mot de passe incorrect, ou fichier de transfert de clé corrompu/altéré."
        ) from exc

    try:
        Fernet(candidate_key)  # valide que la clé déchiffrée est elle-même une clé Fernet exploitable.
    except (ValueError, TypeError) as exc:
        raise KeyTransferError(f"La clé importée n'est pas une clé de chiffrement valide : {exc}") from exc

    existing = resolved_vault.get_password(_KEY_PROFILE_ID)
    if existing and not overwrite:
        raise EncryptionKeyAlreadyConfiguredError(
            "Une clé de chiffrement est déjà configurée sur ce poste. Confirmez explicitement son "
            "remplacement si vous souhaitez malgré tout importer cette nouvelle clé — toute archive "
            "déjà chiffrée avec la clé actuelle deviendrait alors illisible sur ce poste."
        )

    resolved_vault.set_password(_KEY_PROFILE_ID, candidate_key.decode("ascii"))


def test_key_against_archive(archive_path: Path, *, vault: Optional[CredentialVault] = None) -> bool:
    """Vérifie que la clé actuellement configurée sur ce poste permet bien
    de déchiffrer ``archive_path`` — ``True``/``False``, jamais
    d'exception : destinée à une vérification ponctuelle demandée
    explicitement par l'utilisateur (ex. juste après un import de clé),
    jamais à un usage en masse. La copie déchiffrée transitoire est
    systématiquement supprimée, que la vérification réussisse ou non."""
    try:
        temp_path = decrypt_file_to_temp(archive_path, vault=vault)
    except ArchiveEncryptionError:
        return False
    temp_path.unlink(missing_ok=True)
    return True


def decrypt_file_to_temp(path: Path, *, vault: Optional[CredentialVault] = None) -> Path:
    """Déchiffre ``path`` (archive chiffrée) vers un nouveau fichier
    temporaire, dont le chemin est retourné — l'original n'est jamais
    modifié ni supprimé ; l'appelant est responsable de supprimer le
    fichier temporaire une fois son usage terminé (restauration, test
    d'intégrité, etc.). Lève :class:`ArchiveEncryptionError` si le jeton
    n'est pas authentique (mauvaise clé, ou archive corrompue/modifiée
    depuis son chiffrement) — jamais une exception technique brute de
    ``cryptography``. Lève :class:`NoEncryptionKeyConfiguredError`
    (mission corrective, §3.12) si aucune clé n'est configurée sur ce
    poste — jamais une clé générée à la place, qui ne pourrait de toute
    façon jamais déchiffrer quoi que ce soit."""
    key = require_existing_encryption_key(vault)
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
