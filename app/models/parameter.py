from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Parametre(Base):
    """Paramètres applicatifs clé-valeur (devise, sauvegarde, informations entreprise...)."""

    __tablename__ = "parametres"

    cle: Mapped[str] = mapped_column(String(100), primary_key=True)
    valeur: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Parametre(cle={self.cle!r}, valeur={self.valeur!r})"
