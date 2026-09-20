"""Combinaison RBAC + licence dans ``PermissionService`` (§8) : une action
requiert la permission RBAC de l'utilisateur ET que la licence active
couvre la fonctionnalité associée. Les quatre combinaisons possibles sont
couvertes explicitement ci-dessous (§17)."""
import pytest

from app.models.enums import EditionLicence
from app.services.licensing.license_payload import DEFAULT_FEATURES_BY_EDITION
from app.utils.exceptions import LicenseError, PermissionDeniedError

# REPORT_VIEW -> FEATURE_REPORTS (voir permission_map.py) : l'Administrateur a
# la permission RBAC, le Vendeur ne l'a pas. La licence DEMO n'inclut pas
# REPORTS, la licence ENTREPRISE (accès complet, provisionnée par défaut en
# test) l'inclut.
_PERMISSION_CODE = "REPORT_VIEW"
_DEMO_FEATURES = sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.DEMO])


def _activate_demo_license(stack, license_envelope_factory) -> None:
    envelope = license_envelope_factory(edition="DEMO", features=_DEMO_FEATURES)
    stack.licenses.activate_license(envelope)


def test_rbac_ok_and_license_ok_allows_access(login_as) -> None:
    """Scénario 1/4 : Administrateur (a REPORT_VIEW) + licence ENTREPRISE (a REPORTS) -> autorisé."""
    stack, _ = login_as("Administrateur")

    assert stack.permissions.has_permission(_PERMISSION_CODE) is True
    stack.permissions.require_permission(_PERMISSION_CODE)  # ne doit pas lever


def test_rbac_ok_and_license_not_ok_blocks_with_license_error(login_as, license_envelope_factory) -> None:
    """Scénario 2/4 : Administrateur (a REPORT_VIEW) + licence DEMO (sans REPORTS)
    -> refusé par la licence, MÊME pour un Administrateur (§8)."""
    stack, _ = login_as("Administrateur")
    _activate_demo_license(stack, license_envelope_factory)

    assert stack.permissions.has_permission(_PERMISSION_CODE) is False
    with pytest.raises(LicenseError):
        stack.permissions.require_permission(_PERMISSION_CODE)


def test_rbac_not_ok_and_license_ok_blocks_with_permission_error(login_as) -> None:
    """Scénario 3/4 : Vendeur (pas REPORT_VIEW) + licence ENTREPRISE (a REPORTS)
    -> refusé par le RBAC, la licence n'a pas d'importance ici."""
    stack, _ = login_as("Vendeur")

    assert stack.permissions.has_permission(_PERMISSION_CODE) is False
    with pytest.raises(PermissionDeniedError):
        stack.permissions.require_permission(_PERMISSION_CODE)


def test_rbac_not_ok_and_license_not_ok_blocks_with_permission_error(login_as, license_envelope_factory) -> None:
    """Scénario 4/4 : Vendeur (pas REPORT_VIEW) + licence DEMO (sans REPORTS)
    -> le RBAC est vérifié en premier, l'erreur reste PermissionDeniedError."""
    admin_stack, _ = login_as("Administrateur")
    _activate_demo_license(admin_stack, license_envelope_factory)

    stack, _ = login_as("Vendeur")
    assert stack.permissions.has_permission(_PERMISSION_CODE) is False
    with pytest.raises(PermissionDeniedError):
        stack.permissions.require_permission(_PERMISSION_CODE)


def test_license_gated_permissions_still_work_without_feature_gate_attached() -> None:
    """Un PermissionService construit sans FeatureGate (cas historique, ex.
    tests unitaires bas niveau) reste purement RBAC — comportement inchangé
    depuis avant cette phase, indispensable pour ne pas casser les appels
    directs existants (voir tests/test_backup_cli.py)."""
    from app.config.settings import Settings
    from app.services.auth.auth_service import AuthService
    from app.services.auth.permission_service import PermissionService
    from app.services.licensing.permission_map import PERMISSION_TO_FEATURE

    service = PermissionService(AuthService(None), permission_to_feature=PERMISSION_TO_FEATURE)
    assert service.has_permission(_PERMISSION_CODE) is False  # pas d'utilisateur connecté


def test_sale_payment_create_is_feature_gated_like_other_sale_permissions(login_as, license_envelope_factory) -> None:
    """SALE_PAYMENT_CREATE (ventes à crédit/paiements partiels) doit être
    soumise au même contrôle de licence FEATURE_SALES que le reste du
    module Ventes — jamais un point d'accès non licencié échappant au
    contrôle appliqué à SALE_VALIDATE/SALE_CANCEL."""
    stack, _ = login_as("Administrateur")
    _activate_demo_license(stack, license_envelope_factory)  # DEMO n'inclut pas FEATURE_SALES

    assert stack.permissions.has_permission("SALE_PAYMENT_CREATE") is False
    with pytest.raises(LicenseError):
        stack.permissions.require_permission("SALE_PAYMENT_CREATE")


def test_license_view_and_activate_are_never_feature_gated(login_as, license_envelope_factory) -> None:
    """LICENSE_VIEW/LICENSE_ACTIVATE doivent rester accessibles même sans
    fonctionnalité couverte par la licence active, sous peine de rendre
    l'écran d'activation lui-même inatteignable (voir permission_map.py)."""
    stack, _ = login_as("Administrateur")
    _activate_demo_license(stack, license_envelope_factory)

    assert stack.permissions.has_permission("LICENSE_VIEW") is True
    assert stack.permissions.has_permission("LICENSE_ACTIVATE") is True


def test_system_reset_business_data_is_feature_gated_to_backups(login_as, license_envelope_factory) -> None:
    """Audit final avant commit : SYSTEM_RESET_BUSINESS_DATA doit être
    rattachée à FEATURE_BACKUPS (réutilise techniquement BackupService) —
    jamais disponible sans aucune licence valide, même pour
    l'Administrateur."""
    stack, _ = login_as("Administrateur")
    _activate_demo_license(stack, license_envelope_factory)  # DEMO n'inclut pas FEATURE_BACKUPS

    assert stack.permissions.has_permission("SYSTEM_RESET_BUSINESS_DATA") is False
    with pytest.raises(LicenseError):
        stack.permissions.require_permission("SYSTEM_RESET_BUSINESS_DATA")


# -- CAS 4/5 : licence expirée / corrompue bloque une fonctionnalité protégée ---------


def test_expired_license_blocks_a_feature_gated_permission_end_to_end(login_as, license_envelope_factory) -> None:
    """CAS 4 : une licence expirée doit refuser toute permission soumise au
    contrôle de licence, de bout en bout via require_permission — pas
    seulement au niveau de LicenseService.evaluate()."""
    from datetime import date, timedelta

    stack, _ = login_as("Administrateur")
    past_date = (date.today() - timedelta(days=10)).isoformat()
    envelope = license_envelope_factory(expires_at=past_date)
    stack.licenses.activate_license(envelope)

    assert stack.permissions.has_permission("SYSTEM_RESET_BUSINESS_DATA") is False
    with pytest.raises(LicenseError):
        stack.permissions.require_permission("SYSTEM_RESET_BUSINESS_DATA")


def test_corrupted_license_blocks_a_feature_gated_permission_end_to_end(login_as) -> None:
    """CAS 5 : une licence corrompue (payload illisible) doit refuser toute
    permission soumise au contrôle de licence, de bout en bout via
    require_permission."""
    from app.db.session import session_scope
    from app.repositories.licence_repository import LicenceRepository

    stack, _ = login_as("Administrateur")
    with session_scope(None) as session:
        row = LicenceRepository(session).get_current()
        row.payload_json = "{ceci n'est pas du JSON valide"

    assert stack.permissions.has_permission("SYSTEM_RESET_BUSINESS_DATA") is False
    with pytest.raises(LicenseError):
        stack.permissions.require_permission("SYSTEM_RESET_BUSINESS_DATA")
