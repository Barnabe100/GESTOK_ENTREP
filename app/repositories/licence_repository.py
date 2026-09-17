"""Accès aux données pour les licences activées localement.

Aucune colonne « licence courante » dédiée : l'historique complet des
activations est conservé (jamais de suppression), et la licence courante est
simplement la plus récemment ajoutée — évite toute migration de schéma pour
cette phase (voir ``app/models/license.py``, déjà prêt pour cet usage).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.license import Licence
from app.repositories.base import SQLAlchemyRepository


class LicenceRepository(SQLAlchemyRepository[Licence]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Licence)

    def get_current(self) -> Optional[Licence]:
        """La licence courante est la dernière activée (id le plus élevé),
        conservant l'historique complet des activations précédentes."""
        return self.session.query(Licence).order_by(Licence.id.desc()).first()
