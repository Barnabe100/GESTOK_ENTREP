from app.db.seed import INITIAL_ADMIN_USERNAME
from app.services.onboarding.onboarding_service import OnboardingService


def test_not_completed_by_default(initialized_db) -> None:
    service = OnboardingService(initialized_db)

    assert service.is_completed() is False


def test_mark_completed_persists_across_instances(initialized_db) -> None:
    OnboardingService(initialized_db).mark_completed()

    assert OnboardingService(initialized_db).is_completed() is True


def test_should_show_automatically_for_initial_admin_username(initialized_db) -> None:
    service = OnboardingService(initialized_db)

    assert service.should_show_automatically(
        INITIAL_ADMIN_USERNAME, initial_admin_username=INITIAL_ADMIN_USERNAME
    ) is True


def test_should_show_automatically_is_false_for_other_username(initialized_db) -> None:
    """Un utilisateur autre que le compte administrateur initial (y compris
    un second Administrateur créé plus tard) ne déclenche jamais le guidage
    automatique."""
    service = OnboardingService(initialized_db)

    assert service.should_show_automatically(
        "un_autre_admin", initial_admin_username=INITIAL_ADMIN_USERNAME
    ) is False


def test_should_show_automatically_is_false_once_completed(initialized_db) -> None:
    service = OnboardingService(initialized_db)
    service.mark_completed()

    assert service.should_show_automatically(
        INITIAL_ADMIN_USERNAME, initial_admin_username=INITIAL_ADMIN_USERNAME
    ) is False
