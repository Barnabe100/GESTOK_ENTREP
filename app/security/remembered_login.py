"""Mémorisation « Se souvenir de moi » (phase amélioration UX, point 1).

Jamais confondu avec la configuration de connexion PostgreSQL
(``app.config.db_config_store``) : fichier séparé
(:data:`REMEMBERED_LOGIN_FILENAME`, dans ``Settings.data_dir``), coffre
séparé (``app.security.credential_vault.get_login_credential_vault`` —
jamais ``get_credential_vault``, réservé à PostgreSQL). Ce fichier local ne
contient **jamais** de mot de passe — uniquement le nom d'utilisateur
mémorisé (non secret), qui sert de ``profile_id`` pour retrouver le mot de
passe correspondant dans le coffre dédié. Le mot de passe lui-même n'existe
donc jamais ailleurs que dans ce coffre.

Tolérance aux fichiers absents/corrompus, même principe que
``app.config.db_config_store`` : toute lecture invalide (JSON illisible,
champ manquant, champ interdit) est traitée comme « rien de mémorisé »,
jamais une exception propagée — un poste sans ce fichier (toute
installation avant ce point) continue de fonctionner à l'identique.

Indisponibilité du coffre (hors Windows, ou Windows Credential Manager
inaccessible) : :func:`remember_login`/:func:`forget_remembered_login`
peuvent lever :class:`CredentialVaultUnavailableError` — à l'appelant
(``LoginWindow``) d'expliquer le problème et de continuer à permettre une
connexion manuelle, jamais d'interrompre l'authentification elle-même, déjà
réussie à ce stade. :func:`get_remembered_password` ne lève jamais : un
coffre indisponible y est équivalent à « rien de mémorisé »."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from app.security.credential_vault import get_login_credential_vault
from app.utils.exceptions import CredentialVaultUnavailableError
from app.utils.logging_config import get_logger

logger = get_logger("security.remembered_login")

REMEMBERED_LOGIN_FILENAME = "remembered_login.json"

# Jamais autorisés dans ce fichier : une écriture manuelle erronée (ou un
# fichier d'une version future incompatible) contenant un de ces champs
# invalide tout le contenu plutôt que d'être silencieusement ignorée — voir
# la même règle dans app.config.db_config_store.
_FORBIDDEN_KEYS = ("password", "mot_de_passe", "secret", "token")


def _file_path(data_dir: Path) -> Path:
    return data_dir / REMEMBERED_LOGIN_FILENAME


def _read_remembered_username(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Fichier d'identifiant mémorisé illisible, ignoré : %s", exc)
        return None
    if not isinstance(raw, dict):
        return None
    for forbidden_key in _FORBIDDEN_KEYS:
        if forbidden_key in raw:
            logger.warning(
                "Fichier d'identifiant mémorisé contient un champ interdit (%r), ignoré.", forbidden_key
            )
            return None
    username = raw.get("username")
    if not isinstance(username, str) or not username.strip():
        return None
    return username.strip()


def _write_remembered_username(path: Path, username: str) -> None:
    """Écriture atomique (même principe que
    ``app.config.db_config_store.write_db_config_file_atomic``) : jamais
    de fichier partiellement écrit visible par une lecture concurrente."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{REMEMBERED_LOGIN_FILENAME}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"username": username}, handle)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def get_remembered_username(data_dir: Path) -> Optional[str]:
    """Nom d'utilisateur mémorisé pour préremplir l'écran de connexion, ou
    ``None`` si rien n'est mémorisé (jamais une erreur)."""
    return _read_remembered_username(_file_path(data_dir))


def get_remembered_password(data_dir: Path, username: str) -> Optional[str]:
    """Mot de passe mémorisé pour ``username``, ou ``None`` si rien n'est
    mémorisé — ou si le coffre est indisponible : jamais une erreur
    propagée ici, la connexion manuelle doit toujours rester possible
    (voir le mandat de ce point)."""
    try:
        return get_login_credential_vault().get_password(username)
    except CredentialVaultUnavailableError:
        return None


def remember_login(data_dir: Path, username: str, password: str) -> None:
    """Mémorise ``username``/``password`` pour la prochaine connexion.

    Le mot de passe n'est jamais écrit en clair : il est stocké
    exclusivement dans le coffre d'identifiants dédié, sous
    ``profile_id=username``. Seul ``username`` (non secret) est écrit dans
    le fichier local.

    Lève :class:`CredentialVaultUnavailableError` si le coffre est
    indisponible — rien n'est alors écrit, ni le mot de passe ni le nom
    d'utilisateur (jamais un état incohérent où le fichier promettrait un
    mot de passe absent du coffre).

    Correctif revue finale (Point 1) : si un **autre** nom d'utilisateur
    était mémorisé sur ce poste avant cet appel (ex. l'utilisateur A coche
    « Se souvenir de moi », puis l'utilisateur B fait de même sans avoir
    cliqué « Oublier » au préalable), son mot de passe deviendrait
    orphelin dans le coffre — plus jamais référencé par ce fichier, donc
    plus jamais retrouvable ni effaçable depuis l'IHM. Il est donc
    supprimé ici, mais seulement après que la nouvelle mémorisation a
    réellement réussi, et seulement s'il s'agit bien de l'ancien nom
    référencé par CE fichier (jamais un nom d'utilisateur quelconque pris
    ailleurs) — jamais les identifiants d'un utilisateur sans rapport avec
    cette opération. Un échec de ce nettoyage (coffre devenu indisponible
    entre les deux appels) n'est jamais remonté à l'appelant : la nouvelle
    mémorisation a déjà réussi, elle ne doit jamais être remise en cause
    par un problème concernant l'ancienne — au pire, l'ancien secret reste
    orphelin, exactement comme avant ce correctif, jamais un cas pire."""
    path = _file_path(data_dir)
    previous_username = _read_remembered_username(path)

    get_login_credential_vault().set_password(username, password)
    _write_remembered_username(path, username)

    if previous_username is not None and previous_username != username:
        try:
            get_login_credential_vault().delete_password(previous_username)
        except CredentialVaultUnavailableError as exc:
            logger.warning(
                "Nouveaux identifiants mémorisés pour %r, mais l'ancien secret mémorisé "
                "(profil %r) n'a pas pu être supprimé du coffre (%s) : il peut rester "
                "orphelin dans le coffre d'identifiants Windows.",
                username, previous_username, exc,
            )


def forget_remembered_login(data_dir: Path, username: Optional[str] = None) -> None:
    """Supprime les identifiants mémorisés : le mot de passe du coffre
    (pour ``username`` si fourni, sinon pour le nom actuellement mémorisé
    s'il y en a un) et le fichier local. Jamais une erreur si rien n'était
    mémorisé (cohérent avec ``CredentialVault.delete_password``).

    Si le coffre est indisponible, seul le fichier local (jamais un
    secret) est tout de même supprimé : il n'aurait de toute façon jamais
    pu contenir le mot de passe correspondant."""
    path = _file_path(data_dir)
    target_username = username or _read_remembered_username(path)
    if target_username is not None:
        try:
            get_login_credential_vault().delete_password(target_username)
        except CredentialVaultUnavailableError:
            pass
    path.unlink(missing_ok=True)
