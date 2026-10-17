import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import session_scope
from app.models.account_recovery import AdminRecoveryCode
from app.models.rbac import Role
from app.models.user import User
from app.security.password_hashing import hash_password


def _create_admin(session) -> User:
    role = session.query(Role).filter_by(nom="Administrateur").one()
    user = User(username="admin_model_test", password_hash=hash_password("Password!23"), role_id=role.id, roles=[role])
    session.add(user)
    session.flush()
    return user


def test_admin_recovery_code_can_be_created(initialized_db) -> None:
    with session_scope(initialized_db) as session:
        user = _create_admin(session)
        session.add(AdminRecoveryCode(user_id=user.id, code_hash=hash_password("un-code-quelconque")))

    with session_scope(initialized_db) as session:
        row = session.query(AdminRecoveryCode).one()
        assert row.failed_attempts == 0
        assert row.consumed_at is None
        assert row.locked_until is None


def test_user_id_is_unique_one_active_code_per_user(initialized_db) -> None:
    with session_scope(initialized_db) as session:
        user = _create_admin(session)
        session.add(AdminRecoveryCode(user_id=user.id, code_hash=hash_password("premier-code")))

    with pytest.raises(IntegrityError):
        with session_scope(initialized_db) as session:
            session.add(AdminRecoveryCode(user_id=user.id, code_hash=hash_password("second-code")))


def test_recovery_code_relates_to_its_user(initialized_db) -> None:
    with session_scope(initialized_db) as session:
        user = _create_admin(session)
        session.add(AdminRecoveryCode(user_id=user.id, code_hash=hash_password("un-code")))

    with session_scope(initialized_db) as session:
        row = session.query(AdminRecoveryCode).one()
        assert row.user.username == "admin_model_test"
