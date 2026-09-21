from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

# Association Utilisateur <-> Rôle (many-to-many, un utilisateur peut avoir
# plusieurs rôles — voir migration 0011). Définie ici, à côté de
# ``role_permissions``, plutôt que dans ``app/models/user.py`` : les deux
# tables d'association RBAC restent regroupées au même endroit. Toujours
# ``users.role_id`` (colonne historique conservée telle quelle, voir
# ``User.role_id``) qui satisfait la contrainte NOT NULL historique — cette
# table est la seule source de vérité pour l'appartenance réelle à un rôle
# et pour le calcul des permissions effectives (``AuthService.login``,
# ``UserService``), jamais ``users.role_id``.
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    users: Mapped[list["User"]] = relationship("User", secondary=user_roles, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission", secondary=role_permissions, back_populates="roles"
    )

    def __repr__(self) -> str:  # pragma: no cover - confort de debug
        return f"Role(id={self.id!r}, nom={self.nom!r})"


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(50), nullable=False)

    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary=role_permissions, back_populates="permissions"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Permission(code={self.code!r})"
