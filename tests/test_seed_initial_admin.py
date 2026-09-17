from app.config.settings import Settings
from app.db.seed import INITIAL_ADMIN_USERNAME, seed_initial_admin
from app.db.session import session_scope
from app.models.user import User
from app.security.password_hashing import verify_password


def test_seed_initial_admin_creates_admin_when_no_users_exist(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        generated_password = seed_initial_admin(session)

    assert generated_password is not None
    assert len(generated_password) >= 12

    with session_scope(initialized_db) as session:
        admin = session.query(User).filter_by(username=INITIAL_ADMIN_USERNAME).one()
        assert admin.role.nom == "Administrateur"
        assert admin.actif is True
        assert admin.must_change_password is True
        assert verify_password(generated_password, admin.password_hash) is True


def test_seed_initial_admin_is_a_no_op_if_users_already_exist(initialized_db: Settings, make_user) -> None:
    make_user("Vendeur", "quelqu_un_existe_deja")

    with session_scope(initialized_db) as session:
        result = seed_initial_admin(session)

    assert result is None
    with session_scope(initialized_db) as session:
        assert session.query(User).filter_by(username=INITIAL_ADMIN_USERNAME).one_or_none() is None
