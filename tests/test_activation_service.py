"""Mode d'activation LOCAL/SERVER (§1-4 de la préparation LOCAL/SERVER).

``ActivationService`` orchestre le choix de mode autour de ``LicenseService``
(qui reste l'unique autorité de validation cryptographique et de stockage) et
d'un ``LicenseServerClient`` (aucune implémentation réseau réelle à ce stade
— voir ``UnconfiguredLicenseServerClient``, câblée par défaut dans
``app.services.registry``)."""
from __future__ import annotations

from app.services.licensing.activation_mode import ActivationMode
from app.services.licensing.activation_service import ActivationService
from app.services.licensing.license_payload import LicensePayload
from app.services.licensing.license_server_client import LicenseServerClient
from app.services.licensing.license_service import LicenseInfo, LicenseState
from app.utils.exceptions import LicenseServerUnavailableError, ValidationError


class _SpyLicenseServerClient(LicenseServerClient):
    """Double de test : n'effectue aucun appel réseau, enregistre chaque
    invocation pour permettre de vérifier l'ORDRE des opérations (§E/§F —
    la validation locale doit toujours précéder toute sollicitation du
    serveur, et ne jamais avoir lieu du tout si la validation locale
    échoue)."""

    def __init__(self) -> None:
        self.activate_calls: list[tuple[LicensePayload, str]] = []

    def activate(self, license_payload: LicensePayload, device_id: str) -> LicenseInfo:
        self.activate_calls.append((license_payload, device_id))
        raise LicenseServerUnavailableError("Le serveur TechNova n'est pas encore configuré.")

    def deactivate(self, device_id: str) -> None:
        raise LicenseServerUnavailableError("Le serveur TechNova n'est pas encore configuré.")

    def check(self, device_id: str) -> LicenseInfo:
        raise LicenseServerUnavailableError("Le serveur TechNova n'est pas encore configuré.")


def _spy_activation_service(stack) -> tuple[ActivationService, _SpyLicenseServerClient]:
    spy = _SpyLicenseServerClient()
    service = ActivationService(stack.licenses, spy, stack.permissions)
    return service, spy


# -- A : mode absent -> LOCAL ----------------------------------------------------------


def test_a_missing_mode_parameter_defaults_to_local(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.activation.get_mode() == ActivationMode.LOCAL


def test_a_invalid_stored_value_defaults_to_local(login_as) -> None:
    from app.db.session import session_scope
    from app.repositories.parameter_repository import ParameterRepository

    stack, _ = login_as("Administrateur")
    with session_scope(None) as session:
        ParameterRepository(session).set_value("activation.mode", "CECI_N_EST_PAS_UN_MODE")

    assert stack.activation.get_mode() == ActivationMode.LOCAL


# -- B : mode LOCAL, activation valide -> comportement actuel inchangé ------------------


def test_b_local_mode_valid_activation_matches_direct_license_service_call(
    login_as, license_envelope_factory
) -> None:
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(license_id="STK-LOCAL-B", client="Client Local B")

    info = stack.activation.activate(envelope)

    assert info.state == LicenseState.VALID
    assert info.license_id == "STK-LOCAL-B"
    assert info.client == "Client Local B"
    # Le comportement de get_info() après coup est celui de LicenseService,
    # inchangé : l'activation a bien été enregistrée en base.
    assert stack.licenses.get_info().license_id == "STK-LOCAL-B"


# -- C : mode LOCAL, licence invalide -> refus -------------------------------------------


def test_c_local_mode_invalid_license_is_refused(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.activation.activate("pas un JSON de licence valide")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass

    # Aucune activation invalide n'a remplacé la licence de test existante.
    assert stack.licenses.get_info().license_id == "TEST-FULL-ACCESS"


# -- D : mode SERVER sans serveur -> erreur explicite, jamais un succès -----------------


def test_d_server_mode_without_server_raises_explicit_error(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    stack.activation.set_mode(ActivationMode.SERVER)
    envelope = license_envelope_factory(license_id="STK-SERVER-D")

    try:
        stack.activation.activate(envelope)
        assert False, "devait lever LicenseServerUnavailableError"
    except LicenseServerUnavailableError as exc:
        assert "pas encore configuré" in str(exc)

    # Ce n'est jamais devenu la licence active : aucune fausse réussite.
    assert stack.licenses.get_info().license_id != "STK-SERVER-D"
    assert stack.licenses.get_info().license_id == "TEST-FULL-ACCESS"


# -- E : la validation locale a lieu AVANT toute tentative d'appel serveur --------------


def test_e_local_validation_happens_before_server_call(login_as, license_envelope_factory) -> None:
    stack, _ = login_as("Administrateur")
    service, spy = _spy_activation_service(stack)
    service.set_mode(ActivationMode.SERVER)
    envelope = license_envelope_factory(license_id="STK-SERVER-E")

    try:
        service.activate(envelope)
        assert False, "devait lever LicenseServerUnavailableError"
    except LicenseServerUnavailableError:
        pass

    # Le serveur (même factice) a bien été sollicité, avec le payload
    # DÉJÀ validé localement (LicensePayload, pas le texte brut).
    assert len(spy.activate_calls) == 1
    called_payload, called_device_id = spy.activate_calls[0]
    assert isinstance(called_payload, LicensePayload)
    assert called_payload.license_id == "STK-SERVER-E"
    assert called_device_id == stack.licenses.get_info().device_id


# -- F : signature invalide en SERVER -> refus local, AUCUN appel au serveur -----------


def test_f_invalid_signature_in_server_mode_never_calls_license_server_client(login_as) -> None:
    stack, _ = login_as("Administrateur")
    service, spy = _spy_activation_service(stack)
    service.set_mode(ActivationMode.SERVER)

    try:
        service.activate("pas un JSON de licence valide")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass

    assert spy.activate_calls == []


# -- G : persistance du mode entre deux "redémarrages" (nouvelle pile de services) ------


def test_g_local_mode_persists_across_restart(login_as, make_stack) -> None:
    stack, _ = login_as("Administrateur")
    # LOCAL est déjà le mode par défaut ; le confirmer explicitement en base.
    stack.activation.set_mode(ActivationMode.LOCAL)

    restarted_stack = make_stack()
    restarted_stack.auth.login(stack.auth.current_user.username, "MotDePasse!23")

    assert restarted_stack.activation.get_mode() == ActivationMode.LOCAL


def test_g_server_mode_persists_across_restart(login_as, make_stack) -> None:
    stack, current_user = login_as("Administrateur")
    stack.activation.set_mode(ActivationMode.SERVER)

    restarted_stack = make_stack()
    restarted_stack.auth.login(current_user.username, "MotDePasse!23")

    assert restarted_stack.activation.get_mode() == ActivationMode.SERVER


# -- H : bascule LOCAL -> SERVER -> LOCAL ------------------------------------------------


def test_h_switching_modes_back_and_forth(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.activation.get_mode() == ActivationMode.LOCAL

    stack.activation.set_mode(ActivationMode.SERVER)
    assert stack.activation.get_mode() == ActivationMode.SERVER

    stack.activation.set_mode(ActivationMode.LOCAL)
    assert stack.activation.get_mode() == ActivationMode.LOCAL


# -- I : FeatureGate fonctionne exactement comme avant (aucune régression) --------------


def test_i_feature_gate_unaffected_by_activation_mode(login_as, license_envelope_factory) -> None:
    """Le mode d'activation ne concerne que le PROCESSUS d'activation —
    FeatureGate ne consulte jamais ActivationService, uniquement
    LicenseService.evaluate() (inchangé)."""
    stack, _ = login_as("Administrateur")

    # Mode SERVER sélectionné : l'usage quotidien (permissions soumises à la
    # licence) doit rester identique, car FeatureGate ignore totalement le
    # mode d'activation.
    stack.activation.set_mode(ActivationMode.SERVER)
    assert stack.permissions.has_permission("REPORT_VIEW") is True  # licence de test à accès complet

    # Une activation LOCAL réussie continue d'alimenter FeatureGate via
    # LicenseService, comme avant l'introduction du mode d'activation.
    stack.activation.set_mode(ActivationMode.LOCAL)
    envelope = license_envelope_factory(license_id="STK-FEATUREGATE-I", features=["ARTICLES"])
    stack.activation.activate(envelope)

    assert stack.permissions.has_permission("ARTICLE_VIEW") is True
    assert stack.permissions.has_permission("REPORT_VIEW") is False  # plus dans les fonctionnalités de cette licence
