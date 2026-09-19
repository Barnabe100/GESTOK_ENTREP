"""Tests de ``RoleService`` : permissions, garde-fous de protection du rôle
Administrateur, garde-fou « rôle avec utilisateurs actifs », audit, et
garantie de n'affecter ni les utilisateurs ni les mots de passe (Lot C —
Administration des rôles et permissions)."""
import pytest

from app.db.session import session_scope
from app.models.audit import AuditLog
from app.security.password_hashing import verify_password
from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError


def _role_id(stack, role_name: str) -> int:
    return next(r.id for r in stack.roles.list_roles() if r.nom == role_name)


# -- permissions --------------------------------------------------------------------


def test_list_roles_as_administrateur_succeeds(login_as) -> None:
    stack, _ = login_as("Administrateur")

    roles = stack.roles.list_roles()

    assert {r.nom for r in roles} == {"Administrateur", "Gestionnaire de stock", "Vendeur", "Consultation"}


def test_list_roles_denied_for_role_without_role_view(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.roles.list_roles()


def test_list_permissions_denied_for_role_without_role_view(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")

    with pytest.raises(PermissionDeniedError):
        stack.roles.list_permissions()


def test_get_role_permissions_denied_for_role_without_role_view(login_as) -> None:
    stack, _ = login_as("Consultation")

    with pytest.raises(PermissionDeniedError):
        stack.roles.get_role_permissions(1)


def test_update_role_permissions_denied_for_role_without_role_update(login_as) -> None:
    """Consultation n'a que ROLE_VIEW-équivalent... en réalité aucun rôle non-
    Administrateur n'a ROLE_VIEW ni ROLE_UPDATE (voir seed.py) : ce test
    documente le refus pour un rôle sans la permission requise."""
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.roles.update_role_permissions(1, ["ARTICLE_VIEW"])


# -- consultation ---------------------------------------------------------------------


def test_list_roles_reports_active_user_count(login_as, make_user) -> None:
    make_user("Vendeur", "compteur_1")
    make_user("Vendeur", "compteur_2", actif=False)
    stack, _ = login_as("Administrateur")

    vendeur = next(r for r in stack.roles.list_roles() if r.nom == "Vendeur")

    # compteur_2 est inactif : ne doit pas être compté.
    assert vendeur.nombre_utilisateurs_actifs == 1


def test_list_permissions_grouped_by_module_available(login_as) -> None:
    stack, _ = login_as("Administrateur")

    permissions = stack.roles.list_permissions()

    modules = {p.module for p in permissions}
    assert "utilisateurs" in modules
    assert "roles" in modules
    assert any(p.code == "USER_VIEW" for p in permissions)


def test_get_role_permissions_returns_current_codes(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Vendeur")

    codes = stack.roles.get_role_permissions(role_id)

    assert "SALE_CREATE" in codes
    assert "USER_CREATE" not in codes  # Vendeur n'a aucune permission utilisateurs


def test_get_role_permissions_unknown_role_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.roles.get_role_permissions(999999)


# -- modification réussie --------------------------------------------------------------


def test_update_role_permissions_succeeds(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Consultation")
    new_codes = ["ARTICLE_VIEW", "DASHBOARD_VIEW"]

    stack.roles.update_role_permissions(role_id, new_codes)

    assert set(stack.roles.get_role_permissions(role_id)) == set(new_codes)


def test_update_role_permissions_unknown_role_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.roles.update_role_permissions(999999, ["ARTICLE_VIEW"])


def test_update_role_permissions_unknown_code_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Consultation")

    with pytest.raises(ValidationError):
        stack.roles.update_role_permissions(role_id, ["CODE_INEXISTANT"])


def test_update_role_permissions_writes_audit_log(login_as) -> None:
    stack, admin_user = login_as("Administrateur")
    role_id = _role_id(stack, "Consultation")

    stack.roles.update_role_permissions(role_id, ["ARTICLE_VIEW"])

    with session_scope(None) as session:
        entries = session.query(AuditLog).filter_by(action="ROLE_UPDATE", entite_id=role_id).all()
        assert len(entries) == 1
        assert entries[0].user_id == admin_user.id
        assert entries[0].entite == "roles"


# -- garde-fou Administrateur -----------------------------------------------------------


@pytest.mark.parametrize("protected_code", ["ROLE_VIEW", "ROLE_UPDATE", "USER_VIEW", "USER_UPDATE"])
def test_cannot_remove_protected_permission_from_administrateur(login_as, protected_code: str) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Administrateur")
    current_codes = set(stack.roles.get_role_permissions(role_id))
    attempted_codes = current_codes - {protected_code}

    with pytest.raises(ValidationError):
        stack.roles.update_role_permissions(role_id, list(attempted_codes))

    # L'état en base ne doit pas avoir changé après le refus.
    assert protected_code in stack.roles.get_role_permissions(role_id)


def test_administrateur_role_can_still_be_updated_when_protected_permissions_kept(login_as) -> None:
    """Le garde-fou ne bloque que le retrait des 4 permissions protégées —
    une modification qui les conserve toutes doit rester possible."""
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Administrateur")
    current_codes = set(stack.roles.get_role_permissions(role_id))
    protected = {"ROLE_VIEW", "ROLE_UPDATE", "USER_VIEW", "USER_UPDATE"}
    # Retire une permission non protégée quelconque, garde toutes les protégées.
    removable = next(c for c in current_codes if c not in protected)
    new_codes = current_codes - {removable}

    updated = stack.roles.update_role_permissions(role_id, list(new_codes))

    assert removable not in stack.roles.get_role_permissions(role_id)
    assert protected <= set(stack.roles.get_role_permissions(role_id))
    assert updated.nom == "Administrateur"


def test_protected_permission_guard_cannot_be_bypassed_by_direct_service_call(login_as) -> None:
    """Contournement direct du service : même sans passer par l'UI (dont les
    cases seraient grisées), l'appel direct reste refusé."""
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Administrateur")

    with pytest.raises(ValidationError):
        stack.roles.update_role_permissions(role_id, [])


# -- garde-fou rôle avec utilisateurs actifs ---------------------------------------------


def test_cannot_empty_permissions_of_role_with_active_users(login_as, make_user) -> None:
    make_user("Vendeur", "utilisateur_actif_role")
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Vendeur")

    with pytest.raises(ValidationError):
        stack.roles.update_role_permissions(role_id, [])

    # L'état en base ne doit pas avoir changé après le refus.
    assert stack.roles.get_role_permissions(role_id) != []


def test_emptying_permissions_allowed_for_role_without_active_users(login_as, make_user) -> None:
    make_user("Vendeur", "va_etre_desactive", actif=False)
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Vendeur")

    # Aucun utilisateur ACTIF de rôle Vendeur : le garde-fou ne s'applique pas.
    updated = stack.roles.update_role_permissions(role_id, [])

    assert stack.roles.get_role_permissions(role_id) == []
    assert updated.nombre_utilisateurs_actifs == 0


# -- lecture seule vis-à-vis des utilisateurs --------------------------------------------


def test_update_role_permissions_never_touches_users_or_passwords(login_as, make_user) -> None:
    make_user("Vendeur", "cible_intacte", "MotDePasseInitial1")
    stack, _ = login_as("Administrateur")
    role_id = _role_id(stack, "Vendeur")

    stack.roles.update_role_permissions(role_id, ["SALE_VIEW"])

    with session_scope(None) as session:
        from app.models.user import User

        user = session.query(User).filter_by(username="cible_intacte").one()
        assert user.role_id == role_id  # rôle inchangé
        assert verify_password("MotDePasseInitial1", user.password_hash) is True


# -- effet à la prochaine connexion -----------------------------------------------------


def test_permission_changes_apply_only_at_next_login(login_as, make_user, make_stack) -> None:
    make_user("Vendeur", "session_test", "MotDePasseInitial1")
    admin_stack, _ = login_as("Administrateur")
    role_id = _role_id(admin_stack, "Vendeur")

    # Deuxième pile de services indépendante, pointant vers la même base,
    # pour simuler une session déjà ouverte distincte de la session admin.
    vendeur_stack = make_stack()
    vendeur_current = vendeur_stack.auth.login("session_test", "MotDePasseInitial1")
    permissions_before = vendeur_current.permissions

    admin_stack.roles.update_role_permissions(role_id, ["ARTICLE_VIEW"])  # retire SALE_* etc.

    # La session déjà ouverte garde ses permissions déjà chargées.
    assert vendeur_stack.permissions.current_user.permissions == permissions_before

    vendeur_stack.auth.logout()
    reconnected = vendeur_stack.auth.login("session_test", "MotDePasseInitial1")

    assert reconnected.permissions == frozenset({"ARTICLE_VIEW"})
