from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.services.auth.auth_service import AuthService
from app.utils.exceptions import AccountDisabledError, InvalidCredentialsError, ValidationError


def test_login_success_returns_current_user_with_permissions(make_user, make_stack) -> None:
    make_user("Administrateur", "alice", "Password!23")
    auth_service = make_stack().auth

    current_user = auth_service.login("alice", "Password!23")

    assert current_user.username == "alice"
    assert current_user.role_name == "Administrateur"
    assert "USER_VIEW" in current_user.permissions
    assert auth_service.is_authenticated is True
    assert auth_service.current_user is current_user


def test_login_success_is_audited(make_user, make_stack, initialized_db: Settings) -> None:
    make_user("Administrateur", "alice", "Password!23")
    auth_service = make_stack().auth

    auth_service.login("alice", "Password!23")

    with session_scope(initialized_db) as session:
        entries = session.query(AuditLog).filter_by(action="LOGIN").all()
    assert any(e.resultat == ResultatAudit.SUCCES for e in entries)


def test_login_wrong_password_is_rejected(make_user, make_stack) -> None:
    make_user("Vendeur", "bob", "Password!23")
    auth_service = make_stack().auth

    try:
        auth_service.login("bob", "MauvaisMotDePasse")
        assert False, "devait lever InvalidCredentialsError"
    except InvalidCredentialsError:
        pass

    assert auth_service.is_authenticated is False


def test_login_wrong_password_is_audited_as_failure(make_user, make_stack, initialized_db: Settings) -> None:
    make_user("Vendeur", "bob", "Password!23")
    auth_service = make_stack().auth

    try:
        auth_service.login("bob", "MauvaisMotDePasse")
    except InvalidCredentialsError:
        pass

    with session_scope(initialized_db) as session:
        entries = session.query(AuditLog).filter_by(action="LOGIN").all()
    assert any(e.resultat == ResultatAudit.ECHEC for e in entries)


def test_login_unknown_username_is_rejected(make_stack) -> None:
    auth_service = make_stack().auth

    try:
        auth_service.login("utilisateur_qui_n_existe_pas", "peu importe")
        assert False, "devait lever InvalidCredentialsError"
    except InvalidCredentialsError:
        pass

    assert auth_service.is_authenticated is False


def test_login_unknown_username_is_audited_without_user_id(
    make_stack, initialized_db: Settings
) -> None:
    auth_service = make_stack().auth

    try:
        auth_service.login("fantome", "peu importe")
    except InvalidCredentialsError:
        pass

    with session_scope(initialized_db) as session:
        entry = (
            session.query(AuditLog)
            .filter_by(action="LOGIN", resultat=ResultatAudit.ECHEC)
            .order_by(AuditLog.id.desc())
            .first()
        )
    assert entry is not None
    assert entry.user_id is None


def test_login_disabled_account_is_rejected(make_user, make_stack) -> None:
    make_user("Vendeur", "carla", "Password!23", actif=False)
    auth_service = make_stack().auth

    try:
        auth_service.login("carla", "Password!23")
        assert False, "devait lever AccountDisabledError"
    except AccountDisabledError:
        pass

    assert auth_service.is_authenticated is False


def test_login_disabled_account_with_wrong_password_reveals_nothing(make_user, make_stack) -> None:
    """Un mot de passe erroné sur un compte désactivé doit rester une simple erreur
    d'identifiants (ne jamais révéler le statut du compte sans mot de passe valide)."""
    make_user("Vendeur", "carla2", "Password!23", actif=False)
    auth_service = make_stack().auth

    try:
        auth_service.login("carla2", "MauvaisMotDePasse")
        assert False, "devait lever InvalidCredentialsError"
    except InvalidCredentialsError:
        pass


def test_logout_clears_current_user(make_user, make_stack) -> None:
    make_user("Administrateur", "dave", "Password!23")
    auth_service = make_stack().auth
    auth_service.login("dave", "Password!23")

    auth_service.logout()

    assert auth_service.is_authenticated is False
    assert auth_service.current_user is None


def test_logout_is_audited(make_user, make_stack, initialized_db: Settings) -> None:
    make_user("Administrateur", "dave2", "Password!23")
    auth_service = make_stack().auth
    auth_service.login("dave2", "Password!23")

    auth_service.logout()

    with session_scope(initialized_db) as session:
        entries = session.query(AuditLog).filter_by(action="LOGOUT").all()
    assert len(entries) == 1
    assert entries[0].resultat == ResultatAudit.SUCCES


def test_logout_without_login_is_a_no_op(make_stack) -> None:
    auth_service = make_stack().auth
    auth_service.logout()  # ne doit pas lever
    assert auth_service.is_authenticated is False


def test_change_password_success(make_user, make_stack) -> None:
    make_user("Vendeur", "elise", "AncienMotDePasse1")
    auth_service = make_stack().auth
    auth_service.login("elise", "AncienMotDePasse1")

    auth_service.change_password("AncienMotDePasse1", "NouveauMotDePasse1")

    auth_service.logout()
    auth_service.login("elise", "NouveauMotDePasse1")  # doit fonctionner avec le nouveau mot de passe
    assert auth_service.is_authenticated is True


def test_change_password_wrong_old_password_is_rejected(make_user, make_stack) -> None:
    make_user("Vendeur", "felix", "AncienMotDePasse1")
    auth_service = make_stack().auth
    auth_service.login("felix", "AncienMotDePasse1")

    try:
        auth_service.change_password("MauvaisAncien", "NouveauMotDePasse1")
        assert False, "devait lever InvalidCredentialsError"
    except InvalidCredentialsError:
        pass


def test_change_password_too_short_is_rejected(make_user, make_stack) -> None:
    make_user("Vendeur", "gina", "AncienMotDePasse1")
    auth_service = make_stack().auth
    auth_service.login("gina", "AncienMotDePasse1")

    try:
        auth_service.change_password("AncienMotDePasse1", "court")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_change_password_clears_must_change_password_flag(make_stack, initialized_db: Settings) -> None:
    from app.db.seed import seed_initial_admin

    with session_scope(initialized_db) as session:
        generated_password = seed_initial_admin(session)
    assert generated_password is not None

    auth_service = make_stack().auth
    current_user = auth_service.login("admin", generated_password)
    assert current_user.must_change_password is True

    auth_service.change_password(generated_password, "NouveauMotDePasseSolide1")

    assert auth_service.current_user.must_change_password is False
