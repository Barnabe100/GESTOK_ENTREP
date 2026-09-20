"""Synchronisation additive des données de référence (voir diagnostic :
une base existante, créée par une version antérieure du code, ne reçoit
jamais automatiquement les permissions ajoutées par la suite — seule une
synchronisation explicite, additive et idempotente doit combler l'écart,
sans jamais toucher aux rôles, utilisateurs, mots de passe ou
personnalisations existantes)."""
from __future__ import annotations

from app.config.settings import Settings
from app.db.init_db import init_database
from app.db.reference_data_sync import sync_reference_data
from app.db.seed import PERMISSIONS, ROLE_DESCRIPTIONS, ROLE_PERMISSIONS_MATRIX
from app.db.session import session_scope
from app.models.rbac import Permission, Role

# Permissions volontairement récentes (voir le diagnostic) : absentes d'une
# base « ancienne » simulée ci-dessous.
_RECENT_CODES = frozenset({
    "CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE", "CLIENT_ACTIVATE", "CLIENT_DEACTIVATE",
    "SALE_PAYMENT_CREATE", "SYSTEM_RESET_BUSINESS_DATA",
})


def _seed_stale_database(settings: Settings) -> None:
    """Recrée, à la main, l'état d'une base initialisée par une version du
    code antérieure à l'introduction de ``_RECENT_CODES`` : les 4 rôles
    système existent, mais ni les permissions récentes ni leurs
    associations n'ont jamais été créées. Contrairement à
    ``seed_reference_data``, ceci n'insère délibérément qu'un sous-ensemble
    des données de référence actuelles, pour reproduire fidèlement le
    symptôme diagnostiqué (permissions absentes de la table, pas seulement
    non associées)."""
    with session_scope(settings) as session:
        permissions_by_code: dict[str, Permission] = {}
        for code, libelle, module in PERMISSIONS:
            if code in _RECENT_CODES:
                continue
            permission = Permission(code=code, libelle=libelle, module=module)
            session.add(permission)
            permissions_by_code[code] = permission
        session.flush()

        for role_name, permission_codes in ROLE_PERMISSIONS_MATRIX.items():
            role = Role(nom=role_name, description=ROLE_DESCRIPTIONS[role_name])
            old_codes = [code for code in permission_codes if code not in _RECENT_CODES]
            role.permissions = [permissions_by_code[code] for code in old_codes]
            session.add(role)
        session.flush()


def _role_codes(settings: Settings, role_name: str) -> set[str]:
    with session_scope(settings) as session:
        role = session.query(Role).filter_by(nom=role_name).one()
        return {p.code for p in role.permissions}


def _permission_count(settings: Settings, code: str) -> int:
    with session_scope(settings) as session:
        return session.query(Permission).filter_by(code=code).count()


# -- base « ancienne » : permissions récentes absentes ------------------------------


def test_stale_database_is_missing_recent_permissions_before_sync(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        existing_codes = {p.code for p in session.query(Permission).all()}
    assert existing_codes.isdisjoint(_RECENT_CODES)


def test_stale_database_roles_exist_before_sync(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        role_names = {r.nom for r in session.query(Role).all()}
    assert role_names == {"Administrateur", "Gestionnaire de stock", "Vendeur", "Consultation"}


# -- synchronisation : nouvelles permissions récupérées ------------------------------


def test_sync_creates_all_missing_permission_rows(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        result = sync_reference_data(session)

    assert set(result.permissions_created) == _RECENT_CODES
    with session_scope(test_settings) as session:
        existing_codes = {p.code for p in session.query(Permission).all()}
    assert _RECENT_CODES.issubset(existing_codes)


def test_sync_preserves_permission_libelle_and_module_from_code(test_settings: Settings) -> None:
    """Les permissions créées par la synchronisation reprennent exactement
    le libellé et le module définis dans ``PERMISSIONS`` (code source),
    jamais une valeur inventée par la synchronisation elle-même."""
    init_database(test_settings)
    _seed_stale_database(test_settings)
    expected = {code: (libelle, module) for code, libelle, module in PERMISSIONS if code in _RECENT_CODES}

    with session_scope(test_settings) as session:
        sync_reference_data(session)

    with session_scope(test_settings) as session:
        for code, (libelle, module) in expected.items():
            permission = session.query(Permission).filter_by(code=code).one()
            assert permission.libelle == libelle
            assert permission.module == module


# -- synchronisation : associations rôle -> permission attendues ---------------------


def test_sync_grants_expected_permissions_to_administrateur(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        sync_reference_data(session)

    codes = _role_codes(test_settings, "Administrateur")
    assert _RECENT_CODES.issubset(codes)


def test_sync_grants_expected_permissions_to_gestionnaire(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        sync_reference_data(session)

    codes = _role_codes(test_settings, "Gestionnaire de stock")
    assert {"CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE", "CLIENT_ACTIVATE", "CLIENT_DEACTIVATE"}.issubset(codes)
    assert "SALE_PAYMENT_CREATE" not in codes
    assert "SYSTEM_RESET_BUSINESS_DATA" not in codes


def test_sync_grants_expected_permissions_to_vendeur(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        sync_reference_data(session)

    codes = _role_codes(test_settings, "Vendeur")
    assert {"CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE", "SALE_PAYMENT_CREATE"}.issubset(codes)
    assert "CLIENT_ACTIVATE" not in codes
    assert "CLIENT_DEACTIVATE" not in codes
    assert "SYSTEM_RESET_BUSINESS_DATA" not in codes


def test_sync_does_not_grant_recent_permissions_to_consultation(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        sync_reference_data(session)

    codes = _role_codes(test_settings, "Consultation")
    assert codes.isdisjoint(_RECENT_CODES)


# -- synchronisation : ne détruit rien -------------------------------------------------


def test_sync_never_removes_roles_or_users(test_settings: Settings, monkeypatch) -> None:
    from app.security.password_hashing import hash_password
    from app.models.user import User

    init_database(test_settings)
    _seed_stale_database(test_settings)
    with session_scope(test_settings) as session:
        admin_role = session.query(Role).filter_by(nom="Administrateur").one()
        session.add(
            User(username="admin_stale", password_hash=hash_password("MotDePasse!23"), role_id=admin_role.id, actif=True)
        )

    with session_scope(test_settings) as session:
        sync_reference_data(session)

    with session_scope(test_settings) as session:
        assert session.query(Role).count() == 4
        user = session.query(User).filter_by(username="admin_stale").one()
        assert user.password_hash  # mot de passe inchangé, toujours présent
        assert user.actif is True


def test_sync_preserves_manually_granted_custom_permission(test_settings: Settings) -> None:
    """Une permission accordée manuellement à un rôle depuis l'écran
    d'administration, hors de ``ROLE_PERMISSIONS_MATRIX`` (ex. Vendeur ayant
    reçu STOCK_REASON_VIEW par décision administrative locale), ne doit
    jamais être retirée par la synchronisation — celle-ci n'ajoute, ne
    retire jamais."""
    init_database(test_settings)
    _seed_stale_database(test_settings)
    with session_scope(test_settings) as session:
        vendeur = session.query(Role).filter_by(nom="Vendeur").one()
        custom_permission = session.query(Permission).filter_by(code="STOCK_REASON_VIEW").one()
        vendeur.permissions.append(custom_permission)

    with session_scope(test_settings) as session:
        sync_reference_data(session)

    codes = _role_codes(test_settings, "Vendeur")
    assert "STOCK_REASON_VIEW" in codes  # personnalisation préservée
    assert {"CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE", "SALE_PAYMENT_CREATE"}.issubset(codes)  # + rattrapage


def test_sync_never_removes_existing_permission_rows(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)
    with session_scope(test_settings) as session:
        count_before = session.query(Permission).count()

    with session_scope(test_settings) as session:
        sync_reference_data(session)

    with session_scope(test_settings) as session:
        count_after = session.query(Permission).count()
    assert count_after == count_before + len(_RECENT_CODES)


# -- idempotence ------------------------------------------------------------------------


def test_second_sync_makes_no_changes(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        first_result = sync_reference_data(session)
    assert first_result.has_changes is True

    with session_scope(test_settings) as session:
        second_result = sync_reference_data(session)

    assert second_result.permissions_created == []
    assert second_result.role_permissions_added == {}
    assert second_result.has_changes is False


def test_second_sync_creates_no_duplicate_permission_rows(test_settings: Settings) -> None:
    init_database(test_settings)
    _seed_stale_database(test_settings)

    with session_scope(test_settings) as session:
        sync_reference_data(session)
    with session_scope(test_settings) as session:
        sync_reference_data(session)

    for code in _RECENT_CODES:
        assert _permission_count(test_settings, code) == 1


def test_sync_on_already_up_to_date_database_is_a_no_op(initialized_db: Settings) -> None:
    """Appliquée à une base déjà entièrement à jour (cas normal en
    production une fois cette correction déployée), la synchronisation ne
    doit rien modifier dès le premier appel."""
    with session_scope(initialized_db) as session:
        result = sync_reference_data(session)

    assert result.has_changes is False


# -- la licence continue d'être appliquée séparément (FeatureGate non contourné) ------


def test_sync_does_not_bypass_feature_gate_for_license_restricted_permission(
    login_as, license_envelope_factory
) -> None:
    """La synchronisation RBAC ne doit jamais devenir un moyen détourné
    d'accorder un droit que la licence active ne couvre pas : après
    synchronisation, SALE_PAYMENT_CREATE reste soumise à FEATURE_SALES via
    FeatureGate, exactement comme avant (voir test_permission_service_licensing.py)."""
    from datetime import date

    from app.services.licensing.license_payload import DEFAULT_FEATURES_BY_EDITION
    from app.models.enums import EditionLicence
    from app.utils.exceptions import LicenseError

    stack, _ = login_as("Administrateur")

    with session_scope(None) as session:
        sync_reference_data(session)  # base déjà à jour : aucun changement, contrôle de non-régression

    demo_features = sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.DEMO])
    envelope = license_envelope_factory(edition="DEMO", features=demo_features)
    stack.licenses.activate_license(envelope)

    assert stack.permissions.has_permission("SALE_PAYMENT_CREATE") is False
    try:
        stack.permissions.require_permission("SALE_PAYMENT_CREATE")
        assert False, "LicenseError attendue"
    except LicenseError:
        pass
