"""Tests unitaires de ``app.security.remembered_login`` (phase amélioration
UX, point 1) — complète les tests d'intégration de
``tests/test_login_window.py`` sur les cas limites du fichier local
(jamais un secret) : absence, corruption, champ interdit.
"""
from __future__ import annotations

from typing import Optional

import pytest

from app.security.remembered_login import (
    forget_remembered_login,
    get_remembered_password,
    get_remembered_username,
    remember_login,
)
from app.utils.exceptions import CredentialVaultUnavailableError


class _FakeLoginCredentialVault:
    def __init__(self) -> None:
        self.passwords: dict[str, str] = {}

    def get_password(self, profile_id: str) -> Optional[str]:
        return self.passwords.get(profile_id)

    def set_password(self, profile_id: str, password: str) -> None:
        self.passwords[profile_id] = password

    def delete_password(self, profile_id: str) -> None:
        self.passwords.pop(profile_id, None)


@pytest.fixture()
def fake_vault(monkeypatch: pytest.MonkeyPatch) -> _FakeLoginCredentialVault:
    vault = _FakeLoginCredentialVault()
    monkeypatch.setattr("app.security.remembered_login.get_login_credential_vault", lambda: vault)
    return vault


def test_get_remembered_username_returns_none_when_file_absent(tmp_path) -> None:
    assert get_remembered_username(tmp_path) is None


def test_get_remembered_username_returns_none_on_corrupted_json(tmp_path) -> None:
    (tmp_path / "remembered_login.json").write_text("{not valid json", encoding="utf-8")
    assert get_remembered_username(tmp_path) is None


def test_get_remembered_username_returns_none_when_username_field_missing(tmp_path) -> None:
    (tmp_path / "remembered_login.json").write_text("{}", encoding="utf-8")
    assert get_remembered_username(tmp_path) is None


def test_get_remembered_username_rejects_file_containing_a_forbidden_key(tmp_path) -> None:
    """Un fichier qui contiendrait malgré tout un mot de passe (écriture
    manuelle erronée, version future incompatible) est rejeté en bloc,
    jamais partiellement accepté."""
    (tmp_path / "remembered_login.json").write_text(
        '{"username": "u", "password": "jamais-cense-etre-la"}', encoding="utf-8"
    )
    assert get_remembered_username(tmp_path) is None


def test_remember_login_writes_only_the_username_never_the_password(tmp_path, fake_vault) -> None:
    remember_login(tmp_path, "alice", "SecretPassword!23")
    content = (tmp_path / "remembered_login.json").read_text(encoding="utf-8")
    assert "SecretPassword!23" not in content
    assert get_remembered_username(tmp_path) == "alice"
    assert fake_vault.passwords["alice"] == "SecretPassword!23"


def test_get_remembered_password_round_trips_through_the_vault(tmp_path, fake_vault) -> None:
    remember_login(tmp_path, "bob", "AutrePassword!45")
    assert get_remembered_password(tmp_path, "bob") == "AutrePassword!45"


def test_get_remembered_password_returns_none_for_unknown_user(tmp_path, fake_vault) -> None:
    assert get_remembered_password(tmp_path, "personne") is None


def test_forget_remembered_login_removes_both_file_and_vault_entry(tmp_path, fake_vault) -> None:
    remember_login(tmp_path, "carla", "Password!67")
    forget_remembered_login(tmp_path)
    assert get_remembered_username(tmp_path) is None
    assert "carla" not in fake_vault.passwords


def test_forget_remembered_login_is_a_noop_when_nothing_is_remembered(tmp_path, fake_vault) -> None:
    forget_remembered_login(tmp_path)  # ne lève jamais.
    assert get_remembered_username(tmp_path) is None


# -- correctif revue finale (Point 1) : rétention d'un secret orphelin -------
#
# Scénario reproduit explicitement : l'utilisateur A active « Se souvenir de
# moi » (son mot de passe est conservé dans le coffre), puis l'utilisateur B
# active cette option sur le même poste SANS avoir cliqué « Oublier » au
# préalable — le fichier local référence désormais B, mais avant ce
# correctif le mot de passe de A restait indéfiniment dans le coffre,
# orphelin (plus jamais référencé, donc plus jamais retrouvable ni
# effaçable depuis l'IHM).


def test_remember_login_switching_user_deletes_the_previous_users_vault_entry(tmp_path, fake_vault) -> None:
    """Reproduction explicite du scénario A -> B : après que B a mémorisé
    ses identifiants, le mot de passe de A ne doit plus être présent dans
    le coffre."""
    remember_login(tmp_path, "A", "PasswordA!23")
    assert fake_vault.passwords.get("A") == "PasswordA!23"

    remember_login(tmp_path, "B", "PasswordB!45")

    assert "A" not in fake_vault.passwords, "le secret de A est devenu orphelin : il aurait dû être supprimé."
    assert fake_vault.passwords.get("B") == "PasswordB!45"
    assert get_remembered_username(tmp_path) == "B"


def test_remember_login_with_the_same_username_again_keeps_its_own_entry(tmp_path, fake_vault) -> None:
    """Reconfirmer « Se souvenir de moi » pour le MÊME utilisateur ne doit
    jamais supprimer son propre secret qui vient d'être (ré)écrit."""
    remember_login(tmp_path, "A", "PasswordA!23")
    remember_login(tmp_path, "A", "NouveauPasswordA!99")

    assert fake_vault.passwords.get("A") == "NouveauPasswordA!99"


def test_remember_login_switching_user_never_touches_unrelated_vault_entries(tmp_path, fake_vault) -> None:
    """Un secret présent dans le coffre mais jamais référencé par CE
    fichier (ex. mémorisé sur un autre poste, ou par un mécanisme hors de
    ce module) ne doit jamais être supprimé par ce nettoyage — seul
    l'ancien nom explicitement lu dans le fichier local est concerné."""
    fake_vault.passwords["sans-rapport"] = "PasswordSansRapport!00"

    remember_login(tmp_path, "A", "PasswordA!23")
    remember_login(tmp_path, "B", "PasswordB!45")

    assert fake_vault.passwords.get("sans-rapport") == "PasswordSansRapport!00"


def test_remember_login_switching_user_survives_vault_unavailable_during_cleanup(
    tmp_path, fake_vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un échec du coffre lors du nettoyage de l'ancien secret (ex. coffre
    devenu indisponible entre les deux appels) ne doit jamais remettre en
    cause la nouvelle mémorisation, déjà réussie à ce stade."""
    remember_login(tmp_path, "A", "PasswordA!23")

    original_delete = fake_vault.delete_password

    def _failing_delete(profile_id: str) -> None:
        if profile_id == "A":
            raise CredentialVaultUnavailableError("coffre indisponible (simulé)")
        original_delete(profile_id)

    monkeypatch.setattr(fake_vault, "delete_password", _failing_delete)

    remember_login(tmp_path, "B", "PasswordB!45")  # ne doit jamais lever.

    assert get_remembered_username(tmp_path) == "B"
    assert fake_vault.passwords.get("B") == "PasswordB!45"
    # Le nettoyage a échoué : le secret de A reste orphelin, mais ceci ne
    # doit jamais empêcher B d'être correctement mémorisé.
    assert fake_vault.passwords.get("A") == "PasswordA!23"
