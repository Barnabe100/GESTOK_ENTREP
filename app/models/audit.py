from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ResultatAudit
from app.models.mixins import utcnow


class AuditLog(Base):
    """Journal des opérations sensibles. Rétention illimitée en V1 (aucune purge automatique)."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date_heure: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entite: Mapped[str] = mapped_column(String(100), nullable=False)
    entite_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resultat: Mapped[ResultatAudit] = mapped_column(
        SAEnum(ResultatAudit, native_enum=False, length=20, name="resultat_audit"),
        default=ResultatAudit.SUCCES,
        nullable=False,
    )

    user: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"AuditLog(action={self.action!r}, resultat={self.resultat!r})"
