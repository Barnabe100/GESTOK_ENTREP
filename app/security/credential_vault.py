"""Coffre d'identifiants pour le mot de passe PostgreSQL (Lot D).

Contrat de sécurité (non négociable, voir le mandat de ce lot) :

- Le mot de passe PostgreSQL n'est **jamais** écrit en clair dans un
  fichier, une base de données, les journaux ou un message d'erreur.
- En production (poste Windows), le seul mécanisme de stockage autorisé
  est Windows Credential Manager, via la bibliothèque ``keyring`` — et
  seulement après vérification explicite que le backend réellement actif
  est bien ``keyring.backends.Windows.WinVaultKeyring``. Si ce backend
  n'est pas celui effectivement sélectionné par ``keyring`` (coffre
  indisponible, bibliothèque système manquante, tout autre backend
  auto-détecté), l'opération est **refusée explicitement** —
  :class:`CredentialVaultUnavailableError` — jamais un repli silencieux
  vers un autre backend ``keyring`` (ex. un fichier chiffré portable, un
  trousseau alternatif) ni vers un stockage en clair.
- En développement/test sous Linux, ce module n'est **pas** utilisé pour
  obtenir le mot de passe : ``PostgreSQLConnectionConfig.resolve_password``
  continue d'utiliser la variable d'environnement
  ``STOCKMANAGER_TEST_PG_PASSWORD``/``STOCKMANAGER_DB_PASSWORD`` (mécanisme
  Lot A, inchangé) tant que ``credential_key`` n'est pas renseigné. Ce
  module n'est donc jamais sollicité par les tests Linux pour un usage réel
  — seule son interface est testée (vérification explicite du backend,
  refus propre hors Windows), jamais comme un mécanisme de secours pour
  l'application Windows.

Incohérence JSON / coffre (point à documenter, §4.4 du mandat) : le fichier
de configuration externe (``app.config.db_config_store``) peut référencer
un ``credential_key`` pour lequel le coffre ne détient plus aucun secret
(coffre vidé manuellement par l'utilisateur, profil copié d'un autre poste,
etc.). Ce module ne tente alors aucune réconciliation automatique :
``get_password`` retourne ``None`` (absence), et
``PostgreSQLConnectionConfig.resolve_password`` lève une
:class:`ValueError` explicite — exactement le même comportement que
lorsque la variable d'environnement Lot A est absente. La résolution de
cette incohérence (reconfigurer le mot de passe via l'écran
d'administration) reste une action explicite de l'administrateur, jamais
une tentative de deviner ou de recréer le secret.
"""
from __future__ import annotations

import sys
from typing import Optional, Protocol, runtime_checkable

from app.utils.exceptions import CredentialVaultUnavailableError
from app.utils.logging_config import get_logger

logger = get_logger("security.credential_vault")

# Nom de « service » keyring (regroupe toutes les entrées StockManager dans
# le coffre, sans jamais les confondre avec un autre logiciel) — jamais
# modifié après une première version publiée : en changer casserait la
# correspondance avec les ``credential_key`` déjà enregistrés sur les
# postes existants.
_KEYRING_SERVICE_NAME = "StockManager Desktop - PostgreSQL"


@runtime_checkable
class CredentialVault(Protocol):
    """Interface du coffre d'identifiants — sépare la logique métier
    (``app.services``) de l'implémentation concrète (Windows Credential
    Manager via ``keyring``, ci-dessous). ``profile_id`` est l'identifiant
    stable et non secret du profil de connexion (voir
    ``app.config.db_config_store.PostgreSQLProfile.credential_key``),
    jamais une donnée sensible elle-même."""

    def get_password(self, profile_id: str) -> Optional[str]:
        """Retourne le mot de passe enregistré pour ce profil, ou ``None``
        s'il n'y en a aucun (jamais une chaîne vide pour signifier
        l'absence)."""

    def set_password(self, profile_id: str, password: str) -> None:
        """Enregistre (ou remplace) le mot de passe de ce profil."""

    def delete_password(self, profile_id: str) -> None:
        """Supprime le mot de passe de ce profil, si présent. Sans effet
        (jamais une erreur) si aucun mot de passe n'était enregistré."""


def _verified_windows_keyring_backend():
    """Importe ``keyring``, vérifie explicitement que le backend réellement
    actif est ``keyring.backends.Windows.WinVaultKeyring``, et retourne le
    module ``keyring`` prêt à l'emploi.

    Lève :class:`CredentialVaultUnavailableError` dans tous les autres cas
    (bibliothèque absente, backend différent) — jamais un import silencieux
    d'un autre backend disponible sur la machine."""
    try:
        import keyring
    except ImportError as exc:
        raise CredentialVaultUnavailableError(
            "Le module d'accès au coffre d'identifiants Windows n'est pas installé "
            "sur ce poste. Aucun mot de passe ne peut être enregistré ni lu."
        ) from exc

    try:
        from keyring.backends.Windows import WinVaultKeyring
    except ImportError as exc:
        raise CredentialVaultUnavailableError(
            "Le backend Windows Credential Manager n'est pas disponible sur ce poste "
            "(dépendance système manquante). Aucun mot de passe ne peut être "
            "enregistré ni lu via un autre mécanisme."
        ) from exc

    active_backend = keyring.get_keyring()
    if not isinstance(active_backend, WinVaultKeyring):
        raise CredentialVaultUnavailableError(
            "Le coffre d'identifiants actif n'est pas Windows Credential Manager "
            f"(backend détecté : {type(active_backend).__name__}). Par sécurité, "
            "aucun mot de passe ne sera enregistré ni lu via ce backend non autorisé."
        )

    return keyring


class WindowsCredentialVault:
    """Implémentation ``CredentialVault`` pour Windows Credential Manager,
    via ``keyring`` — n'accepte de fonctionner qu'avec le backend
    ``WinVaultKeyring`` réellement actif, vérifié à chaque opération (jamais
    seulement à la construction : un coffre déjà ouvert pourrait devenir
    indisponible entre deux appels, ex. service Windows arrêté)."""

    def get_password(self, profile_id: str) -> Optional[str]:
        keyring = _verified_windows_keyring_backend()
        try:
            return keyring.get_password(_KEYRING_SERVICE_NAME, profile_id)
        except Exception as exc:
            # Jamais le mot de passe (il n'a pas encore été résolu ici) ni
            # aucun détail de bas niveau potentiellement sensible dans le
            # message exposé à l'appelant — seule l'exception technique
            # complète part en journal (sans secret : aucune valeur
            # manipulée par ce bloc n'est un mot de passe).
            logger.error("Échec de lecture du coffre d'identifiants pour le profil %r : %s", profile_id, exc)
            raise CredentialVaultUnavailableError(
                "Impossible de lire le coffre d'identifiants Windows. Vérifiez que le "
                "service Windows Credential Manager est disponible sur ce poste."
            ) from exc

    def set_password(self, profile_id: str, password: str) -> None:
        keyring = _verified_windows_keyring_backend()
        try:
            keyring.set_password(_KEYRING_SERVICE_NAME, profile_id, password)
        except Exception as exc:
            logger.error("Échec d'écriture du coffre d'identifiants pour le profil %r : %s", profile_id, exc)
            raise CredentialVaultUnavailableError(
                "Impossible d'enregistrer le mot de passe dans le coffre d'identifiants "
                "Windows. Vérifiez que le service Windows Credential Manager est "
                "disponible sur ce poste."
            ) from exc

    def delete_password(self, profile_id: str) -> None:
        keyring = _verified_windows_keyring_backend()
        try:
            keyring.delete_password(_KEYRING_SERVICE_NAME, profile_id)
        except keyring.errors.PasswordDeleteError:
            # Rien n'était enregistré pour ce profil : pas une erreur (voir
            # contrat de l'interface CredentialVault.delete_password).
            pass
        except Exception as exc:
            logger.error("Échec de suppression dans le coffre d'identifiants pour le profil %r : %s", profile_id, exc)
            raise CredentialVaultUnavailableError(
                "Impossible de supprimer le mot de passe du coffre d'identifiants "
                "Windows. Vérifiez que le service Windows Credential Manager est "
                "disponible sur ce poste."
            ) from exc


def get_credential_vault() -> CredentialVault:
    """Point d'entrée unique pour obtenir le coffre d'identifiants actif.

    Décision par plateforme, prise une fois, jamais un repli : hors
    Windows, aucun coffre n'est proposé — le développement/test Linux
    utilise exclusivement la variable d'environnement Lot A (voir
    ``PostgreSQLConnectionConfig.resolve_password``, jamais ce module)."""
    if sys.platform != "win32":
        raise CredentialVaultUnavailableError(
            "Le coffre d'identifiants sécurisé n'est disponible que sous Windows. "
            "En développement/test, utilisez la variable d'environnement "
            "STOCKMANAGER_DB_PASSWORD (ou STOCKMANAGER_TEST_PG_PASSWORD pour les "
            "tests PostgreSQL) plutôt qu'un profil associé à un credential_key."
        )
    return WindowsCredentialVault()
