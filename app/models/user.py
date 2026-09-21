from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin
from app.models.rbac import user_roles


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Colonne historique conservée à l'identique (NOT NULL, jamais modifiée
    # par la migration 0011) : un simple pointeur de compatibilité vers l'un
    # des rôles de l'utilisateur (le premier fourni à la création), utile
    # pour tout code n'ayant pas besoin de la liste complète (constructions
    # ORM directes des tests de repositories, par exemple). Ce n'est PLUS la
    # source de vérité des permissions ni de l'appartenance à un rôle depuis
    # l'introduction du multi-rôle — voir ``roles`` ci-dessous, seule
    # collection utilisée par ``AuthService.login``/``UserService``.
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dernier_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Source de vérité de l'appartenance à un rôle (many-to-many, table
    # ``user_roles`` — voir app/models/rbac.py) : un utilisateur peut avoir
    # un ou plusieurs rôles, jamais aucun (contrainte applicative, vérifiée
    # par UserService, pas par le schéma).
    roles: Mapped[list["Role"]] = relationship("Role", secondary=user_roles, back_populates="users")

    def __repr__(self) -> str:  # pragma: no cover
        return f"User(id={self.id!r}, username={self.username!r})"
