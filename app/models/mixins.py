from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Ajoute date_creation / date_modification, gérées automatiquement."""

    date_creation: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    date_modification: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
