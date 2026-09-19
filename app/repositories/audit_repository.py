"""Accès aux données pour la consultation du journal d'audit (lecture
seule — seuls les services métier eux-mêmes écrivent dans ``audit_logs``,
chacun via sa propre méthode ``_audit``/``_log_audit`` privée, inchangée
par ce module).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, contains_eager

from app.models.audit import AuditLog
from app.models.user import User
from app.repositories.base import SQLAlchemyRepository


class AuditRepository(SQLAlchemyRepository[AuditLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AuditLog)

    def search(
        self,
        term: str = "",
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        entite: Optional[str] = None,
    ) -> list[AuditLog]:
        """``AuditLog.user_id`` est nullable (ex. tentative de connexion avec
        un identifiant inconnu, voir ``AuthService.login``) : jointure
        externe (``outerjoin``), jamais une jointure interne comme celle de
        ``MouvementRepository.search`` (où ``user_id`` n'est jamais nul) —
        une jointure interne exclurait silencieusement ces entrées.

        ``date_heure`` porte une heure : ``date_to`` est une borne inclusive
        sur la journée entière, même convention que
        ``MouvementRepository.search``."""
        query = (
            self.session.query(AuditLog)
            .outerjoin(User, AuditLog.user_id == User.id)
            .options(contains_eager(AuditLog.user))
        )
        if term:
            like_term = f"%{term}%"
            query = query.filter(
                or_(
                    AuditLog.action.ilike(like_term),
                    AuditLog.details.ilike(like_term),
                    User.username.ilike(like_term),
                )
            )
        if date_from is not None:
            query = query.filter(AuditLog.date_heure >= datetime.combine(date_from, time.min))
        if date_to is not None:
            query = query.filter(AuditLog.date_heure < datetime.combine(date_to + timedelta(days=1), time.min))
        if entite is not None:
            query = query.filter(AuditLog.entite == entite)
        return query.order_by(AuditLog.date_heure.desc(), AuditLog.id.desc()).all()

    def list_entites(self) -> list[str]:
        """Valeurs distinctes de ``entite`` réellement présentes en base —
        utilisé pour peupler dynamiquement le filtre « Entité » de
        ``AuditPage``, plutôt qu'une liste figée dans le code qui devrait
        être tenue à jour à chaque nouveau module écrivant dans l'audit."""
        rows = self.session.query(AuditLog.entite).distinct().order_by(AuditLog.entite).all()
        return [row[0] for row in rows]
