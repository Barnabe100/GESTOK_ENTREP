"""Couche repository : seule couche autorisée à parler SQLAlchemy directement.

Les services métier des phases suivantes dépendent de :class:`AbstractRepository`,
jamais de :class:`SQLAlchemyRepository` ni de la session SQLAlchemy elle-même.
Cette séparation est ce qui permettra de faire évoluer la persistance
(ex. vers PostgreSQL derrière une API) sans réécrire la logique métier.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class AbstractRepository(ABC, Generic[ModelT]):
    @abstractmethod
    def get_by_id(self, entity_id: int) -> Optional[ModelT]:
        """Retourne l'entité par identifiant, ou None si absente."""

    @abstractmethod
    def list_all(self) -> Sequence[ModelT]:
        """Retourne toutes les entités."""

    @abstractmethod
    def add(self, entity: ModelT) -> ModelT:
        """Ajoute une nouvelle entité et la retourne (avec son identifiant assigné)."""


class SQLAlchemyRepository(AbstractRepository[ModelT]):
    """Implémentation générique de repository basée sur une session SQLAlchemy.

    Utilisable telle quelle pour des besoins de lecture/écriture simples ;
    les repositories spécifiques à une entité (avec des requêtes métier
    dédiées) seront ajoutés au fil des phases suivantes.
    """

    def __init__(self, session: Session, model: Type[ModelT]) -> None:
        self.session = session
        self.model = model

    def get_by_id(self, entity_id: int) -> Optional[ModelT]:
        return self.session.get(self.model, entity_id)

    def list_all(self) -> Sequence[ModelT]:
        return self.session.query(self.model).all()

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        self.session.flush()
        return entity
