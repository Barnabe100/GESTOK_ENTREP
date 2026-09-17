from app.utils.exceptions import PermissionDeniedError


def test_has_permission_true_when_granted(login_as) -> None:
    _, permission_service, _, _ = login_as("Administrateur")
    assert permission_service.has_permission("USER_VIEW") is True


def test_has_permission_false_when_not_granted(login_as) -> None:
    _, permission_service, _, _ = login_as("Vendeur")
    assert permission_service.has_permission("STOCK_ENTRY_CREATE") is False


def test_has_permission_false_when_no_user_logged_in(make_stack) -> None:
    _, permission_service, _ = make_stack()
    assert permission_service.has_permission("ARTICLE_VIEW") is False


def test_require_permission_passes_silently_when_granted(login_as) -> None:
    _, permission_service, _, _ = login_as("Administrateur")
    permission_service.require_permission("BACKUP_RESTORE")  # ne doit pas lever


def test_require_permission_raises_when_denied(login_as) -> None:
    _, permission_service, _, _ = login_as("Vendeur")
    try:
        permission_service.require_permission("BACKUP_RESTORE")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_require_permission_raises_when_not_authenticated(make_stack) -> None:
    _, permission_service, _ = make_stack()
    try:
        permission_service.require_permission("ARTICLE_VIEW")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_permission_service_reflects_logout(login_as) -> None:
    auth_service, permission_service, _, _ = login_as("Administrateur")
    assert permission_service.has_permission("USER_VIEW") is True

    auth_service.logout()

    assert permission_service.has_permission("USER_VIEW") is False
