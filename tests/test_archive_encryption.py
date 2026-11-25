"""Tests de app.services.backups.archive_encryption — un coffre en mémoire
(``_FakeVault``) remplace le coffre d'identifiants Windows réel, injecté
explicitement (voir la docstring de module d'archive_encryption.py) : ces
tests valident la logique de chiffrement/déchiffrement elle-même,
indépendamment de Windows Credential Manager (couvert séparément par
tests/test_credential_vault.py)."""
from __future__ import annotations

import tempfile
from pathlib import Path
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


# -- mission corrective §3.12 : ne jamais générer de clé au déchiffrement --------


def test_decrypt_without_any_key_raises_dedicated_error_without_generating_one(tmp_path) -> None:
    source_vault = _FakeVault()
    archive = tmp_path / "archive.db"
    archive.write_bytes(b"contenu original")
    archive_encryption.encrypt_file_in_place(archive, vault=source_vault)

    empty_vault = _FakeVault()
    with pytest.raises(archive_encryption.NoEncryptionKeyConfiguredError):
        archive_encryption.decrypt_file_to_temp(archive, vault=empty_vault)

    # Aucune clé n'a été générée sur ce coffre vide à cette occasion.
    assert empty_vault.get_password("archive-encryption-key") is None


def test_require_existing_encryption_key_never_creates_one(tmp_path) -> None:
    vault = _FakeVault()

    with pytest.raises(archive_encryption.NoEncryptionKeyConfiguredError):
        archive_encryption.require_existing_encryption_key(vault)

    assert vault.get_password("archive-encryption-key") is None


def test_require_existing_encryption_key_returns_it_when_present() -> None:
    vault = _FakeVault()
    created = archive_encryption.ensure_encryption_key(vault)

    assert archive_encryption.require_existing_encryption_key(vault) == created


# -- mission corrective §3.1 : transfert de la clé vers un autre ordinateur ------


def test_export_then_import_on_a_second_vault_allows_decrypting_the_same_archive(tmp_path) -> None:
    """Scénario central du mandat correctif : une archive chiffrée sur
    « l'ancien poste » (premier coffre) doit rester déchiffrable sur « le
    nouveau poste » (second coffre, totalement vide au départ) après
    export puis import de la clé — jamais le même coffre pour les deux."""
    old_computer_vault = _FakeVault()
    archive = tmp_path / "stockmanager_backup_20260101_020000.db"
    original_content = b"donnees de l'ancien poste"
    archive.write_bytes(original_content)
    archive_encryption.encrypt_file_in_place(archive, vault=old_computer_vault)

    transfer_file = tmp_path / "cle_de_transfert.json"
    archive_encryption.export_encryption_key(transfer_file, "mot-de-passe-solide", vault=old_computer_vault)

    new_computer_vault = _FakeVault()
    archive_encryption.import_encryption_key(transfer_file, "mot-de-passe-solide", vault=new_computer_vault)

    decrypted_path = archive_encryption.decrypt_file_to_temp(archive, vault=new_computer_vault)
    try:
        assert decrypted_path.read_bytes() == original_content
    finally:
        decrypted_path.unlink()


def test_export_never_stores_the_password_in_clear(tmp_path) -> None:
    vault = _FakeVault()
    archive_encryption.ensure_encryption_key(vault)
    transfer_file = tmp_path / "cle_de_transfert.json"

    archive_encryption.export_encryption_key(transfer_file, "mot-de-passe-tres-secret", vault=vault)

    assert "mot-de-passe-tres-secret" not in transfer_file.read_text(encoding="utf-8")


def test_export_without_any_key_raises_no_encryption_key_configured_error(tmp_path) -> None:
    vault = _FakeVault()
    transfer_file = tmp_path / "cle_de_transfert.json"

    with pytest.raises(archive_encryption.NoEncryptionKeyConfiguredError):
        archive_encryption.export_encryption_key(transfer_file, "mot-de-passe", vault=vault)

    assert not transfer_file.exists()


def test_export_requires_a_password(tmp_path) -> None:
    vault = _FakeVault()
    archive_encryption.ensure_encryption_key(vault)
    transfer_file = tmp_path / "cle_de_transfert.json"

    with pytest.raises(archive_encryption.KeyTransferError):
        archive_encryption.export_encryption_key(transfer_file, "", vault=vault)


def test_export_refuses_the_configured_backup_folder_as_destination(tmp_path) -> None:
    vault = _FakeVault()
    archive_encryption.ensure_encryption_key(vault)
    backups_folder = tmp_path / "backups"
    backups_folder.mkdir()
    transfer_file = backups_folder / "cle_de_transfert.json"

    with pytest.raises(archive_encryption.KeyTransferError):
        archive_encryption.export_encryption_key(
            transfer_file, "mot-de-passe", vault=vault, backup_destination=backups_folder,
        )

    assert not transfer_file.exists()


def test_export_allows_a_different_folder_than_backups(tmp_path) -> None:
    vault = _FakeVault()
    archive_encryption.ensure_encryption_key(vault)
    backups_folder = tmp_path / "backups"
    backups_folder.mkdir()
    transfer_file = tmp_path / "ailleurs" / "cle_de_transfert.json"

    archive_encryption.export_encryption_key(
        transfer_file, "mot-de-passe", vault=vault, backup_destination=backups_folder,
    )

    assert transfer_file.exists()


def test_import_with_wrong_password_raises_key_transfer_error(tmp_path) -> None:
    vault = _FakeVault()
    archive_encryption.ensure_encryption_key(vault)
    transfer_file = tmp_path / "cle_de_transfert.json"
    archive_encryption.export_encryption_key(transfer_file, "bon-mot-de-passe", vault=vault)

    with pytest.raises(archive_encryption.KeyTransferError):
        archive_encryption.import_encryption_key(transfer_file, "mauvais-mot-de-passe", vault=_FakeVault())


def test_import_with_altered_transfer_file_raises_key_transfer_error(tmp_path) -> None:
    vault = _FakeVault()
    archive_encryption.ensure_encryption_key(vault)
    transfer_file = tmp_path / "cle_de_transfert.json"
    archive_encryption.export_encryption_key(transfer_file, "mot-de-passe", vault=vault)

    import json

    data = json.loads(transfer_file.read_text(encoding="utf-8"))
    data["wrapped_key_b64"] = data["wrapped_key_b64"][:-4] + "xxxx"
    transfer_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(archive_encryption.KeyTransferError):
        archive_encryption.import_encryption_key(transfer_file, "mot-de-passe", vault=_FakeVault())


def test_import_with_missing_file_raises_key_transfer_error(tmp_path) -> None:
    with pytest.raises(archive_encryption.KeyTransferError):
        archive_encryption.import_encryption_key(tmp_path / "absent.json", "mot-de-passe", vault=_FakeVault())


def test_import_never_overwrites_existing_key_without_explicit_confirmation(tmp_path) -> None:
    old_vault = _FakeVault()
    archive_encryption.ensure_encryption_key(old_vault)
    transfer_file = tmp_path / "cle_de_transfert.json"
    archive_encryption.export_encryption_key(transfer_file, "mot-de-passe", vault=old_vault)

    destination_vault = _FakeVault()
    existing_key = archive_encryption.ensure_encryption_key(destination_vault)

    with pytest.raises(archive_encryption.EncryptionKeyAlreadyConfiguredError):
        archive_encryption.import_encryption_key(transfer_file, "mot-de-passe", vault=destination_vault)

    # La clé déjà présente n'a pas été modifiée par la tentative refusée.
    assert archive_encryption.require_existing_encryption_key(destination_vault) == existing_key


def test_import_overwrites_when_explicitly_confirmed(tmp_path) -> None:
    old_vault = _FakeVault()
    original_key = archive_encryption.ensure_encryption_key(old_vault)
    transfer_file = tmp_path / "cle_de_transfert.json"
    archive_encryption.export_encryption_key(transfer_file, "mot-de-passe", vault=old_vault)

    destination_vault = _FakeVault()
    archive_encryption.ensure_encryption_key(destination_vault)  # une autre clé, différente

    archive_encryption.import_encryption_key(
        transfer_file, "mot-de-passe", vault=destination_vault, overwrite=True,
    )

    assert archive_encryption.require_existing_encryption_key(destination_vault) == original_key


def test_import_rejects_a_transfer_file_whose_content_is_not_valid_json(tmp_path) -> None:
    transfer_file = tmp_path / "cle_de_transfert.json"
    transfer_file.write_text("ceci n'est pas du JSON", encoding="utf-8")

    with pytest.raises(archive_encryption.KeyTransferError):
        archive_encryption.import_encryption_key(transfer_file, "mot-de-passe", vault=_FakeVault())


# -- mission corrective §3.1 : vérification de la clé après import --------------


def test_key_against_archive_succeeds_with_the_right_key(tmp_path) -> None:
    vault = _FakeVault()
    archive = tmp_path / "archive.db"
    archive.write_bytes(b"contenu")
    archive_encryption.encrypt_file_in_place(archive, vault=vault)

    assert archive_encryption.test_key_against_archive(archive, vault=vault) is True


def test_key_against_archive_fails_with_the_wrong_key(tmp_path) -> None:
    archive = tmp_path / "archive.db"
    archive.write_bytes(b"contenu")
    archive_encryption.encrypt_file_in_place(archive, vault=_FakeVault())

    other_vault = _FakeVault()
    archive_encryption.ensure_encryption_key(other_vault)
    assert archive_encryption.test_key_against_archive(archive, vault=other_vault) is False


def test_key_against_archive_never_leaves_a_decrypted_temp_file(tmp_path) -> None:
    vault = _FakeVault()
    archive = tmp_path / "archive.db"
    archive.write_bytes(b"contenu")
    archive_encryption.encrypt_file_in_place(archive, vault=vault)

    before = set(Path(tempfile.gettempdir()).iterdir())
    archive_encryption.test_key_against_archive(archive, vault=vault)
    after = set(Path(tempfile.gettempdir()).iterdir())

    assert after - before == set()
