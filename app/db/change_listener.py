"""Réception des notifications de changement (Chantier D, synchronisation
automatique) — l'autre moitié de ``app/db/change_notifications.py``.

Une connexion PostgreSQL ``LISTEN`` dédiée par poste, interrogée de façon
non bloquante (``timeout=0`` — confirmé par un test manuel : un sondage
vide ou plein revient en quelques dizaines de microsecondes, jamais une
requête sur les tables métier elles-mêmes) depuis un ``QTimer`` (voir
``app/views/main_window.py``) — jamais depuis une boucle/un thread dédié,
pour rester simple (aucune donnée à faire transiter entre threads).

Résolution du mot de passe (correctif, audit de revue) : passe
exclusivement par ``PostgreSQLConnectionConfig.resolve_password()`` — la
même méthode officielle que ``Settings.sqlalchemy_database_uri`` — qui
choisit elle-même entre le coffre d'identifiants (``credential_key``
renseigné, poste administré via l'assistant/l'écran d'administration) et
la variable d'environnement (déploiement scripté/tests), sans jamais
dupliquer cette logique ici ni contourner le coffre. Un précédent essai de
ce module lisait directement ``os.environ``, ce qui ne fonctionnait
jamais pour une connexion configurée via le coffre — corrigé.

Construction de la connexion (correctif, audit de revue) : jamais de
chaîne DSN construite par interpolation (``f"postgresql://{user}:{pwd}@..."``),
qui exposerait tout caractère réservé (``@``, ``%``, ``:``, ``/``, ...) du
nom d'utilisateur ou du mot de passe à une erreur d'interprétation de
l'URL — exactement la même classe de défaut déjà rencontrée et corrigée
pour Alembic ailleurs dans ce projet (voir
``test_alembic_config_accepts_percent_encoded_password_characters``).
``psycopg.connect()`` reçoit ici chaque paramètre séparément (``host``,
``port``, ``dbname``, ``user``, ``password``), jamais assemblés en chaîne
par ce code : aucun caractère n'a donc besoin d'être échappé, quel qu'il
soit. Le mot de passe n'est jamais journalisé ni inclus dans un message
d'erreur (les échecs de connexion ``psycopg``/PostgreSQL n'incluent jamais
le mot de passe fourni dans leur texte).

Reconnexion automatique : toute erreur pendant ``poll()`` ferme la
connexion et retourne un ensemble vide — le prochain appel retente une
connexion neuve. Jamais bloquant pour l'interface : aucune exception n'est
jamais levée hors de cette classe.
"""
from __future__ import annotations

from typing import Optional

import psycopg

from app.config.settings import Settings
from app.db.change_notifications import CHANGES_CHANNEL
from app.utils.logging_config import get_logger

logger = get_logger("db.change_listener")


class PostgreSQLChangeListener:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: Optional[psycopg.Connection] = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.closed

    def connect(self) -> bool:
        """Tente d'ouvrir (ou ré-ouvrir) la connexion ``LISTEN`` dédiée.
        Ne lève jamais : retourne ``False`` en cas d'échec, le prochain
        appel de :meth:`poll` retentera."""
        if self.is_connected:
            return True
        try:
            pg = self._settings.postgresql
            connection = psycopg.connect(
                host=pg.host, port=pg.port, dbname=pg.database, user=pg.username,
                password=pg.resolve_password(), autocommit=True, connect_timeout=5,
            )
            connection.execute(f"LISTEN {CHANGES_CHANNEL}")
            self._connection = connection
            return True
        except Exception:
            # Jamais le mot de passe dans ce message : ``exc_info=True``
            # journalise l'exception technique (ex. "password authentication
            # failed for user ...", "connection refused") — PostgreSQL et
            # psycopg n'incluent jamais le mot de passe fourni dans ce texte.
            logger.warning("Connexion LISTEN de synchronisation indisponible.", exc_info=True)
            self._connection = None
            return False

    def poll(self) -> set[str]:
        """Sondage non bloquant : retourne l'ensemble des types d'entités
        signalés depuis le dernier appel (vide si rien n'est en attente,
        ou si la connexion est indisponible — reconnexion tentée
        automatiquement, transparente pour l'appelant)."""
        if not self.is_connected and not self.connect():
            return set()

        entity_types: set[str] = set()
        try:
            for notification in self._connection.notifies(timeout=0):
                entity_types.update(notification.payload.split(","))
        except Exception:
            logger.warning(
                "Connexion LISTEN de synchronisation perdue — reconnexion au prochain sondage.",
                exc_info=True,
            )
            self.close()
        return entity_types

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:  # pragma: no cover - fermeture best-effort
                pass
            self._connection = None
