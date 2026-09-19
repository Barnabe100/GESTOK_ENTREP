import pytest

from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.rbac import Role
from app.security.password_hashing import verify_password
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def test_list_users_as_administrateur(login_as, make_user) -> None:
    make_user("Vendeur", "un_vendeur")
    stack, _ = login_as("Administrateur")

    users = stack.users.list_users()

    usernames = {u.username for u in users}
    assert "un_vendeur" in usernames
    assert any(u.role_name == "Administrateur" for u in users)


def test_list_users_denied_for_vendeur(login_as) -> None:
    """Le Vendeur n'a pas USER_VIEW : la consultation de la liste est refusée côté service."""
    stack, _ = login_as("Vendeur")

    try:
        stack.users.list_users()
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_set_active_as_administrateur_succeeds(login_as, make_user) -> None:
    make_user("Vendeur", "target_user")
    stack, _ = login_as("Administrateur")

    target_id = next(u.id for u in stack.users.list_users() if u.username == "target_user")
    updated = stack.users.set_active(target_id, False)

    assert updated.actif is False


def test_set_active_denied_for_vendeur_even_by_direct_service_call(login_as, make_user) -> None:
    """Contournement de l'interface : même en appelant directement le service (sans passer
    par un bouton d'UI masqué/désactivé), l'action reste refusée pour un rôle non autorisé."""
    make_user("Vendeur", "victime")
    stack, _ = login_as("Vendeur")

    # Un Vendeur n'a pas non plus USER_VIEW : on ne peut même pas lister -> on cible un id arbitraire.
    try:
        stack.users.set_active(999999, False)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_set_active_denied_for_gestionnaire_stock(login_as, make_user) -> None:
    """Le Gestionnaire de stock gère le catalogue mais pas les comptes utilisateurs."""
    make_user("Vendeur", "cible_gestionnaire")
    stack, _ = login_as("Gestionnaire de stock")

    try:
        stack.users.set_active(1, False)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_set_active_unknown_user_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.users.set_active(999999, False)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_reset_password_as_administrateur_succeeds_and_forces_change(login_as, make_user) -> None:
    make_user("Vendeur", "reset_target", "MotDePasseInitial1")
    stack, _ = login_as("Administrateur")

    target_id = next(u.id for u in stack.users.list_users() if u.username == "reset_target")
    stack.users.reset_password(target_id, "NouveauMotDePasse99")

    stack.auth.logout()
    target_current_user = stack.auth.login("reset_target", "NouveauMotDePasse99")
    assert target_current_user.must_change_password is True


def test_reset_password_denied_for_consultation(login_as, make_user) -> None:
    make_user("Vendeur", "reset_target2")
    stack, _ = login_as("Consultation")

    try:
        stack.users.reset_password(1, "NouveauMotDePasse99")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_reset_password_too_short_is_rejected(login_as, make_user) -> None:
    make_user("Vendeur", "reset_target3")
    stack, _ = login_as("Administrateur")

    target_id = next(u.id for u in stack.users.list_users() if u.username == "reset_target3")
    try:
        stack.users.reset_password(target_id, "court")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


# -- création d'utilisateur ----------------------------------------------------------


def _role_id(role_name: str) -> int:
    with session_scope(None) as session:
        return session.query(Role).filter_by(nom=role_name).one().id


def test_create_user_as_administrateur_succeeds(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")

    summary = stack.users.create_user("nouveau_vendeur", "MotDePasse!23", role_id, actif=True)

    assert summary.username == "nouveau_vendeur"
    assert summary.role_name == "Vendeur"
    assert summary.actif is True


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_create_user_succeeds_for_each_non_admin_role(login_as, role_name: str) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id(role_name)

    summary = stack.users.create_user(f"user_{role_name.split()[0].lower()}", "MotDePasse!23", role_id)

    assert summary.role_name == role_name
    users = stack.users.list_users()
    assert any(u.username == summary.username and u.role_name == role_name for u in users)


def test_create_user_with_administrateur_role_succeeds(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Administrateur")

    summary = stack.users.create_user("second_admin", "MotDePasse!23", role_id)

    assert summary.role_name == "Administrateur"


def test_create_user_denied_for_non_administrateur(login_as) -> None:
    stack, _ = login_as("Vendeur")
    role_id = _role_id("Vendeur")

    try:
        stack.users.create_user("intrus", "MotDePasse!23", role_id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_create_user_duplicate_username_raises_conflict(login_as, make_user) -> None:
    make_user("Vendeur", "deja_pris")
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")

    try:
        stack.users.create_user("deja_pris", "MotDePasse!23", role_id)
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_create_user_empty_username_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")

    try:
        stack.users.create_user("   ", "MotDePasse!23", role_id)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_user_short_password_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")

    try:
        stack.users.create_user("nouvel_utilisateur", "court", role_id)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_user_unknown_role_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.users.create_user("nouvel_utilisateur", "MotDePasse!23", 999999)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_create_user_can_be_created_inactive(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")

    summary = stack.users.create_user("compte_inactif", "MotDePasse!23", role_id, actif=False)

    assert summary.actif is False


def test_create_user_forces_must_change_password(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")
    stack.users.create_user("doit_changer", "MotDePasseInitial1", role_id)

    logged_in_user = stack.auth.login("doit_changer", "MotDePasseInitial1")

    assert logged_in_user.must_change_password is True


def test_create_user_password_is_hashed_never_plaintext(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")
    stack.users.create_user("hash_check", "MotDePasseSecret1", role_id)

    with session_scope(None) as session:
        from app.models.user import User

        user = session.query(User).filter_by(username="hash_check").one()
        assert user.password_hash != "MotDePasseSecret1"
        assert verify_password("MotDePasseSecret1", user.password_hash) is True


def test_create_user_writes_audit_log(login_as) -> None:
    stack, admin_user = login_as("Administrateur")
    role_id = _role_id("Vendeur")
    summary = stack.users.create_user("audite", "MotDePasse!23", role_id)

    with session_scope(None) as session:
        entries = session.query(AuditLog).filter_by(action="USER_CREATE", entite_id=summary.id).all()
        assert len(entries) == 1
        assert entries[0].user_id == admin_user.id


def test_list_roles_returns_all_seeded_roles(login_as) -> None:
    stack, _ = login_as("Administrateur")

    roles = {r.nom for r in stack.users.list_roles()}

    assert roles == {"Administrateur", "Gestionnaire de stock", "Vendeur", "Consultation"}


def test_list_roles_denied_for_non_administrateur(login_as) -> None:
    stack, _ = login_as("Vendeur")

    try:
        stack.users.list_roles()
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


# -- modification du rôle (lot Gestion complète des utilisateurs) --------------------


def test_update_user_as_administrateur_succeeds(login_as, make_user) -> None:
    make_user("Vendeur", "cible_role")
    stack, _ = login_as("Administrateur")
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_role")
    role_id = _role_id("Gestionnaire de stock")

    updated = stack.users.update_user(target_id, role_id)

    assert updated.role_name == "Gestionnaire de stock"


def test_update_user_unknown_role_raises_not_found(login_as, make_user) -> None:
    make_user("Vendeur", "cible_role_inconnu")
    stack, _ = login_as("Administrateur")
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_role_inconnu")

    try:
        stack.users.update_user(target_id, 999999)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_update_user_unknown_user_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")

    try:
        stack.users.update_user(999999, role_id)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_update_user_denied_for_non_administrateur(login_as, make_user) -> None:
    make_user("Vendeur", "cible_refus")
    stack, _ = login_as("Vendeur")
    role_id = _role_id("Gestionnaire de stock")

    try:
        stack.users.update_user(1, role_id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_update_user_writes_audit_log(login_as, make_user) -> None:
    make_user("Vendeur", "cible_audit")
    stack, admin_user = login_as("Administrateur")
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_audit")
    role_id = _role_id("Consultation")

    stack.users.update_user(target_id, role_id)

    with session_scope(None) as session:
        entries = session.query(AuditLog).filter_by(action="USER_UPDATE", entite_id=target_id).all()
        assert len(entries) == 1
        assert entries[0].user_id == admin_user.id


def test_update_user_does_not_change_username_or_password(login_as, make_user) -> None:
    make_user("Vendeur", "cible_inchangee", "MotDePasseInitial1")
    stack, _ = login_as("Administrateur")
    target_id = next(u.id for u in stack.users.list_users() if u.username == "cible_inchangee")
    role_id = _role_id("Gestionnaire de stock")

    stack.users.update_user(target_id, role_id)

    with session_scope(None) as session:
        from app.models.user import User

        user = session.get(User, target_id)
        assert user.username == "cible_inchangee"
        assert verify_password("MotDePasseInitial1", user.password_hash) is True


def test_update_user_cannot_remove_own_administrateur_role(login_as) -> None:
    """§6 : un administrateur ne peut pas retirer son propre rôle Administrateur."""
    stack, current_user = login_as("Administrateur")
    role_id = _role_id("Vendeur")

    try:
        stack.users.update_user(current_user.id, role_id)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass

    with session_scope(None) as session:
        from app.models.user import User

        user = session.get(User, current_user.id)
        assert user.role.nom == "Administrateur"


def test_update_user_can_change_another_administrateur_role(login_as) -> None:
    """Un administrateur peut rétrograder un AUTRE administrateur (seule
    l'auto-rétrogradation est bloquée)."""
    stack, _ = login_as("Administrateur")
    role_id = _role_id("Vendeur")
    admin_role_id = _role_id("Administrateur")
    other_admin = stack.users.create_user("autre_admin", "MotDePasse!23", admin_role_id)

    updated = stack.users.update_user(other_admin.id, role_id)

    assert updated.role_name == "Vendeur"


# -- protection du dernier administrateur actif (§6) ----------------------------------


def test_set_active_cannot_deactivate_last_active_administrateur(login_as) -> None:
    stack, current_user = login_as("Administrateur")

    try:
        stack.users.set_active(current_user.id, False)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass

    with session_scope(None) as session:
        from app.models.user import User

        user = session.get(User, current_user.id)
        assert user.actif is True


def test_set_active_can_deactivate_administrateur_when_another_active_admin_exists(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    admin_role_id = _role_id("Administrateur")
    other_admin = stack.users.create_user("second_admin_actif", "MotDePasse!23", admin_role_id)

    updated = stack.users.set_active(other_admin.id, False)

    assert updated.actif is False


# -- LOT F : la démotion d'un PAIR administrateur ne doit jamais faire passer ---------
# -- le nombre d'administrateurs actifs de 1 à 0 (même garde-fou que set_active) ------


def test_update_user_two_active_admins_peer_demotion_succeeds_and_actor_stays_admin(login_as) -> None:
    """§A : deux administrateurs actifs, A modifie le rôle de B → succès,
    A reste Administrateur actif (le nombre d'administrateurs actifs passe
    de 2 à 1, jamais à 0)."""
    stack, admin_a = login_as("Administrateur")
    admin_role_id = _role_id("Administrateur")
    vendeur_role_id = _role_id("Vendeur")
    admin_b = stack.users.create_user("admin_b_peer", "MotDePasse!23", admin_role_id)

    updated_b = stack.users.update_user(admin_b.id, vendeur_role_id)

    assert updated_b.role_name == "Vendeur"
    with session_scope(None) as session:
        from app.models.user import User

        admin_a_row = session.get(User, admin_a.id)
        assert admin_a_row.role.nom == "Administrateur"
        assert admin_a_row.actif is True


def test_update_user_demoting_peer_admin_leaves_exactly_one_active_admin(login_as) -> None:
    """§C : après démotion d'un administrateur pair, il reste exactement un
    administrateur actif (jamais zéro) — vérifié directement en base."""
    stack, admin_a = login_as("Administrateur")
    admin_role_id = _role_id("Administrateur")
    consultation_role_id = _role_id("Consultation")
    admin_b = stack.users.create_user("admin_b_target", "MotDePasse!23", admin_role_id)

    stack.users.update_user(admin_b.id, consultation_role_id)

    with session_scope(None) as session:
        from app.models.rbac import Role
        from app.models.user import User

        active_admin_count = (
            session.query(User)
            .join(Role)
            .filter(Role.nom == "Administrateur", User.actif.is_(True))
            .count()
        )
        assert active_admin_count == 1


def test_update_user_non_admin_role_with_user_update_cannot_demote_last_active_admin(login_as) -> None:
    """§D : le garde-fou porte sur le COMPTE ciblé, pas sur le rôle de
    l'acteur. Un rôle non-Administrateur ayant reçu ``USER_UPDATE`` via
    l'écran Rôles/Permissions (Lot C) ne doit pas pouvoir, via cette
    permission déléguée, retirer le rôle Administrateur du dernier compte
    Administrateur actif — c'était le seul chemin par lequel l'ancienne
    garde (limitée à l'auto-démotion) pouvait être contournée."""
    stack, admin_a = login_as("Administrateur")
    vendeur_role_id = _role_id("Vendeur")
    current_vendeur_codes = stack.roles.get_role_permissions(vendeur_role_id)
    stack.roles.update_role_permissions(vendeur_role_id, current_vendeur_codes + ["USER_UPDATE"])

    vendeur_stack, _ = login_as("Vendeur")
    consultation_role_id = _role_id("Consultation")

    try:
        vendeur_stack.users.update_user(admin_a.id, consultation_role_id)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass

    with session_scope(None) as session:
        from app.models.user import User

        admin_a_row = session.get(User, admin_a.id)
        assert admin_a_row.role.nom == "Administrateur"
        assert admin_a_row.actif is True


def test_set_active_non_admin_role_with_user_activate_cannot_deactivate_last_active_admin(login_as) -> None:
    """Même invariant que le test précédent, appliqué à la désactivation
    (``set_active``) : ce garde-fou existait déjà (compte des
    administrateurs actifs, sans condition sur l'acteur) et n'a pas eu
    besoin d'être modifié par le Lot F — ce test le documente/consolide."""
    stack, admin_a = login_as("Administrateur")
    vendeur_role_id = _role_id("Vendeur")
    current_vendeur_codes = stack.roles.get_role_permissions(vendeur_role_id)
    stack.roles.update_role_permissions(vendeur_role_id, current_vendeur_codes + ["USER_ACTIVATE"])

    vendeur_stack, _ = login_as("Vendeur")

    try:
        vendeur_stack.users.set_active(admin_a.id, False)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass

    with session_scope(None) as session:
        from app.models.user import User

        admin_a_row = session.get(User, admin_a.id)
        assert admin_a_row.actif is True
