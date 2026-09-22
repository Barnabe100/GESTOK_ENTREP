"""``ActivationMode.from_stored_value`` : jamais autre chose que LOCAL/SERVER
en sortie, quelle que soit l'entrée — la seule porte d'entrée de la valeur
stockée en base (``parametres``) vers le code applicatif."""
from app.services.licensing.activation_mode import ActivationMode, DEFAULT_ACTIVATION_MODE


def test_default_activation_mode_is_local() -> None:
    assert DEFAULT_ACTIVATION_MODE == ActivationMode.LOCAL


def test_from_stored_value_none_defaults_to_local() -> None:
    assert ActivationMode.from_stored_value(None) == ActivationMode.LOCAL


def test_from_stored_value_empty_string_defaults_to_local() -> None:
    assert ActivationMode.from_stored_value("") == ActivationMode.LOCAL


def test_from_stored_value_unknown_string_defaults_to_local() -> None:
    assert ActivationMode.from_stored_value("QUANTUM") == ActivationMode.LOCAL


def test_from_stored_value_local_roundtrips() -> None:
    assert ActivationMode.from_stored_value("LOCAL") == ActivationMode.LOCAL


def test_from_stored_value_server_roundtrips() -> None:
    assert ActivationMode.from_stored_value("SERVER") == ActivationMode.SERVER


def test_from_stored_value_is_case_sensitive_and_defaults_to_local() -> None:
    """Aucune tolérance de casse implicite : une valeur stockée corrompue ou
    modifiée manuellement ne doit jamais être devinée, seulement retomber
    sur LOCAL par sécurité."""
    assert ActivationMode.from_stored_value("local") == ActivationMode.LOCAL
    assert ActivationMode.from_stored_value("server") == ActivationMode.LOCAL
