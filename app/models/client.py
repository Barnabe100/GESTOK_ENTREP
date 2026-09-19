from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import StatutActifInactif
from app.models.mixins import TimestampMixin


class Client(TimestampMixin, Base):
    """Client de l'entreprise cliente. Jamais de suppression physique (voir
    ClientService) : un client désactivé reste consultable — en particulier
    dans l'historique des ventes qui lui sont associées — mais n'est plus
    proposé pour une nouvelle vente."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(150), nullable=False)
    telephone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    adresse: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    observations: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    statut: Mapped[StatutActifInactif] = mapped_column(
        SAEnum(StatutActifInactif, native_enum=False, length=20, name="statut_actif_inactif"),
        default=StatutActifInactif.ACTIF,
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Client(id={self.id!r}, nom={self.nom!r})"
