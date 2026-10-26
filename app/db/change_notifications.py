"""Notifications de changement multi-poste (PostgreSQL ``LISTEN``/``NOTIFY``)
— Chantier D, synchronisation automatique entre postes.

Contexte : avant ce lot, un écran ouvert ne se rafraîchissait qu'à son
ouverture (changement de module dans la navigation, voir
``MainWindow._on_navigation_changed``, déjà existant) ou après une action
locale de l'utilisateur — une modification faite depuis un AUTRE poste
connecté à la même base PostgreSQL n'apparaissait jamais tant que
l'utilisateur ne changeait pas d'écran lui-même.

Mécanisme retenu (hybride — voir le rapport de ce lot pour la comparaison
des options envisagées : interrogation périodique seule, écartée car trop
coûteuse à l'échelle visée ; ``LISTEN``/``NOTIFY`` seul, écarté car une
notification manquée — coupure réseau — ne serait jamais rattrapée,
``NOTIFY`` n'étant jamais un stockage durable) :

  1. Après chaque COMMIT réussi d'une session ayant créé/modifié/supprimé
     au moins une entité « suivie » (voir :data:`_TRACKED_TABLES`), un
     signal PostgreSQL est émis sur le canal :data:`CHANGES_CHANNEL`, avec
     pour payload les types d'entités concernés (ex.
     ``"articles,mouvements_stock"`` pour une entrée de stock validée).
  2. Chaque poste maintient une connexion ``LISTEN`` dédiée (voir
     ``app/views/main_window.py``), interrogée à faible fréquence par un
     ``QTimer`` — jamais une requête sur les tables métier elles-mêmes.
  3. Une réconciliation périodique, plus lente, rafraîchit l'écran actif
     indépendamment des notifications reçues — filet de sécurité en cas de
     notification manquée ou après une reconnexion réseau.

Jamais activé sous SQLite (``settings.db_backend != "postgresql"``) : un
seul poste existe alors (architecture déjà établie, voir les lots
précédents) — le rafraîchissement sur navigation déjà existant reste
suffisant, sans connexion ``LISTEN`` ni ``NOTIFY`` superflus.

Détection des changements — DEUX mécanismes combinés, nécessaires l'un et
l'autre (confirmé par un test qui échouait avec un seul des deux, voir le
rapport de ce lot) :

  * ``after_flush`` (``session.new``/``dirty``/``deleted``, encore valides
    à cet instant) pour les créations/modifications ORM ordinaires
    (``session.add(Category(...))``, utilisé par la quasi-totalité des
    services de référence).
  * ``do_orm_execute`` pour les instructions ``UPDATE``/``DELETE`` Core
    exécutées directement via ``session.execute(update(Modele)...)`` —
    déjà le mécanisme établi de ce projet pour les mises à jour
    atomiques sous accès concurrent (``StockService.apply_movement`` pour
    ``Article.stock_actuel``, ``apply_atomic_status_transition`` pour le
    statut des documents) : ces écritures ne déclenchent JAMAIS le suivi
    ORM habituel (``session.dirty`` reste vide), un stock mis à jour lors
    d'une validation de document serait donc invisible pour
    ``after_flush`` seul — exactement le cas qui compte le plus pour
    l'exigence « les stocks doivent être actualisés après validation ».

Les deux alimentent le même accumulateur (``session.info``), vidé par
``after_commit`` (qui émet alors le ``NOTIFY``) ou par ``after_rollback``
(sans jamais notifier) — une transaction annulée ne doit jamais apparaître
comme une opération validée sur un autre poste.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.utils.logging_config import get_logger

logger = get_logger("db.change_notifications")

CHANGES_CHANNEL = "stockmanager_changes"

_PENDING_KEY = "_pending_change_notifications"

# Nom de table -> type d'entité (identiques par choix, pour rester lisible
# dans les logs et côté Qt) — une entrée ici seulement pour les tables dont
# un écran doit se rafraîchir automatiquement (voir le mandat de ce lot,
# §6) ; ``paiements``/``audit_logs``/etc. en sont absents car déjà couverts
# par leur document parent (Vente/Location) ou non concernés.
_TRACKED_TABLES = frozenset(
    {
        "articles",
        "categories",
        "fournisseurs",
        "motifs_sortie",
        "unites_article",
        "clients",
        "ventes",
        "entrees",
        "sorties",
        "inventaires",
        "locations",
        "mouvements_stock",
    }
)


def _pending(session: Session) -> set[str]:
    return session.info.setdefault(_PENDING_KEY, set())


def _collect_from_flush(session: Session, flush_context) -> None:  # noqa: ANN001
    pending = _pending(session)
    for obj in (*session.new, *session.dirty, *session.deleted):
        table_name = obj.__table__.name
        if table_name in _TRACKED_TABLES:
            pending.add(table_name)


def _collect_from_core_dml(orm_execute_state) -> None:  # noqa: ANN001
    if not (orm_execute_state.is_update or orm_execute_state.is_delete or orm_execute_state.is_insert):
        return
    table_name = orm_execute_state.statement.table.name
    if table_name in _TRACKED_TABLES:
        _pending(orm_execute_state.session).add(table_name)


def _notify_after_commit(session: Session, settings: Settings) -> None:
    pending = session.info.pop(_PENDING_KEY, None)
    if not pending:
        return
    payload = ",".join(sorted(pending))
    try:
        from app.db.session import get_engine

        with get_engine(settings).connect() as connection:
            connection.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": CHANGES_CHANNEL, "payload": payload},
            )
            connection.commit()
    except Exception:
        # Jamais bloquant : l'opération métier est déjà validée (COMMIT déjà
        # effectué) — un échec d'émission dégrade seulement la réactivité
        # de la synchronisation, rattrapée par la réconciliation périodique
        # côté Qt (voir la docstring de module), jamais la correction des
        # données elles-mêmes.
        logger.warning(
            "Échec de l'émission NOTIFY (%s) — l'opération métier reste validée.",
            payload, exc_info=True,
        )


def _clear_pending(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)


def register_change_notifications(session_factory: sessionmaker, settings: Settings) -> None:
    """Active les notifications de changement pour les sessions produites
    par ``session_factory`` — n'a aucun effet sous SQLite (voir la
    docstring de module)."""
    if settings.db_backend != "postgresql":
        return

    from sqlalchemy import event

    event.listen(session_factory, "after_flush", _collect_from_flush)
    event.listen(session_factory, "do_orm_execute", _collect_from_core_dml)
    event.listen(session_factory, "after_commit", lambda session: _notify_after_commit(session, settings))
    event.listen(session_factory, "after_rollback", _clear_pending)
