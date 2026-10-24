"""Synchronisation ADDITIVE des unités d'articles de référence (§7,
évolution F), pour une base déjà initialisée.

Même principe que ``app.db.reference_data_sync`` (permissions/rôles) : une
installation déjà existante avant ce lot doit elle aussi recevoir les
unités canoniques ci-dessous sans réinitialisation — ce module n'y est pas
fusionné pour préserver le périmètre déjà documenté de
``reference_data_sync`` (strictement permissions/rôles).

Règles strictes (jamais dérogées) :
- Aucune unité n'est supprimée ni modifiée.
- Une unité déjà créée manuellement (avant ce lot ou par le bouton
  « Nouveau ») qui coïncide avec une valeur canonique (espaces/casse
  ignorés, voir ``normalize_label``) n'est jamais dupliquée.
- Idempotent : un deuxième appel sans changement de code ne produit aucune
  modification.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.catalog import UniteArticle
from app.repositories.exit_reason_repository import normalize_label
from app.utils.logging_config import get_logger

logger = get_logger("db.unite_article_seed")

# Liste fermée initiale (§7.1) — reprend exactement les valeurs demandées,
# complétée de « Caisse » pour les boissons (§7.1) ; aucune valeur
# supplémentaire n'a été ajoutée sans justification métier explicite.
CANONICAL_UNITES_ARTICLE: tuple[str, ...] = (
    "Pièce",
    "Unité",
    "Caisse",
    "Carton",
    "Paquet",
    "Sac",
    "Kilogramme",
    "Gramme",
    "Litre",
    "Millilitre",
    "Mètre",
    "Mètre carré",
)


def sync_unites_article_reference_data(session: Session) -> list[str]:
    """Ajoute les unités canoniques manquantes. Retourne les libellés
    effectivement créés (liste vide si déjà à jour)."""
    existing_normalized = {normalize_label(u.libelle) for u in session.query(UniteArticle).all()}

    created: list[str] = []
    for libelle in CANONICAL_UNITES_ARTICLE:
        if normalize_label(libelle) not in existing_normalized:
            session.add(UniteArticle(libelle=libelle))
            existing_normalized.add(normalize_label(libelle))
            created.append(libelle)

    if created:
        session.flush()
        logger.info("Unités d'article de référence ajoutées : %s", ", ".join(created))
    else:
        logger.info("Unités d'article de référence : déjà à jour, aucun changement.")

    return created
