"""Structure et sérialisation canonique de la charge utile de licence (§3-4)."""
import json

import pytest

from app.models.enums import EditionLicence
from app.services.licensing.license_payload import (
    LICENSE_FORMAT_VERSION,
    LicensePayload,
    LicensePayloadError,
    canonical_json_bytes,
)


def _valid_payload_dict() -> dict:
    return {
        "license_version": LICENSE_FORMAT_VERSION,
        "license_id": "STK-0001",
        "product": "StockManager Desktop",
        "client": "Client Test",
        "edition": "STANDARD",
        "issued_at": "2026-01-01",
        "expires_at": "2027-01-01",
        "max_users": 5,
        "max_devices": 2,
        "features": ["ARTICLES", "SALES"],
    }


def test_canonical_json_bytes_is_deterministic_regardless_of_key_order() -> None:
    ordered = {"a": 1, "b": 2}
    reordered = {"b": 2, "a": 1}
    assert canonical_json_bytes(ordered) == canonical_json_bytes(reordered)


def test_canonical_json_bytes_uses_compact_separators() -> None:
    encoded = canonical_json_bytes({"a": 1, "b": [1, 2]})
    assert b" " not in encoded


def test_from_dict_parses_a_valid_payload() -> None:
    payload = LicensePayload.from_dict(_valid_payload_dict())
    assert payload.license_id == "STK-0001"
    assert payload.edition == EditionLicence.STANDARD
    assert payload.max_users == 5
    assert payload.max_devices == 2
    assert payload.features == frozenset({"ARTICLES", "SALES"})
    assert payload.expires_at is not None


def test_to_dict_round_trips_through_json() -> None:
    payload = LicensePayload.from_dict(_valid_payload_dict())
    round_tripped = json.loads(json.dumps(payload.to_dict()))
    assert round_tripped["license_id"] == "STK-0001"
    assert round_tripped["edition"] == "STANDARD"
    assert sorted(round_tripped["features"]) == ["ARTICLES", "SALES"]


@pytest.mark.parametrize("missing_key", ["license_version", "license_id", "product", "client", "edition", "issued_at", "max_users", "max_devices", "features"])
def test_from_dict_missing_field_raises(missing_key: str) -> None:
    data = _valid_payload_dict()
    del data[missing_key]
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


def test_from_dict_unknown_edition_raises() -> None:
    data = _valid_payload_dict()
    data["edition"] = "ULTRA_PLATINUM"
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


def test_from_dict_unsupported_version_type_raises() -> None:
    data = _valid_payload_dict()
    data["license_version"] = "1"
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


def test_from_dict_invalid_issued_at_raises() -> None:
    data = _valid_payload_dict()
    data["issued_at"] = "pas une date"
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


def test_from_dict_missing_expires_at_means_no_expiration() -> None:
    data = _valid_payload_dict()
    del data["expires_at"]
    payload = LicensePayload.from_dict(data)
    assert payload.expires_at is None


@pytest.mark.parametrize("bad_value", [0, -1, 1.5, "5", True])
def test_from_dict_non_positive_or_wrong_type_max_users_raises(bad_value) -> None:
    data = _valid_payload_dict()
    data["max_users"] = bad_value
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


@pytest.mark.parametrize("bad_value", [0, -1, 1.5, "2", True])
def test_from_dict_non_positive_or_wrong_type_max_devices_raises(bad_value) -> None:
    data = _valid_payload_dict()
    data["max_devices"] = bad_value
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


def test_from_dict_features_wrong_type_raises() -> None:
    data = _valid_payload_dict()
    data["features"] = "ARTICLES,SALES"
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


def test_from_dict_features_with_non_string_element_raises() -> None:
    data = _valid_payload_dict()
    data["features"] = ["ARTICLES", 42]
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


def test_from_dict_blank_license_id_raises() -> None:
    data = _valid_payload_dict()
    data["license_id"] = "   "
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(data)


def test_from_dict_rejects_non_dict_input() -> None:
    with pytest.raises(LicensePayloadError):
        LicensePayload.from_dict(["not", "a", "dict"])
