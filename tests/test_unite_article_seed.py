"""Synchronisation additive des unités d'articles de référence (§7.4) :
une base déjà existante (migrée vers le schéma de ce lot mais jamais encore
synchronisée) doit recevoir les unités canoniques sans réinitialisation,
exactement comme ``sync_reference_data`` pour les permissions."""
from __future__ import annotations

from app.config.settings import Settings
from app.db.session import session_scope
from app.db.unite_article_seed import CANONICAL_UNITES_ARTICLE, sync_unites_article_reference_data
from app.models.catalog import UniteArticle


def test_sync_adds_all_canonical_values_to_an_empty_table(test_settings: Settings) -> None:
    from app.db.init_db import init_database

    init_database(test_settings)
    with session_scope(test_settings) as session:
        assert session.query(UniteArticle).count() == 0

        created = sync_unites_article_reference_data(session)

        assert set(created) == set(CANONICAL_UNITES_ARTICLE)
        assert {u.libelle for u in session.query(UniteArticle).all()} == set(CANONICAL_UNITES_ARTICLE)


def test_sync_is_idempotent(test_settings: Settings) -> None:
    from app.db.init_db import init_database

    init_database(test_settings)
    with session_scope(test_settings) as session:
        sync_unites_article_reference_data(session)

    with session_scope(test_settings) as session:
        second_run_created = sync_unites_article_reference_data(session)

        assert second_run_created == []
        assert session.query(UniteArticle).count() == len(CANONICAL_UNITES_ARTICLE)


def test_sync_never_duplicates_a_preexisting_case_insensitive_match(test_settings: Settings) -> None:
    """Une installation où un administrateur aurait déjà créé « unité »
    (minuscule) avant ce lot ne doit jamais se retrouver avec deux lignes
    équivalentes une fois la synchronisation exécutée."""
    from app.db.init_db import init_database

    init_database(test_settings)
    with session_scope(test_settings) as session:
        session.add(UniteArticle(libelle="unité"))

        created = sync_unites_article_reference_data(session)

        assert "Unité" not in created
        assert [u.libelle for u in session.query(UniteArticle).filter(UniteArticle.libelle.ilike("unité")).all()] == [
            "unité"
        ]


def test_sync_never_removes_or_modifies_existing_rows(test_settings: Settings) -> None:
    from app.db.init_db import init_database

    init_database(test_settings)
    with session_scope(test_settings) as session:
        session.add(UniteArticle(libelle="Bidon"))
        sync_unites_article_reference_data(session)

    with session_scope(test_settings) as session:
        assert "Bidon" in {u.libelle for u in session.query(UniteArticle).all()}
