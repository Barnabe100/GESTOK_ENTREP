import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from app.db.session import session_scope
from app.repositories.parameter_repository import ParameterRepository
from app.views.onboarding_dialog import OnboardingDialog


def _build_dialog(stack, on_navigate=None):
    return OnboardingDialog(
        company_settings_service=stack.parameters,
        user_service=stack.users,
        license_service=stack.licenses,
        backup_service=stack.backups,
        onboarding_service=stack.onboarding,
        permission_service=stack.permissions,
        on_navigate=on_navigate or (lambda *a, **k: True),
    )


def _all_text(dialog) -> str:
    return " ".join(label.text() for label in dialog.findChildren(QLabel))


# -- contenu de base ----------------------------------------------------------------


def test_shows_intro_and_all_steps_for_administrateur(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    text = _all_text(dialog)
    assert "Informations de l'entreprise et devise" in text
    assert "Logo de l'entreprise" in text
    assert "Utilisateurs" in text
    assert "Licence" in text
    assert "sauvegarde" in text.lower()


def test_company_step_not_completed_by_default(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert "À faire" in _all_text(dialog)


def test_company_step_completed_once_name_configured(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.update_config(nom="Ma Société", adresse=None, telephone=None, email=None, devise="XOF")

    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert "Terminé" in _all_text(dialog)


def test_logo_step_completed_once_logo_path_configured(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    with session_scope(None) as session:
        ParameterRepository(session).set_value("entreprise.logo_path", "/tmp/logo.png")

    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert "Terminé" in _all_text(dialog)


def test_users_step_not_completed_with_only_the_current_admin(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert len(stack.users.list_users()) == 1  # seul l'admin courant existe

    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert "À faire" in _all_text(dialog)


def test_users_step_completed_once_a_second_user_exists(qtbot, login_as, make_user) -> None:
    stack, _ = login_as("Administrateur")
    make_user("Vendeur", "second_utilisateur")

    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert "Terminé" in _all_text(dialog)


def test_license_step_reflects_valid_test_license(qtbot, login_as) -> None:
    """La licence de test à accès complet (voir conftest) est VALIDE par
    défaut : l'étape licence doit donc apparaître terminée."""
    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    text = _all_text(dialog)
    assert "Licence" in text
    assert "Terminé" in text


def test_backup_step_not_completed_by_default(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    backups = stack.backups.list_backups()
    assert backups == []


def test_backup_step_completed_after_a_manual_backup(qtbot, login_as, tmp_path) -> None:
    stack, _ = login_as("Administrateur")
    destination = tmp_path / "backups"
    stack.backups.update_config(
        auto_enabled=False, frequency="daily", time_of_day="02:00", destination=str(destination), retention=10
    )
    stack.backups.create_manual_backup()

    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert "Terminé" in _all_text(dialog)


# -- permissions ----------------------------------------------------------------------


@pytest.mark.parametrize("role_name", ["Gestionnaire de stock", "Vendeur", "Consultation"])
def test_no_step_shown_for_roles_without_the_relevant_permissions(qtbot, login_as, role_name: str) -> None:
    """Aucune des permissions requises (SETTINGS_VIEW/USER_VIEW/LICENSE_VIEW/
    BACKUP_VIEW) n'est accordée à ces rôles : aucune étape ne doit
    apparaître, et aucune méthode gardée ne doit être appelée (voir test
    dédié ci-dessous)."""
    stack, _ = login_as(role_name)
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    # Le bouton « Fermer » reste toujours présent (le guidage doit rester
    # fermable) ; aucun bouton d'étape (« Configurer »/« Ouvrir ») ne l'est.
    step_buttons = [b for b in dialog.findChildren(QPushButton) if b.text() != "Fermer"]
    assert step_buttons == []


@pytest.mark.parametrize(
    "service_attr,method_name",
    [
        ("parameters", "get_config"),
        ("users", "list_users"),
        ("licenses", "get_info"),
        ("backups", "list_backups"),
    ],
)
def test_gated_service_method_never_called_without_permission(
    qtbot, login_as, monkeypatch, service_attr: str, method_name: str
) -> None:
    stack, _ = login_as("Vendeur")

    calls: list[object] = []
    service = getattr(stack, service_attr)
    original = getattr(type(service), method_name)
    monkeypatch.setattr(type(service), method_name, lambda self, *a, **k: calls.append(1) or original(self, *a, **k))

    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    assert calls == []


# -- fermeture / persistance -----------------------------------------------------------


def test_closing_button_marks_onboarding_completed(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    assert stack.onboarding.is_completed() is False

    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)
    close_button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Fermer")
    close_button.click()

    assert stack.onboarding.is_completed() is True


def test_reject_marks_onboarding_completed(qtbot, login_as) -> None:
    """Équivalent de la fermeture via la croix de la fenêtre (QDialog
    appelle ``reject()`` dans ce cas)."""
    stack, _ = login_as("Administrateur")
    dialog = _build_dialog(stack)
    qtbot.addWidget(dialog)

    dialog.reject()

    assert stack.onboarding.is_completed() is True


def test_navigating_from_a_step_closes_dialog_and_marks_completed(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    navigated: list[tuple] = []

    dialog = _build_dialog(stack, on_navigate=lambda module, preset=None: navigated.append((module, preset)) or True)
    qtbot.addWidget(dialog)

    step_buttons = [b for b in dialog.findChildren(QPushButton) if b.text() != "Fermer"]
    assert step_buttons  # au moins une étape pour l'Administrateur
    step_buttons[0].click()

    assert len(navigated) == 1
    assert stack.onboarding.is_completed() is True
    assert dialog.result() == dialog.DialogCode.Accepted
