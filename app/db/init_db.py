"""Initialisation du schéma de base de données via Alembic.

En développement comme en production, le schéma est toujours amené à jour
par les migrations Alembic (jamais par un ``create_all`` direct), afin que
les mises à jour ultérieures de l'application puissent faire évoluer le
schéma sans perte de données chez les clients déjà installés.
"""
from __future__ import annotations

from typing import Iterator, Optional

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import Settings, get_settings
from app.utils.logging_config import get_logger
from app.utils.runtime_paths import app_root

logger = get_logger("db.init")

PROJECT_ROOT = app_root()
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_PATH = PROJECT_ROOT / "migrations"


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    # Lot B : pour PostgreSQL, sqlalchemy_database_uri est un objet URL (Lot
    # A, masquage du mot de passe dans son propre repr/str) — Config exige
    # une chaîne. render_as_string(hide_password=False) restitue le mot de
    # passe réel (indispensable pour se connecter), jamais affiché ni
    # journalisé ici : seule la valeur transmise à Alembic en dépend.
    uri = settings.sqlalchemy_database_uri
    uri_str = uri if isinstance(uri, str) else uri.render_as_string(hide_password=False)
    # Correctif : alembic.config.Config stocke ses options dans un
    # configparser.ConfigParser, dont l'interpolation par défaut
    # (BasicInterpolation) traite tout « % » isolé comme le début d'une
    # référence — un mot de passe PostgreSQL contenant un caractère spécial
    # percent-encodé par render_as_string (ex. « %40 », « %21 ») y lève
    # ValueError: invalid interpolation syntax dès cet appel. Doubler
    # chaque « % » (« %% ») le restitue tel quel à la lecture (configparser
    # décode « %% » -> « % » dans son before_get) : jamais une altération du
    # mot de passe ni de l'URL utilisée par SQLAlchemy lui-même (ci-dessus,
    # `uri`/`uri_str`), qui ne voit jamais cette version échappée — seule la
    # valeur transmise à ``Config`` en dépend.
    config.set_main_option("sqlalchemy.url", uri_str.replace("%", "%%"))
    return config


def init_database(settings: Optional[Settings] = None) -> None:
    """Amène le schéma de la base au niveau de la dernière migration Alembic.

    Idempotent : sans effet si le schéma est déjà à jour. Crée le fichier de
    base de données et le répertoire parent s'ils n'existent pas encore.
    """
    settings = settings or get_settings()
    settings.ensure_directories()
    logger.info("Initialisation du schéma de base de données : %s", settings.db_path)
    config = _alembic_config(settings)
    command.upgrade(config, "head")
    logger.info("Schéma de base de données à jour.")


def _walk_ancestors(script: ScriptDirectory, revision_id: Optional[str], visited: set[str]) -> Iterator[str]:
    """Génère ``revision_id`` lui-même puis chacun de ses ancêtres, en
    remontant son (ou ses, pour une révision de fusion) ``down_revision`` —
    ``visited`` évite toute boucle infinie en cas d'incohérence du graphe.
    L'historique de ce projet est en pratique strictement linéaire (une
    seule tête, une seule base, vérifié par inspection directe), mais le
    cas d'une révision de fusion (``down_revision`` sous forme de tuple,
    plusieurs branches parentes) est géré par précaution plutôt que supposé
    absent pour toujours."""
    if revision_id is None or revision_id in visited:
        return
    visited.add(revision_id)
    yield revision_id
    revision = script.get_revision(revision_id)
    if revision is None or revision.down_revision is None:
        return
    parents = revision.down_revision
    if not isinstance(parents, tuple):
        parents = (parents,)
    for parent in parents:
        yield from _walk_ancestors(script, parent, visited)


def is_ancestor_revision(candidate_revision: Optional[str], settings: Optional[Settings] = None) -> bool:
    """Vrai si ``candidate_revision`` est la révision actuelle (``head``) ou
    une révision Alembic strictement antérieure sur son historique — c'est
    à dire si l'amener à ``head`` ne demande jamais qu'une suite de
    migrations ASCENDANTES (``command.upgrade``), jamais de retour en
    arrière. Utilisé pour assouplir la vérification de compatibilité de
    version avant restauration (mission corrective « Fiabilisation du
    module de sauvegarde », §3.10) : une sauvegarde plus ancienne mais
    compatible peut alors être restaurée puis mise à niveau automatiquement
    vers ``head``, plutôt que refusée pour la seule raison qu'elle ne
    correspond pas exactement à la version actuelle.

    Retourne ``False`` sans jamais lever si ``candidate_revision`` est
    ``None``, inconnue du script Alembic, ou n'est pas un ancêtre de
    ``head`` (cas d'une sauvegarde plus RÉCENTE que l'application actuelle
    — prise avec une version ultérieure de StockManager puis restaurée sur
    un poste resté en retard — ou sur une branche distincte) : dans ces
    deux cas, une mise à niveau automatique ne serait jamais sûre."""
    if not candidate_revision:
        return False
    settings = settings or get_settings()
    try:
        script = ScriptDirectory.from_config(_alembic_config(settings))
        heads = script.get_heads()
    except Exception:
        return False
    visited: set[str] = set()
    for head in heads:
        if candidate_revision in _walk_ancestors(script, head, visited):
            return True
    return False
