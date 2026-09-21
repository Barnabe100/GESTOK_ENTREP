"""Lot multi-rôles RBAC (§14 A-M du cahier des charges) : un utilisateur a un
seul compte/mot de passe mais peut porter un OU PLUSIEURS rôles simultanément
(ex. Jean = Vendeur + Gestionnaire de stock, connexion unique, permissions
cumulées). Les permissions effectives sont l'UNION dédupliquée des
permissions de tous ses rôles, calculée côté service (``AuthService.login``),
jamais seulement en UI.

Chaque test ci-dessous correspond à un point du §14 (A à M), identifié dans
son nom et son docstring pour rester traçable par rapport à la spécification."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import get_engine, session_scope
from app.models.enums import EditionLicence
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.services.licensing.license_payload import DEFAULT_FEATURES_BY_EDITION, FEATURE_MULTI_USER
from app.utils.exceptions import LicenseError, ValidationError
from tests.conftest import DEFAULT_TEST_PASSWORD


def _role_id(stack, role_name: str) -> int:
    return next(r.id for r in stack.users.list_roles() if r.nom == role_name)


# -- A : utilisateur mono-rôle -- comportement inchangé -----------------------


def test_a_single_role_user_works_as_before(login_as) -> None:
    stack, current_user = login_as("Vendeur")

    assert current_user.role_names == ("Vendeur",)
    assert len(current_user.role_ids) == 1
    assert "SALE_CREATE" in current_user.permissions
    assert "ARTICLE_CREATE" not in current_user.permissions  # exclusif Gestionnaire de stock


# -- B : utilisateur à deux rôles ---------------------------------------------


def test_b_two_role_user_both_roles_correctly_stored(login_as) -> None:
    stack, current_user = login_as(["Vendeur", "Gestionnaire de stock"])

    assert current_user.role_names == ("Gestionnaire de stock", "Vendeur")
    assert len(current_user.role_ids) == 2

    with session_scope(None) as session:
        user = session.query(User).filter_by(id=current_user.id).one()
        assert {r.nom for r in user.roles} == {"Vendeur", "Gestionnaire de stock"}


# -- C : utilisateur à trois rôles --------------------------------------------


def test_c_three_role_user_works(login_as) -> None:
    stack, current_user = login_as(["Vendeur", "Gestionnaire de stock", "Consultation"])

    assert current_user.role_names == ("Consultation", "Gestionnaire de stock", "Vendeur")
    assert len(current_user.role_ids) == 3
    assert "SALE_CREATE" in current_user.permissions
    assert "ARTICLE_CREATE" in current_user.permissions
    assert "STOCK_MOVEMENT_VIEW" in current_user.permissions  # Consultation


# -- D : permissions cumulées, dédupliquées ------------------------------------


def test_d_cumulated_permissions_are_deduplicated_union(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    vendeur_codes = set(admin_stack.roles.get_role_permissions(_role_id(admin_stack, "Vendeur")))
    gestionnaire_codes = set(
        admin_stack.roles.get_role_permissions(_role_id(admin_stack, "Gestionnaire de stock"))
    )
    # DASHBOARD_VIEW est portée par les deux rôles : sert à vérifier la déduplication.
    assert "DASHBOARD_VIEW" in vendeur_codes and "DASHBOARD_VIEW" in gestionnaire_codes

    stack, current_user = login_as(["Vendeur", "Gestionnaire de stock"])

    assert current_user.permissions == frozenset(vendeur_codes | gestionnaire_codes)
    assert "SALE_CREATE" in current_user.permissions  # exclusif Vendeur
    assert "ARTICLE_CREATE" in current_user.permissions  # exclusif Gestionnaire de stock
    assert "DASHBOARD_VIEW" in current_user.permissions  # commune, présente une seule fois (frozenset)


# -- E : retirer un rôle retire ses permissions exclusives (sauf si couvertes) --


def test_e_removing_a_role_removes_its_exclusive_permissions(login_as, make_user, make_stack) -> None:
    admin_stack, _ = login_as("Administrateur")
    gestionnaire_role_id = _role_id(admin_stack, "Gestionnaire de stock")
    make_user(["Vendeur", "Gestionnaire de stock"], "polyvalent_e")
    target_id = next(u.id for u in admin_stack.users.list_users() if u.username == "polyvalent_e")

    admin_stack.users.update_user(target_id, [gestionnaire_role_id])  # retire Vendeur

    target_stack = make_stack()
    current_user = target_stack.auth.login("polyvalent_e", DEFAULT_TEST_PASSWORD)

    assert current_user.role_names == ("Gestionnaire de stock",)
    assert "SALE_CREATE" not in current_user.permissions  # rôle Vendeur retiré, plus couvert par aucun autre
    assert "ARTICLE_CREATE" in current_user.permissions  # toujours porté par Gestionnaire de stock
    assert "DASHBOARD_VIEW" in current_user.permissions  # commune aux deux rôles, reste présente


# -- F : éditer sans changer les rôles les conserve ----------------------------


def test_f_editing_user_without_changing_roles_preserves_them(login_as, make_user) -> None:
    admin_stack, _ = login_as("Administrateur")
    make_user(["Vendeur", "Gestionnaire de stock"], "polyvalent_f")
    target = next(u for u in admin_stack.users.list_users() if u.username == "polyvalent_f")

    # L'administrateur ne modifie aucune case dans le dialogue d'édition : les
    # mêmes role_ids sont retransmis tels quels (voir EditUserDialog/UsersPage).
    updated = admin_stack.users.update_user(target.id, list(target.role_ids))

    assert set(updated.role_ids) == set(target.role_ids)
    assert updated.role_names == ("Gestionnaire de stock", "Vendeur")


# -- G : au moins un rôle obligatoire ------------------------------------------


def test_g_create_user_with_zero_roles_is_refused(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.users.create_user("sans_role", "MotDePasse!23", [])


def test_g_update_user_with_zero_roles_is_refused(login_as, make_user) -> None:
    stack, _ = login_as("Administrateur")
    make_user("Vendeur", "cible_g")
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_g")

    with pytest.raises(ValidationError):
        stack.users.update_user(target_id, [])


# -- H : le même rôle ne peut pas être attribué deux fois ----------------------


def test_h_create_user_with_duplicate_role_is_refused(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Vendeur")

    with pytest.raises(ValidationError):
        stack.users.create_user("doublon", "MotDePasse!23", [role_id, role_id])


def test_h_update_user_with_duplicate_role_is_refused(login_as, make_user) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Vendeur")
    make_user("Vendeur", "cible_h")
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_h")

    with pytest.raises(ValidationError):
        stack.users.update_user(target_id, [role_id, role_id])


# -- I : max_users compte les COMPTES actifs, jamais les rôles détenus --------


def test_i_multi_role_user_counts_as_one_active_user_for_max_users(login_as, license_envelope_factory) -> None:
    """Exemple de l'énoncé : Jean cumule 2 rôles mais ne consomme qu'une
    seule place de licence, jamais deux."""
    stack, _ = login_as("Administrateur")  # 1 compte actif
    envelope = license_envelope_factory(max_users=2)
    stack.licenses.activate_license(envelope)
    vendeur_role_id = _role_id(stack, "Vendeur")
    gestionnaire_role_id = _role_id(stack, "Gestionnaire de stock")

    jean = stack.users.create_user(
        "jean", "MotDePasse!23", [vendeur_role_id, gestionnaire_role_id], actif=True
    )
    assert jean.actif is True
    assert len(jean.role_ids) == 2

    active_count = sum(1 for u in stack.users.list_users() if u.actif)
    assert active_count == 2  # administrateur + jean, jamais 3 malgré les 2 rôles de jean

    # Un 3e compte actif dépasserait la limite (max_users=2), même si aucun
    # rôle supplémentaire n'est en cause : la limite porte sur les comptes.
    with pytest.raises(ValidationError):
        stack.users.create_user("paul", "MotDePasse!23", [vendeur_role_id], actif=True)


# -- J : l'authentification charge les permissions cumulées -------------------


def test_j_authentication_loads_cumulated_permissions_after_login(make_user, make_stack) -> None:
    make_user(["Vendeur", "Gestionnaire de stock"], "polyvalent_j", "MotDePasse!23")
    stack = make_stack()

    current_user = stack.auth.login("polyvalent_j", "MotDePasse!23")

    assert current_user.role_names == ("Gestionnaire de stock", "Vendeur")
    assert "SALE_CREATE" in current_user.permissions
    assert "ARTICLE_CREATE" in current_user.permissions
    assert stack.permissions.has_permission("SALE_CREATE") is True
    assert stack.permissions.has_permission("ARTICLE_CREATE") is True


# -- K : compatibilité — la migration 0011 préserve le rôle existant ----------


def test_k_migration_preserves_existing_users_role(test_settings) -> None:
    """§13/§14-K : vérifié empiriquement (jamais seulement en relisant le
    code de la migration) — un utilisateur créé à la révision 0010 (avant le
    lot multi-rôles) doit retrouver exactement son rôle actuel dans
    ``user_roles`` après la mise à jour vers la révision 0011, sans qu'il
    n'ait jamais eu à se reconnecter ni qu'aucune donnée ne soit perdue."""
    from alembic import command

    from app.db.init_db import _alembic_config
    from app.db.seed import seed_reference_data

    config = _alembic_config(test_settings)
    command.upgrade(config, "0010")

    with session_scope(test_settings) as session:
        seed_reference_data(session)
        vendeur_role = session.query(Role).filter_by(nom="Vendeur").one()
        user = User(
            username="avant_migration_0011",
            password_hash=hash_password("Password!23"),
            role_id=vendeur_role.id,
            actif=True,
        )
        session.add(user)
        session.flush()
        user_id = user.id
        role_id = vendeur_role.id

    command.upgrade(config, "0011")

    engine = get_engine(test_settings)
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT user_id, role_id FROM user_roles WHERE user_id = :uid"), {"uid": user_id}
        ).fetchall()
    assert rows == [(user_id, role_id)]

    with session_scope(test_settings) as session:
        persisted_user = session.get(User, user_id)
        assert persisted_user.role_id == role_id  # colonne héritée, jamais modifiée par la migration
        assert [r.nom for r in persisted_user.roles] == ["Vendeur"]  # source de vérité désormais


# -- L : régression — le RBAC mono-rôle existant continue de fonctionner ------


def test_l_existing_single_role_permission_matrix_unchanged(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    expected = frozenset(admin_stack.roles.get_role_permissions(_role_id(admin_stack, "Vendeur")))

    _, current_user = login_as("Vendeur")

    assert current_user.permissions == expected


# -- M : le multi-utilisateurs reste une fonctionnalité PROFESSIONAL/ENTREPRISE --


def test_m_multi_user_management_blocked_for_demo_edition(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    demo_features = sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.DEMO])
    envelope = license_envelope_factory(edition="DEMO", features=demo_features)
    stack.licenses.activate_license(envelope)

    assert stack.permissions.has_permission("USER_CREATE") is False
    with pytest.raises(LicenseError):
        stack.permissions.require_permission("USER_CREATE")


def test_m_multi_user_management_blocked_for_standard_edition(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    standard_features = sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.STANDARD])
    envelope = license_envelope_factory(edition="STANDARD", features=standard_features)
    stack.licenses.activate_license(envelope)

    assert stack.permissions.has_permission("USER_UPDATE") is False
    with pytest.raises(LicenseError):
        stack.permissions.require_permission("USER_UPDATE")


def test_m_multi_user_management_allowed_when_license_grants_the_feature(login_as, license_envelope_factory) -> None:
    """Une licence PROFESSIONAL incluant explicitement MULTI_USER (offre
    commerciale multi-utilisateurs) débloque la gestion des comptes — le
    contrôle repose uniquement sur le FeatureGate existant, jamais sur
    l'édition en tant que telle."""
    stack, _ = login_as("Administrateur")
    professional_features = sorted(
        DEFAULT_FEATURES_BY_EDITION[EditionLicence.PROFESSIONAL] | {FEATURE_MULTI_USER}
    )
    envelope = license_envelope_factory(edition="PROFESSIONAL", features=professional_features)
    stack.licenses.activate_license(envelope)

    assert stack.permissions.has_permission("USER_CREATE") is True
    stack.permissions.require_permission("USER_CREATE")  # ne doit pas lever


def test_m_multi_user_management_allowed_for_entreprise_edition(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    entreprise_features = sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.ENTREPRISE])
    envelope = license_envelope_factory(edition="ENTREPRISE", features=entreprise_features)
    stack.licenses.activate_license(envelope)

    assert stack.permissions.has_permission("USER_ACTIVATE") is True
    stack.permissions.require_permission("USER_ACTIVATE")
