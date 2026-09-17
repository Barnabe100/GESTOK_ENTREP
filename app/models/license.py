from datetime import date
from typing import Optional

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import EditionLicence, StatutLicence
from app.models.mixins import TimestampMixin


class Licence(TimestampMixin, Base):
    """Licence activée localement. Les droits/fonctionnalités accordés sont portés par
    ``payload_json`` (signé, voir architecture de licence — implémentée en phase ultérieure)."""

    __tablename__ = "licences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client: Mapped[str] = mapped_column(String(150), nullable=False)
    produit: Mapped[str] = mapped_column(String(100), nullable=False)
    edition: Mapped[EditionLicence] = mapped_column(
        SAEnum(EditionLicence, native_enum=False, length=20, name="edition_licence"), nullable=False
    )
    date_emission: Mapped[date] = mapped_column(Date, nullable=False)
    date_expiration: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False)
    max_postes: Mapped[int] = mapped_column(Integer, nullable=False)
    statut: Mapped[StatutLicence] = mapped_column(
        SAEnum(StatutLicence, native_enum=False, length=20, name="statut_licence"), nullable=False
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Licence(client={self.client!r}, edition={self.edition!r}, statut={self.statut!r})"
