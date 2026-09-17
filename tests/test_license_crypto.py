"""Primitives cryptographiques Ed25519 pures (§2, §16)."""
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.licensing import license_crypto


def _generate_public_key_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )


def test_verify_accepts_a_valid_signature() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key_bytes = _generate_public_key_bytes(private_key)
    message = b"payload-de-licence"
    signature = private_key.sign(message)

    assert license_crypto.verify(public_key_bytes, message, signature) is True


def test_verify_rejects_a_tampered_message() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key_bytes = _generate_public_key_bytes(private_key)
    signature = private_key.sign(b"message original")

    assert license_crypto.verify(public_key_bytes, b"message modifie", signature) is False


def test_verify_rejects_signature_from_a_different_key() -> None:
    private_key = Ed25519PrivateKey.generate()
    other_private_key = Ed25519PrivateKey.generate()
    public_key_bytes = _generate_public_key_bytes(private_key)
    message = b"payload-de-licence"
    wrong_signature = other_private_key.sign(message)

    assert license_crypto.verify(public_key_bytes, message, wrong_signature) is False


def test_verify_rejects_wrong_public_key() -> None:
    private_key = Ed25519PrivateKey.generate()
    other_public_key_bytes = _generate_public_key_bytes(Ed25519PrivateKey.generate())
    message = b"payload-de-licence"
    signature = private_key.sign(message)

    assert license_crypto.verify(other_public_key_bytes, message, signature) is False


def test_verify_never_raises_on_garbage_signature_bytes() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key_bytes = _generate_public_key_bytes(private_key)

    assert license_crypto.verify(public_key_bytes, b"message", b"pas-une-vraie-signature") is False


def test_verify_never_raises_on_malformed_public_key_bytes() -> None:
    assert license_crypto.verify(b"trop-court", b"message", b"0" * 64) is False


def test_verify_rejects_empty_signature() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key_bytes = _generate_public_key_bytes(private_key)

    assert license_crypto.verify(public_key_bytes, b"message", b"") is False
