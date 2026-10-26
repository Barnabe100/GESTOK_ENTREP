"""Génération atomique des numéros de document (Vente/Entrée/Sortie/
Inventaire/Location) — voir ``app/models/counters.py`` pour le contexte
complet de l'audit multi-poste ayant motivé ce mécanisme.

Remplace l'ancien ``numero = f"PREFIX-{repo.count_all() + 1:06d}"`` par une
unique instruction SQL ``UPDATE ... SET valeur = valeur + 1 ...
RETURNING valeur``, au même principe déjà validé dans ce projet par
``StockService.apply_movement`` (``Article.stock_actuel``) et
``app.utils.atomic_transition.apply_atomic_status_transition`` : jamais de
lecture-puis-écriture Python, toujours une mise à jour SQL conditionnelle
qui laisse le moteur lui-même sérialiser les écritures concurrentes.
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.counters import CompteurNumerotation


class CounterRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def next_value(self, type_document: str) -> int:
        """Incrémente et retourne atomiquement le compteur de
        ``type_document`` — jamais la même valeur à deux appels, même sous
        accès concurrent réel (verrou de ligne PostgreSQL, verrou base
        SQLite — voir la docstring de module).

        Lève ``LookupError`` si ``type_document`` n'a pas de ligne dans
        ``compteurs_numerotation`` : ne doit jamais se produire en usage
        normal (la migration 0017 crée une ligne par type de document
        existant) — une levée explicite est préférable à un ``INSERT``
        silencieux qui masquerait un type de document oublié par la
        migration ou une faute de frappe dans l'appelant."""
        result = self.session.execute(
            update(CompteurNumerotation)
            .where(CompteurNumerotation.type_document == type_document)
            .values(valeur=CompteurNumerotation.valeur + 1)
            .returning(CompteurNumerotation.valeur)
        )
        row = result.first()
        if row is None:
            raise LookupError(
                f"Aucun compteur de numérotation pour le type « {type_document} »."
            )
        return row[0]
