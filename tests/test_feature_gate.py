"""``FeatureGate`` : point de contrôle unique des fonctionnalités licenciées (§7)."""
import pytest

from app.models.enums import EditionLicence
from app.services.licensing.license_payload import DEFAULT_FEATURES_BY_EDITION
from app.utils.exceptions import LicenseError


def test_can_returns_true_for_a_feature_included_in_the_active_license(login_as) -> None:
    stack, _ = login_as("Administrateur")  # licence de test à accès complet

    assert stack.permissions._feature_gate.can("REPORTS") is True


def test_can_returns_false_for_a_feature_not_included_in_the_active_license(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(
        edition="DEMO", features=sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.DEMO])
    )
    stack.licenses.activate_license(envelope)

    assert stack.permissions._feature_gate.can("REPORTS") is False


def test_can_returns_false_when_no_license_is_active(test_settings) -> None:
    from app.db import session as db_session_module
    from app.db.init_db import init_database
    from app.db.seed import seed_reference_data
    from app.services.registry import build_service_registry
    from tests.conftest import TEST_LICENSE_PUBLIC_KEY_BYTES

    init_database(test_settings)
    with db_session_module.session_scope(test_settings) as session:
        seed_reference_data(session)
    stack = build_service_registry(test_settings, license_public_key_bytes=TEST_LICENSE_PUBLIC_KEY_BYTES)

    assert stack.permissions._feature_gate.can("ARTICLES") is False


def test_require_raises_license_error_when_feature_not_covered(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(
        edition="DEMO", features=sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.DEMO])
    )
    stack.licenses.activate_license(envelope)

    with pytest.raises(LicenseError):
        stack.permissions._feature_gate.require("REPORTS")


def test_require_does_not_raise_when_feature_is_covered(login_as) -> None:
    stack, _ = login_as("Administrateur")

    stack.permissions._feature_gate.require("REPORTS")  # ne doit pas lever
