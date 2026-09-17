from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError


def test_list_users_as_administrateur(login_as, make_user) -> None:
    make_user("Vendeur", "un_vendeur")
    _, _, user_service, _ = login_as("Administrateur")

    users = user_service.list_users()

    usernames = {u.username for u in users}
    assert "un_vendeur" in usernames
    assert any(u.role_name == "Administrateur" for u in users)


def test_list_users_denied_for_vendeur(login_as) -> None:
    """Le Vendeur n'a pas USER_VIEW : la consultation de la liste est refusée côté service."""
    _, _, user_service, _ = login_as("Vendeur")

    try:
        user_service.list_users()
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_set_active_as_administrateur_succeeds(login_as, make_user) -> None:
    make_user("Vendeur", "target_user")
    _, _, user_service, _ = login_as("Administrateur")

    target_id = next(u.id for u in user_service.list_users() if u.username == "target_user")
    updated = user_service.set_active(target_id, False)

    assert updated.actif is False


def test_set_active_denied_for_vendeur_even_by_direct_service_call(login_as, make_user) -> None:
    """Contournement de l'interface : même en appelant directement le service (sans passer
    par un bouton d'UI masqué/désactivé), l'action reste refusée pour un rôle non autorisé."""
    make_user("Vendeur", "victime")
    _, _, user_service, _ = login_as("Vendeur")

    # Un Vendeur n'a pas non plus USER_VIEW : on ne peut même pas lister -> on cible un id arbitraire.
    try:
        user_service.set_active(999999, False)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_set_active_denied_for_gestionnaire_stock(login_as, make_user) -> None:
    """Le Gestionnaire de stock gère le catalogue mais pas les comptes utilisateurs."""
    make_user("Vendeur", "cible_gestionnaire")
    _, _, user_service, _ = login_as("Gestionnaire de stock")

    try:
        user_service.set_active(1, False)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_set_active_unknown_user_raises_not_found(login_as) -> None:
    _, _, user_service, _ = login_as("Administrateur")

    try:
        user_service.set_active(999999, False)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_reset_password_as_administrateur_succeeds_and_forces_change(login_as, make_user) -> None:
    make_user("Vendeur", "reset_target", "MotDePasseInitial1")
    auth_service, _, user_service, _ = login_as("Administrateur")

    target_id = next(u.id for u in user_service.list_users() if u.username == "reset_target")
    user_service.reset_password(target_id, "NouveauMotDePasse99")

    auth_service.logout()
    target_current_user = auth_service.login("reset_target", "NouveauMotDePasse99")
    assert target_current_user.must_change_password is True


def test_reset_password_denied_for_consultation(login_as, make_user) -> None:
    make_user("Vendeur", "reset_target2")
    _, _, user_service, _ = login_as("Consultation")

    try:
        user_service.reset_password(1, "NouveauMotDePasse99")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_reset_password_too_short_is_rejected(login_as, make_user) -> None:
    make_user("Vendeur", "reset_target3")
    _, _, user_service, _ = login_as("Administrateur")

    target_id = next(u.id for u in user_service.list_users() if u.username == "reset_target3")
    try:
        user_service.reset_password(target_id, "court")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass
