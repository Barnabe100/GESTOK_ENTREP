"""Tests de app.services.backups.archive_encryption — un coffre en mémoire
(``_FakeVault``) remplace le coffre d'identifiants Windows réel, injecté
explicitement (voir la docstring de module d'archive_encryption.py) : ces
tests valident la logique de chiffrement/déchiffrement elle-même,
indépendamment de Windows Credential Manager (couvert séparément par
tests/test_credential_vault.py)."""
from __future__ import annotations

from typing import Optional

import pytest

from app.services.backups import archive_encryption
from app.services.backups.archive_encryption import ArchiveEncryptionError


class _FakeVault:
    """Implémente le protocole ``CredentialVault`` en mémoire — jamais
    utilisé en dehors des tests."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get_password(self, profile_id: str) -> Optional[str]:
        return self._store.get(profile_id)

    def set_password(self, profile_id: str, password: str) -> None:
        self._store[profile_id] = password

    def delete_password(self, profile_id: str) -> None:
        self._store.pop(profile_id, None)


def test_ensure_encryption_key_generates_once_and_reuses(tmp_path) -> None:
    vault = _FakeVault()

    first = archive_encryption.ensure_encryption_key(vault)
    second = archive_encryption.ensure_encryption_key(vault)

    assert first == second
    assert len(first) == 44  # clé Fernet : 32 octets encodés base64 url-safe


def test_different_vaults_produce_different_keys() -> None:
    key_a = archive_encryption.ensure_encryption_key(_FakeVault())
    key_b = archive_encryption.ensure_encryption_key(_FakeVault())

    assert key_a != key_b


def test_encrypt_then_decrypt_round_trips_original_content(tmp_path) -> None:
    vault = _FakeVault()
    archive = tmp_path / "stockmanager_backup_20260101_020000.db"
    original_content = b"contenu binaire de sauvegarde \x00\x01\xff"
    archive.write_bytes(original_content)

    archive_encryption.encrypt_file_in_place(archive, vault=vault)
    assert archive.read_bytes() != original_content  # bien chiffré sur place

    decrypted_path = archive_encryption.decrypt_file_to_temp(archive, vault=vault)
    try:
        assert decrypted_path.read_bytes() == original_content
    finally:
        decrypted_path.unlink()


def test_encrypt_in_place_preserves_file_name(tmp_path) -> None:
    vault = _FakeVault()
    archive = tmp_path / "stockmanager_backup_20260101_020000.db"
    archive.write_bytes(b"contenu")

    archive_encryption.encrypt_file_in_place(archive, vault=vault)

    assert archive.exists()
    assert archive.name == "stockmanager_backup_20260101_020000.db"


def test_decrypt_with_wrong_key_raises_archive_encryption_error(tmp_path) -> None:
    archive = tmp_path / "archive.db"
    archive.write_bytes(b"contenu original")
    archive_encryption.encrypt_file_in_place(archive, vault=_FakeVault())

    with pytest.raises(ArchiveEncryptionError):
        archive_encryption.decrypt_file_to_temp(archive, vault=_FakeVault())  # coffre différent -> clé différente


def test_decrypt_corrupted_archive_raises_archive_encryption_error(tmp_path) -> None:
    vault = _FakeVault()
    archive = tmp_path / "archive.db"
    archive.write_bytes(b"contenu original")
    archive_encryption.encrypt_file_in_place(archive, vault=vault)
    # Corrompt le jeton chiffré après coup (support défaillant, altération).
    archive.write_bytes(archive.read_bytes()[:-5] + b"xxxxx")

    with pytest.raises(ArchiveEncryptionError):
        archive_encryption.decrypt_file_to_temp(archive, vault=vault)


def test_decrypt_to_temp_never_modifies_the_original_encrypted_file(tmp_path) -> None:
    vault = _FakeVault()
    archive = tmp_path / "archive.db"
    archive.write_bytes(b"contenu original")
    archive_encryption.encrypt_file_in_place(archive, vault=vault)
    encrypted_bytes_before = archive.read_bytes()

    decrypted_path = archive_encryption.decrypt_file_to_temp(archive, vault=vault)
    decrypted_path.unlink()

    assert archive.read_bytes() == encrypted_bytes_before
