"""Accès aux données pour les paramètres applicatifs (``parametres``,
table clé-valeur).

Première utilisation de ce modèle (jusqu'ici défini mais non exploité) :
la configuration des sauvegardes y est stockée plutôt que dans une nouvelle
table dédiée, conformément à l'instruction explicite de cette phase de
réutiliser ce mécanisme existant.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.parameter import Parametre
from app.repositories.base import SQLAlchemyRepository


class ParameterRepository(SQLAlchemyRepository[Parametre]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Parametre)

    def get_value(self, cle: str) -> Optional[str]:
        parametre = self.session.get(Parametre, cle)
        return parametre.valeur if parametre is not None else None

    def set_value(self, cle: str, valeur: Optional[str]) -> None:
        parametre = self.session.get(Parametre, cle)
        if parametre is None:
            parametre = Parametre(cle=cle, valeur=valeur)
            self.session.add(parametre)
        else:
            parametre.valeur = valeur
        self.session.flush()
