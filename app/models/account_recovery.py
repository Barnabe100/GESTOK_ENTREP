"""Code de récupération du compte administrateur (lot récupération admin).

Un seul code actif par utilisateur (``user_id`` unique) : générer un
nouveau code invalide immédiatement l'ancien (``AccountRecoveryService``
remplace la ligne existante plutôt que d'en empiler une seconde — pas un
journal d'historique, un état courant). Jamais le code en clair ici : seule
son empreinte (Argon2, même primitive que ``User.password_hash``) est
stockée, via ``app.security.password_hashing``.

``failed_attempts``/``locked_until`` portent la limitation anti-brute-force
(§ lot récupération admin) : lus et modifiés dans la même transaction que
leur vérification (``AccountRecoveryService``, ``session_scope``) — jamais
une lecture puis une écriture séparées, pour rester sûr vis-à-vis d'accès
concurrents (SQLite sérialise les transactions d'écriture : la seconde
attend la fin de la première, puis relit l'état déjà à jour)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import utcnow


class AdminRecoveryCode(Base):
    __tablename__ = "admin_recovery_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # NULL tant que le code n'a jamais été utilisé avec succès — un code
    # consommé n'est plus jamais vérifiable (voir
    # AccountRecoveryService.reset_password_with_code), même si la ligne
    # reste présente jusqu'à la prochaine régénération.
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:  # pragma: no cover
        return f"AdminRecoveryCode(user_id={self.user_id!r})"
