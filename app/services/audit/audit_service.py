"""Service de consultation du journal d'audit (lecture seule).

Strictement séparé de l'écriture des audits : chaque service métier
continue d'écrire dans ``audit_logs`` via sa propre méthode privée
``_audit``/``_log_audit`` (inchangées par ce module) — ``AuditService``
n'expose que des méthodes de consultation, jamais de création, modification
ou suppression, conformément à la décision de conservation illimitée des
audits (aucune purge, aucun archivage).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.repositories.audit_repository import AuditRepository
from app.services.audit.audit_summary import AuditSummary
from app.services.auth.permission_service import PermissionService


class AuditService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def list_audits(
        self,
        term: str = "",
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        entite: Optional[str] = None,
    ) -> list[AuditSummary]:
        self._permissions.require_permission("AUDIT_VIEW")
        with session_scope(self._settings) as session:
            repo = AuditRepository(session)
            audits = repo.search(term=term, date_from=date_from, date_to=date_to, entite=entite)
            return [AuditSummary.from_model(a) for a in audits]

    def list_entites(self) -> list[str]:
        self._permissions.require_permission("AUDIT_VIEW")
        with session_scope(self._settings) as session:
            return AuditRepository(session).list_entites()
