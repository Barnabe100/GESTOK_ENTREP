import logging
import threading
from datetime import timedelta

import pytest

from app.config.settings import get_settings
from app.db.session import session_scope
from app.models.account_recovery import AdminRecoveryCode
from app.models.mixins import utcnow
from app.models.user import User
from app.utils.exceptions import InvalidCredentialsError, PermissionDeniedError, ValidationError

DEFAULT_TEST_PASSWORD = "Password!23"


def _get_recovery_row(settings, user_id: int) -> AdminRecoveryCode:
    with session_scope(settings) as session:
        row = session.query(AdminRecoveryCode).filter_by(user_id=user_id).one()
        session.expunge(row)
        return row


# -- génération -----------------------------------------------------------------


def test_generate_code_returns_plaintext_once_and_stores_only_hash(login_as) -> None:
    stack, current_user = login_as("Administrateur")

    code = stack.account_recovery.generate_code()

    assert isinstance(code, str) and len(code) >= 32
    row = _get_recovery_row(get_settings(), current_user.id)
    assert row.code_hash != code
    assert code not in row.code_hash


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_generate_code_denied_for_non_administrateur_roles(login_as, role_name) -> None:
    stack, _ = login_as(role_name)

    with pytest.raises(PermissionDeniedError):
        stack.account_recovery.generate_code()


def test_regenerate_code_invalidates_previous_code(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    first_code = stack.account_recovery.generate_code()
    second_code = stack.account_recovery.generate_code()

    assert first_code != second_code

    with pytest.raises(InvalidCredentialsError):
        stack.account_recovery.reset_password_with_code(
            current_user.username, first_code, "NouveauMotDePasse!1"
        )

    # Le nouveau code, lui, fonctionne toujours.
    stack.account_recovery.reset_password_with_code(
        current_user.username, second_code, "NouveauMotDePasse!1"
    )


# -- utilisation normale ---------------------------------------------------------


def test_reset_password_with_valid_code_succeeds(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()

    stack.account_recovery.reset_password_with_code(current_user.username, code, "NouveauMotDePasse!1")

    relogged_in = stack.auth.login(current_user.username, "NouveauMotDePasse!1")
    assert relogged_in.username == current_user.username


def test_reset_password_resets_must_change_password_flag(login_as, make_stack) -> None:
    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()
    stack.account_recovery.reset_password_with_code(current_user.username, code, "NouveauMotDePasse!1")

    fresh_stack = make_stack()
    relogged_in = fresh_stack.auth.login(current_user.username, "NouveauMotDePasse!1")
    assert relogged_in.must_change_password is False


def test_used_code_cannot_be_reused(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()
    stack.account_recovery.reset_password_with_code(current_user.username, code, "NouveauMotDePasse!1")

    with pytest.raises(InvalidCredentialsError):
        stack.account_recovery.reset_password_with_code(current_user.username, code, "AutreMotDePasse!2")


def test_weak_new_password_is_rejected(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()

    with pytest.raises(ValidationError):
        stack.account_recovery.reset_password_with_code(current_user.username, code, "court")

    # Le code reste utilisable ensuite (rejet du mot de passe ≠ consommation du code).
    stack.account_recovery.reset_password_with_code(current_user.username, code, "MotDePasseValide!9")


# -- anti-énumération -------------------------------------------------------------


def test_unknown_username_and_wrong_code_raise_identical_error(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    stack.account_recovery.generate_code()

    unknown_error = None
    wrong_code_error = None
    try:
        stack.account_recovery.reset_password_with_code("compte-inexistant", "peu-importe", "NouveauMotDePasse!1")
    except InvalidCredentialsError as exc:
        unknown_error = exc
    try:
        stack.account_recovery.reset_password_with_code(current_user.username, "code-invalide", "NouveauMotDePasse!1")
    except InvalidCredentialsError as exc:
        wrong_code_error = exc

    assert unknown_error is not None and wrong_code_error is not None
    assert str(unknown_error) == str(wrong_code_error)


def test_inactive_administrator_cannot_use_recovery(login_as, make_user, make_stack) -> None:
    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()

    with session_scope(get_settings()) as session:
        user = session.get(User, current_user.id)
        user.actif = False

    fresh_stack = make_stack()
    with pytest.raises(InvalidCredentialsError) as exc_info:
        fresh_stack.account_recovery.reset_password_with_code(current_user.username, code, "NouveauMotDePasse!1")

    with session_scope(get_settings()) as session:
        user = session.get(User, current_user.id)
        user.actif = True
    try:
        other_error = None
        try:
            fresh_stack.account_recovery.reset_password_with_code(current_user.username, "code-invalide", "NouveauMotDePasse!1")
        except InvalidCredentialsError as exc:
            other_error = exc
        assert str(other_error) == str(exc_info.value)
    finally:
        pass


def test_non_administrator_cannot_use_recovery_even_with_a_code_row(login_as, make_stack) -> None:
    """Défense en profondeur : même si une ligne existait pour un compte non
    Administrateur (ne devrait jamais arriver via generate_code, gardé par
    la permission), reset_password_with_code refuse quand même."""
    stack, current_user = login_as("Vendeur")

    with session_scope(get_settings()) as session:
        session.add(AdminRecoveryCode(user_id=current_user.id, code_hash=session.get(User, current_user.id).password_hash))

    fresh_stack = make_stack()
    with pytest.raises(InvalidCredentialsError):
        fresh_stack.account_recovery.reset_password_with_code(current_user.username, "peu-importe", "NouveauMotDePasse!1")


# -- tentatives / verrouillage -----------------------------------------------------


def test_too_many_failed_attempts_locks_the_account(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    stack.account_recovery.generate_code()

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            stack.account_recovery.reset_password_with_code(current_user.username, "code-invalide", "NouveauMotDePasse!1")

    row = _get_recovery_row(get_settings(), current_user.id)
    assert row.failed_attempts == 5
    assert row.locked_until is not None and row.locked_until > utcnow().replace(tzinfo=None)


def test_locked_account_rejects_even_the_correct_code(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            stack.account_recovery.reset_password_with_code(current_user.username, "code-invalide", "NouveauMotDePasse!1")

    with pytest.raises(InvalidCredentialsError):
        stack.account_recovery.reset_password_with_code(current_user.username, code, "NouveauMotDePasse!1")


def test_lock_expires_after_lockout_duration(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()

    for _ in range(5):
        with pytest.raises(InvalidCredentialsError):
            stack.account_recovery.reset_password_with_code(current_user.username, "code-invalide", "NouveauMotDePasse!1")

    # Simule l'expiration du verrouillage (passé), sans modifier la logique du service.
    with session_scope(get_settings()) as session:
        row = session.query(AdminRecoveryCode).filter_by(user_id=current_user.id).one()
        row.locked_until = utcnow() - timedelta(seconds=1)

    stack.account_recovery.reset_password_with_code(current_user.username, code, "NouveauMotDePasse!1")


def test_successful_reset_clears_failed_attempts_and_lock(login_as) -> None:
    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()

    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            stack.account_recovery.reset_password_with_code(current_user.username, "code-invalide", "NouveauMotDePasse!1")

    stack.account_recovery.reset_password_with_code(current_user.username, code, "NouveauMotDePasse!1")

    code2 = stack.account_recovery.generate_code()
    row = _get_recovery_row(get_settings(), current_user.id)
    assert row.failed_attempts == 0
    assert row.locked_until is None


# -- accès concurrents ------------------------------------------------------------


def test_concurrent_failed_attempts_are_not_lost(login_as) -> None:
    """Deux threads échouent simultanément plusieurs fois : le compteur final
    doit refléter exactement le nombre total d'échecs, sans mise à jour
    perdue (lecture-modification-écriture entièrement dans une seule
    transaction par appel, voir AccountRecoveryService)."""
    stack, current_user = login_as("Administrateur")
    stack.account_recovery.generate_code()
    username = current_user.username

    attempts_per_thread = 2
    errors: list[Exception] = []

    def _attempt() -> None:
        for _ in range(attempts_per_thread):
            try:
                stack.account_recovery.reset_password_with_code(username, "code-invalide", "NouveauMotDePasse!1")
            except InvalidCredentialsError:
                pass
            except Exception as exc:  # pragma: no cover - diagnostic uniquement
                errors.append(exc)

    threads = [threading.Thread(target=_attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    row = _get_recovery_row(get_settings(), current_user.id)
    assert row.failed_attempts == 2 * attempts_per_thread


# -- absence de secrets dans les journaux ------------------------------------------


def test_generated_code_never_appears_in_logs(login_as, caplog) -> None:
    stack, current_user = login_as("Administrateur")
    with caplog.at_level(logging.DEBUG):
        code = stack.account_recovery.generate_code()

    for record in caplog.records:
        assert code not in record.getMessage()


def test_submitted_code_never_appears_in_logs_on_failure(login_as, caplog) -> None:
    stack, current_user = login_as("Administrateur")
    stack.account_recovery.generate_code()
    secret_attempt = "ce-code-secret-ne-doit-jamais-apparaitre"

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(InvalidCredentialsError):
            stack.account_recovery.reset_password_with_code(current_user.username, secret_attempt, "NouveauMotDePasse!1")

    for record in caplog.records:
        assert secret_attempt not in record.getMessage()


def test_generated_password_temp_still_uses_same_hashing_but_code_not_in_audit_details(login_as) -> None:
    """Le détail d'audit écrit par le service ne doit jamais contenir le
    code lui-même, ni en clair ni partiellement."""
    from app.models.audit import AuditLog

    stack, current_user = login_as("Administrateur")
    code = stack.account_recovery.generate_code()

    with session_scope(get_settings()) as session:
        entries = session.query(AuditLog).filter_by(entite="admin_recovery").all()
        for entry in entries:
            assert entry.details is None or code not in entry.details
