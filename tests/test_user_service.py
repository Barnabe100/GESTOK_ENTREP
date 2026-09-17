from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError


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
