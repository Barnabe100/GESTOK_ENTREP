from app.config.settings import Settings
from app.db.seed import ROLE_PERMISSIONS_MATRIX, seed_reference_data
from app.db.session import session_scope
from app.models.rbac import Permission, Role


def test_seed_creates_four_roles(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        roles = {r.nom for r in session.query(Role).all()}
    assert roles == {"Administrateur", "Gestionnaire de stock", "Vendeur", "Consultation"}


def test_seed_creates_expected_permission_count(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        count = session.query(Permission).count()
    assert count == len(ROLE_PERMISSIONS_MATRIX["Administrateur"])


def test_administrateur_has_every_permission(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        admin = session.query(Role).filter_by(nom="Administrateur").one()
        admin_permission_count = len(admin.permissions)  # charger avant fermeture de la session
        total_permissions = session.query(Permission).count()
    assert admin_permission_count == total_permissions


def test_vendeur_can_sell_but_not_manage_entries(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        vendeur = session.query(Role).filter_by(nom="Vendeur").one()
        codes = {p.code for p in vendeur.permissions}
    assert "SALE_CREATE" in codes
    assert "SALE_VALIDATE" in codes
    assert "STOCK_ENTRY_CREATE" not in codes
    assert "SALE_CANCEL" not in codes  # réservé à l'Administrateur


def test_only_administrateur_can_cancel_operations(initialized_db: Settings) -> None:
    cancel_codes = {"STOCK_ENTRY_CANCEL", "STOCK_EXIT_CANCEL", "SALE_CANCEL"}
    with session_scope(initialized_db) as session:
        for role in session.query(Role).all():
            role_codes = {p.code for p in role.permissions}
            if role.nom == "Administrateur":
                assert cancel_codes.issubset(role_codes)
            else:
                assert role_codes.isdisjoint(cancel_codes)


def test_seed_is_idempotent_without_force(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        seed_reference_data(session)  # ne doit rien dupliquer (roles déjà présents)
        role_count = session.query(Role).count()
    assert role_count == 4
