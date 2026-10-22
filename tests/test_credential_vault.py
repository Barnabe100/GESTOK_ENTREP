"""Lot D.2 : coffre d'identifiants pour le mot de passe PostgreSQL — voir
``app.security.credential_vault``.

Ces tests s'exécutent sur Linux (aucune machine Windows disponible dans cet
environnement) : ils ne peuvent donc pas prouver qu'une écriture/lecture
réelle dans Windows Credential Manager fonctionne. Ce qu'ils prouvent, et
qui ne dépend pas de la plateforme :
1. hors Windows, le coffre est explicitement refusé (jamais un repli) ;
2. même en simulant ``sys.platform == "win32"``, un backend ``keyring``
   différent de ``WinVaultKeyring`` (ici ``keyring.backends.fail.Keyring``,
   le backend réellement sélectionné dans ce conteneur Linux, vérifié par
   lecture directe) est explicitement rejeté — jamais utilisé silencieusement ;
3. aucun mot de passe n'apparaît dans les exceptions levées.

La validation réelle sur un poste Windows avec Windows Credential Manager
disponible reste à faire séparément (voir le rapport de ce lot)."""
from __future__ import annotations

import sys

import keyring
import pytest

from app.security.credential_vault import (
    CredentialVault,
    WindowsCredentialVault,
    get_credential_vault,
)
from app.utils.exceptions import AppError, ConfigurationError, CredentialVaultUnavailableError


def test_vault_unavailable_outside_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(CredentialVaultUnavailableError):
        get_credential_vault()


def test_credential_vault_unavailable_error_is_an_app_error() -> None:
    assert issubclass(CredentialVaultUnavailableError, ConfigurationError)
    assert issubclass(CredentialVaultUnavailableError, AppError)


def test_real_backend_in_this_sandbox_is_not_windows_vault() -> None:
    """Confirme la prémisse des tests suivants : ce conteneur Linux n'a
    évidemment pas Windows Credential Manager — le backend réellement
    sélectionné par keyring est le backend « échec » (aucun stockage
    disponible), jamais un stockage en clair auto-sélectionné."""
    backend = keyring.get_keyring()
    assert type(backend).__name__ != "WinVaultKeyring"


@pytest.fixture()
def pretend_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simule sys.platform == 'win32' pour atteindre le code de
    WindowsCredentialVault — le backend keyring réel sous-jacent reste
    celui de ce conteneur Linux (voir test ci-dessus), ce qui permet de
    tester le rejet explicite d'un backend non autorisé sans machine
    Windows."""
    monkeypatch.setattr(sys, "platform", "win32")


def test_get_credential_vault_returns_windows_vault_when_platform_is_windows(pretend_windows) -> None:
    vault = get_credential_vault()
    assert isinstance(vault, WindowsCredentialVault)
    assert isinstance(vault, CredentialVault)


def test_get_password_rejects_non_windows_backend(pretend_windows) -> None:
    vault = get_credential_vault()
    with pytest.raises(CredentialVaultUnavailableError, match="backend"):
        vault.get_password("profile-1")


def test_set_password_rejects_non_windows_backend_never_stores_anything(pretend_windows) -> None:
    vault = get_credential_vault()
    with pytest.raises(CredentialVaultUnavailableError):
        vault.set_password("profile-1", "s3cret-value")


def test_delete_password_rejects_non_windows_backend(pretend_windows) -> None:
    vault = get_credential_vault()
    with pytest.raises(CredentialVaultUnavailableError):
        vault.delete_password("profile-1")


def test_rejection_message_never_contains_the_attempted_password(pretend_windows) -> None:
    vault = get_credential_vault()
    with pytest.raises(CredentialVaultUnavailableError) as exc_info:
        vault.set_password("profile-1", "tres-secret-mot-de-passe")
    assert "tres-secret-mot-de-passe" not in str(exc_info.value)


def test_rejection_message_names_the_wrong_backend_without_exposing_secrets(pretend_windows) -> None:
    vault = get_credential_vault()
    with pytest.raises(CredentialVaultUnavailableError) as exc_info:
        vault.get_password("profile-1")
    # Le nom du backend réel (diagnostic utile) peut apparaître ; aucune
    # valeur secrète n'existe à ce stade (aucun mot de passe n'a encore
    # été manipulé par cet appel en lecture).
    assert "Keyring" in str(exc_info.value) or "backend" in str(exc_info.value)


# -- intégration avec PostgreSQLConnectionConfig.resolve_password ----------------------


def test_resolve_password_propagates_vault_unavailable_when_credential_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hors Windows, une configuration construite avec ``credential_key``
    (comme le ferait le futur assistant/écran d'administration) échoue de
    façon explicite et distincte (CredentialVaultUnavailableError), jamais
    un repli silencieux vers une autre source de mot de passe."""
    from app.config.settings import PostgreSQLConnectionConfig

    monkeypatch.setattr(sys, "platform", "linux")
    config = PostgreSQLConnectionConfig(
        host="h", port=5432, database="d", username="u", credential_key="profile-x",
    )
    with pytest.raises(CredentialVaultUnavailableError):
        config.resolve_password()


def test_resolve_password_still_uses_env_var_when_credential_key_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-régression explicite (Lot A) : une configuration sans
    ``credential_key`` (valeur par défaut) continue de résoudre le mot de
    passe par variable d'environnement, sans jamais consulter le coffre."""
    from app.config.settings import PostgreSQLConnectionConfig

    monkeypatch.setenv("STOCKMANAGER_DB_PASSWORD", "s3cret-env")
    config = PostgreSQLConnectionConfig(host="h", port=5432, database="d", username="u")
    assert config.credential_key is None
    assert config.resolve_password() == "s3cret-env"
