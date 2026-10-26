"""Compteurs de numérotation atomique des documents métier.

Contexte (audit multi-poste) : l'ancien mécanisme (``numero =
f"PREFIX-{repo.count_all() + 1:06d}"``, lu puis écrit en deux étapes
Python distinctes dans ``SaleService``/``EntryService``/``ExitService``/
``InventoryService``/``LocationService``) produit le même numéro pour deux
créations quasi simultanées sur des postes différents — la contrainte
``UNIQUE`` sur ``numero`` empêche toute corruption, mais l'opération
échoue alors pour l'un des deux utilisateurs (mesuré : jusqu'à 87 % de
collisions à 50 postes simulés lors d'une création strictement
simultanée).

Cette table remplace le COUNT(*) par un compteur persistant, incrémenté de
façon atomique par :meth:`app.repositories.counter_repository.CounterRepository.next_value`
— une unique instruction SQL ``UPDATE ... RETURNING``, jamais une
lecture-puis-écriture Python, au même principe déjà validé par
``StockService.apply_movement`` (voir ``app/services/stock/stock_service.py``,
règle 3 de sa docstring de module) : le moteur lui-même sérialise les
écritures concurrentes (verrou de ligne PostgreSQL, verrou base SQLite),
sans qu'aucune collision ne soit plus possible.
"""
from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CompteurNumerotation(Base):
    """Une ligne par type de document — ``type_document`` est le préfixe
    exact utilisé dans le numéro (ex. ``"VNT"`` pour ``VNT-000042``).

    ``valeur`` est le dernier numéro déjà attribué pour ce type, jamais le
    prochain disponible : le prochain est toujours ``valeur + 1``, obtenu
    atomiquement (jamais en relisant puis réécrivant cette valeur depuis
    Python)."""

    __tablename__ = "compteurs_numerotation"

    type_document: Mapped[str] = mapped_column(String(10), primary_key=True)
    valeur: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover
        return f"CompteurNumerotation(type_document={self.type_document!r}, valeur={self.valeur!r})"
