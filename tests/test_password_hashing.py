import pytest

from app.security.password_hashing import hash_password, verify_password


def test_hash_password_never_returns_plaintext() -> None:
    hashed = hash_password("SuperSecret!23")
    assert hashed != "SuperSecret!23"
    assert hashed.startswith("$argon2")


def test_verify_password_accepts_correct_password() -> None:
    hashed = hash_password("SuperSecret!23")
    assert verify_password("SuperSecret!23", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("SuperSecret!23")
    assert verify_password("MauvaisMotDePasse", hashed) is False


def test_hash_password_rejects_empty_password() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_hash_password_is_salted_and_non_deterministic() -> None:
    first = hash_password("SuperSecret!23")
    second = hash_password("SuperSecret!23")
    assert first != second
    assert verify_password("SuperSecret!23", first) is True
    assert verify_password("SuperSecret!23", second) is True
