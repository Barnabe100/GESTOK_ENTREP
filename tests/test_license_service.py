"""Validation centralisée (§5), état exploitable (§6) et activation (§9) de
``LicenseService`` — voir aussi test_license_security.py (absence de clé
privée) et test_permission_service_licensing.py (combinaison RBAC+licence)."""
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.config.settings import Settings
from app.db import session as db_session_module
from app.models.enums import EditionLicence
from app.repositories.licence_repository import LicenceRepository
from app.services.licensing.license_payload import DEFAULT_FEATURES_BY_EDITION
from app.services.licensing.license_service import LicenseState
from app.services.registry import build_service_registry
from app.utils.exceptions import PermissionDeniedError, ValidationError
from tests.conftest import TEST_LICENSE_PUBLIC_KEY_BYTES


# -- état ---------------------------------------------------------------------------


def test_full_access_test_license_evaluates_as_valid(login_as) -> None:
    """Sanity check de la licence auto-provisionnée par conftest.py, dont
    dépendent tous les autres tests existants de la suite."""
    stack, _ = login_as("Administrateur")

    info = stack.licenses.get_info()

    assert info.state == LicenseState.VALID
    assert info.edition == EditionLicence.ENTREPRISE


def test_missing_license_state_when_no_license_activated(test_settings: Settings) -> None:
    """Base migrée et seedée, mais sans aucune licence : simule une
    installation neuve — ``initialized_db`` provisionne toujours une licence
    de test, ce test construit donc sa propre base minimale."""
    from app.db.init_db import init_database
    from app.db.seed import seed_reference_data

    init_database(test_settings)
    with db_session_module.session_scope(test_settings) as session:
        seed_reference_data(session)

    stack = build_service_registry(test_settings, license_public_key_bytes=TEST_LICENSE_PUBLIC_KEY_BYTES)

    assert stack.licenses.get_state() == LicenseState.MISSING


def test_evaluate_detects_corrupted_stored_payload(login_as) -> None:
    stack, _ = login_as("Administrateur")

    _corrupt_current_license_payload()

    assert stack.licenses.get_state() == LicenseState.CORRUPTED


def _corrupt_current_license_payload() -> None:
    from app.db.session import session_scope

    with session_scope(None) as session:
        row = LicenceRepository(session).get_current()
        row.payload_json = "{ceci n'est pas du JSON valide"


def test_evaluate_detects_tampered_stored_signature(login_as) -> None:
    stack, _ = login_as("Administrateur")
    from app.db.session import session_scope

    with session_scope(None) as session:
        row = LicenceRepository(session).get_current()
        row.signature = row.signature[:-4] + "AAAA"

    assert stack.licenses.get_state() == LicenseState.INVALID


# -- activation : succès -------------------------------------------------------------


def test_activate_license_persists_and_reports_details(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(
        license_id="STK-ABC-123", client="Ma Société", edition="PROFESSIONAL",
        max_users=7, max_devices=3, features=sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.PROFESSIONAL]),
    )

    info = stack.licenses.activate_license(envelope)

    assert info.state == LicenseState.VALID
    assert info.license_id == "STK-ABC-123"
    assert info.client == "Ma Société"
    assert info.edition == EditionLicence.PROFESSIONAL
    assert info.max_users == 7
    assert info.max_devices == 3
    assert "REPORTS" in info.features


def test_activate_license_without_expiration_is_valid(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(expires_at=None)

    info = stack.licenses.activate_license(envelope)

    assert info.state == LicenseState.VALID
    assert info.expires_at is None


def test_activate_license_with_past_expiration_is_stored_but_reports_expired(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    past_date = (date.today() - timedelta(days=10)).isoformat()
    envelope = license_envelope_factory(expires_at=past_date)

    info = stack.licenses.activate_license(envelope)

    assert info.state == LicenseState.EXPIRED


def test_device_id_is_stable_across_evaluations(login_as) -> None:
    stack, _ = login_as("Administrateur")

    first = stack.licenses.get_info().device_id
    second = stack.licenses.get_info().device_id

    assert first is not None
    assert first == second


# -- activation : permissions ---------------------------------------------------------


def test_activate_license_requires_license_activate_permission(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Vendeur")
    envelope = license_envelope_factory()

    with pytest.raises(PermissionDeniedError):
        stack.licenses.activate_license(envelope)


def test_get_info_requires_license_view_permission(login_as) -> None:
    """LICENSE_VIEW n'est accordée qu'à l'Administrateur (voir app/db/seed.py) ;
    ce test vérifie que LicenseService la fait respecter, indépendamment de
    ce que l'UI affiche ou masque."""
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.licenses.get_info()


# -- activation : sécurité / falsification (§16) ----------------------------------------


def test_activate_license_rejects_invalid_json(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.licenses.activate_license("ceci n'est pas du JSON")


def test_activate_license_rejects_missing_envelope_keys(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.licenses.activate_license('{"foo": "bar"}')


def test_activate_license_rejects_tampered_payload(login_as, license_envelope_factory) -> None:
    """Modifier la charge utile après signature (ex. relever max_users) sans
    re-signer doit être détecté : la signature ne correspond plus."""
    import json

    envelope = license_envelope_factory(max_users=1)
    tampered = json.loads(envelope)
    tampered["payload"]["max_users"] = 9999
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(json.dumps(tampered))


def test_activate_license_rejects_signature_from_wrong_key(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    wrong_key = Ed25519PrivateKey.generate()
    envelope = license_envelope_factory(private_key=wrong_key)

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(envelope)


def test_activate_license_rejects_malformed_signature_encoding(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(signature_override="pas-du-base64-valide-!!")

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(envelope)


def test_activate_license_rejects_unsupported_version(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(license_version=99)

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(envelope)


def test_activate_license_rejects_wrong_product(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(product="Un Autre Logiciel")

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(envelope)


def test_activate_license_rejects_unknown_edition(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(edition="ULTRA_PLATINUM")

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(envelope)


def test_activate_license_rejects_unknown_feature(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(features=["ARTICLES", "FONCTIONNALITE_INVENTEE"])

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(envelope)


def test_activate_license_rejects_incoherent_future_issue_date(login_as, license_envelope_factory) -> None:
    future_date = (date.today() + timedelta(days=30)).isoformat()
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(issued_at=future_date)

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(envelope)


def test_activate_license_rejects_modified_features_without_resigning(login_as, license_envelope_factory) -> None:
    import json

    envelope = license_envelope_factory(features=["ARTICLES"])
    tampered = json.loads(envelope)
    tampered["payload"]["features"] = sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.ENTREPRISE])
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.licenses.activate_license(json.dumps(tampered))


def test_failed_activation_never_replaces_the_current_license(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    before = stack.licenses.get_info().license_id

    tampered_envelope = license_envelope_factory(signature_override="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    with pytest.raises(ValidationError):
        stack.licenses.activate_license(tampered_envelope)

    after = stack.licenses.get_info().license_id
    assert after == before
