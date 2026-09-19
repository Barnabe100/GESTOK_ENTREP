"""Vue de présentation en lecture seule d'une entrée du journal d'audit,
pour ``AuditPage``/``AuditDetailDialog``."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models.audit import AuditLog
from app.models.enums import ResultatAudit


@dataclass(frozen=True)
class AuditSummary:
    id: int
    date_heure: datetime
    user_id: Optional[int]
    # None lorsque ``user_id`` est nul (ex. tentative de connexion avec un
    # identifiant inconnu) — jamais une valeur inventée.
    username: Optional[str]
    action: str
    entite: str
    entite_id: Optional[int]
    details: Optional[str]
    resultat: ResultatAudit

    @classmethod
    def from_model(cls, audit: AuditLog) -> "AuditSummary":
        return cls(
            id=audit.id,
            date_heure=audit.date_heure,
            user_id=audit.user_id,
            username=audit.user.username if audit.user is not None else None,
            action=audit.action,
            entite=audit.entite,
            entite_id=audit.entite_id,
            details=audit.details,
            resultat=audit.resultat,
        )
