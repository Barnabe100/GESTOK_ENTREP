"""Transition d'état atomique d'un document métier (Entree/Sortie/Vente/
Inventaire/Location) sous accès concurrent.

Contexte (audit de concurrence, Lot C) : chaque service de document
(``EntryService``, ``ExitService``, ``SaleService``, ``InventoryService``,
``LocationService``) protégeait historiquement chaque transition de statut
(``validate_*``/``cancel_*``/``depart_*``/``return_*``) par une simple
lecture ORM suivie d'un test Python, par exemple ::

    if sortie.statut != StatutOperation.BROUILLON:
        raise ConflictError(...)

Sous deux sessions distinctes réellement concurrentes, rien n'empêche les
deux appels de lire le même statut avant que l'un des deux n'écrive : les
deux passent le test, et la transition (donc les mouvements de stock
qu'elle déclenche via ``StockService.apply_movement``) est appliquée deux
fois. Confirmé empiriquement, symétriquement sur SQLite et PostgreSQL
16.15 (voir le rapport de ce lot) — ``StockService.apply_movement``
lui-même n'est pas en cause : il protège correctement ``Article.stock_actuel``
contre la perte de mise à jour, mais chaque service appelant pouvait
l'invoquer deux fois pour ce qui doit rester une seule et même opération.

Cette fonction reprend le principe déjà validé par
``StockService.apply_movement`` — une mise à jour SQL conditionnelle
(``UPDATE ... WHERE ... SET ...``), jamais une lecture-puis-écriture
Python — appliqué ici au statut d'un document plutôt qu'à une quantité
numérique : si la clause ``WHERE`` ne correspond plus (parce qu'un autre
appel a déjà effectué la transition), aucune ligne n'est mise à jour et
``ConflictError`` est levée, avant qu'aucun mouvement de stock dépendant
n'ait été appliqué par l'appelant.
"""
from __future__ import annotations

from typing import Any, Type

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.utils.exceptions import ConflictError


def apply_atomic_status_transition(
    session: Session,
    model: Type[Any],
    row_id: int,
    *,
    expected_status: Any,
    new_status: Any,
    error_message: str,
) -> None:
    """Fait passer ``model.statut`` de ``expected_status`` à ``new_status``
    pour la ligne ``row_id``, de façon atomique et conditionnelle.

    Lève :class:`ConflictError` (``error_message``) si la ligne n'est plus
    dans l'état ``expected_status`` au moment de l'écriture — qu'elle ait
    déjà subi cette même transition par un appel concurrent, ou toute
    autre modification de son statut entre la lecture initiale par
    l'appelant et cet appel.

    Ne rafraîchit pas l'objet ORM déjà détenu par l'appelant (à sa charge,
    via ``session.refresh(...)``, à l'identique de ce que fait
    ``StockService.apply_movement`` pour ``Article``) : cette fonction ne
    fait qu'exécuter l'instruction SQL elle-même.
    """
    result = session.execute(
        update(model)
        .where(model.id == row_id, model.statut == expected_status)
        .values(statut=new_status)
    )
    if result.rowcount == 0:
        raise ConflictError(error_message)
