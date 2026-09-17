import logging
import sys

from app.config.settings import Settings
from app.db.session import session_scope
from app.main import bootstrap
from app.models.rbac import Role
from app.utils import error_handler


def test_bootstrap_initializes_database_and_seeds_reference_data(test_settings: Settings) -> None:
    bootstrap()

    assert test_settings.db_path.exists()
    with session_scope(test_settings) as session:
        roles = {r.nom for r in session.query(Role).all()}
    assert roles == {"Administrateur", "Gestionnaire de stock", "Vendeur", "Consultation"}


def test_bootstrap_installs_global_exception_handler(test_settings: Settings) -> None:
    original_hook = sys.excepthook
    try:
        bootstrap()
        assert sys.excepthook is error_handler.handle_exception
    finally:
        sys.excepthook = original_hook


def test_bootstrap_configures_logging_with_settings_log_level(test_settings: Settings) -> None:
    bootstrap()
    logger = logging.getLogger("stockmanager")
    assert logger.level == logging.DEBUG  # STOCKMANAGER_LOG_LEVEL=DEBUG dans test_settings


def test_bootstrap_is_idempotent(test_settings: Settings) -> None:
    bootstrap()
    bootstrap()  # ne doit pas échouer ni dupliquer les données de référence

    with session_scope(test_settings) as session:
        assert session.query(Role).count() == 4
