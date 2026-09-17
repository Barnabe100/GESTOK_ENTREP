import pytest

from app.utils.exceptions import (
    AppError,
    ConfigurationError,
    ConflictError,
    DatabaseError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

ALL_SUBCLASSES = [
    ValidationError,
    NotFoundError,
    ConflictError,
    PermissionDeniedError,
    DatabaseError,
    ConfigurationError,
]


@pytest.mark.parametrize("exception_class", ALL_SUBCLASSES)
def test_all_app_exceptions_inherit_from_apperror(exception_class: type[Exception]) -> None:
    assert issubclass(exception_class, AppError)


def test_apperror_is_a_standard_exception() -> None:
    assert issubclass(AppError, Exception)


def test_exception_message_is_preserved() -> None:
    error = ValidationError("stock négatif refusé")
    assert str(error) == "stock négatif refusé"
