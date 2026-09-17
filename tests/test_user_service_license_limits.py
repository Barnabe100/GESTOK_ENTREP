"""Limite ``max_users`` de la licence active, appliquée par
``UserService.set_active`` (§12) — seul point d'entrée actuel de
l'application qui augmente le nombre de comptes actifs (aucune création
d'utilisateur n'existe encore, voir app/services/users/user_service.py).

Règle retenue : seuls les comptes actifs (``User.actif is True``) comptent
dans la limite ; un compte désactivé ne consomme pas de place."""
import pytest

from app.services.licensing.license_payload import KNOWN_FEATURES
from app.utils.exceptions import ValidationError


def _activate_license_with_max_users(stack, license_envelope_factory, max_users: int) -> None:
    envelope = license_envelope_factory(max_users=max_users, features=sorted(KNOWN_FEATURES))
    stack.licenses.activate_license(envelope)


def test_set_active_refused_when_activating_would_exceed_max_users(login_as, make_user, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")  # 1 compte actif (l'administrateur connecté)
    make_user("Vendeur", "candidat_refuse", actif=False)
    _activate_license_with_max_users(stack, license_envelope_factory, max_users=1)

    target_id = next(u.id for u in stack.users.list_users() if u.username == "candidat_refuse")
    with pytest.raises(ValidationError):
        stack.users.set_active(target_id, True)

    # Le compte reste inactif : la tentative refusée n'a rien modifié.
    still_inactive = next(u for u in stack.users.list_users() if u.username == "candidat_refuse")
    assert still_inactive.actif is False


def test_set_active_succeeds_when_still_under_max_users(login_as, make_user, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")  # 1 compte actif
    make_user("Vendeur", "candidat_accepte", actif=False)
    _activate_license_with_max_users(stack, license_envelope_factory, max_users=2)

    target_id = next(u.id for u in stack.users.list_users() if u.username == "candidat_accepte")
    updated = stack.users.set_active(target_id, True)

    assert updated.actif is True


def test_disabled_accounts_do_not_count_towards_max_users(login_as, make_user, license_envelope_factory) -> None:
    """Plusieurs comptes désactivés ne consomment aucune place : seul le
    compte administrateur actif compte, la limite reste donc respectée."""
    stack, _ = login_as("Administrateur")
    make_user("Vendeur", "inactif_1", actif=False)
    make_user("Vendeur", "inactif_2", actif=False)
    make_user("Vendeur", "a_activer", actif=False)
    _activate_license_with_max_users(stack, license_envelope_factory, max_users=2)

    target_id = next(u.id for u in stack.users.list_users() if u.username == "a_activer")
    updated = stack.users.set_active(target_id, True)

    assert updated.actif is True


def test_set_active_deactivation_is_never_blocked_by_the_limit(login_as, make_user, license_envelope_factory) -> None:
    """Désactiver un compte réduit le nombre de comptes actifs : jamais
    concerné par la limite, même une licence déjà à sa limite maximale."""
    stack, _ = login_as("Administrateur")
    make_user("Vendeur", "deja_actif", actif=True)
    _activate_license_with_max_users(stack, license_envelope_factory, max_users=1)  # déjà dépassée (2 actifs)

    target_id = next(u.id for u in stack.users.list_users() if u.username == "deja_actif")
    updated = stack.users.set_active(target_id, False)

    assert updated.actif is False


def test_reactivating_an_already_active_user_is_a_no_op_not_blocked(login_as, license_envelope_factory) -> None:
    stack, current_user = login_as("Administrateur")
    _activate_license_with_max_users(stack, license_envelope_factory, max_users=1)

    updated = stack.users.set_active(current_user.id, True)

    assert updated.actif is True
