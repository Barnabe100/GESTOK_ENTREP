from decimal import Decimal

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.catalog import Article, Category
from app.models.enums import StatutActifInactif
from app.repositories.article_repository import ArticleRepository


def _make_article(session, category, reference, **overrides):
    defaults = dict(
        reference=reference,
        designation="Article",
        category_id=category.id,
        unite="unité",
        prix_achat_defaut=Decimal("10"),
        prix_vente=Decimal("20"),
        cout_moyen_pondere=Decimal("10"),
        stock_actuel=Decimal("0"),
        stock_min=Decimal("0"),
    )
    defaults.update(overrides)
    article = Article(**defaults)
    session.add(article)
    return article


def test_find_by_reference_exact_match(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        category = Category(nom="Boissons")
        session.add(category)
        session.flush()
        _make_article(session, category, "ART-001")
        session.flush()

        repo = ArticleRepository(session)
        assert repo.find_by_reference("ART-001") is not None
        assert repo.find_by_reference("art-001") is None  # sensible à la casse
        assert repo.find_by_reference("INCONNU") is None


def test_find_by_reference_excludes_given_id(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        category = Category(nom="Boissons")
        session.add(category)
        session.flush()
        article = _make_article(session, category, "ART-002")
        session.flush()

        repo = ArticleRepository(session)
        assert repo.find_by_reference("ART-002", exclude_id=article.id) is None
        assert repo.find_by_reference("ART-002", exclude_id=article.id + 1) is not None


def test_find_by_barcode(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        category = Category(nom="Boissons")
        session.add(category)
        session.flush()
        _make_article(session, category, "ART-003", code_barres="1112223334445")
        session.flush()

        repo = ArticleRepository(session)
        assert repo.find_by_barcode("1112223334445") is not None
        assert repo.find_by_barcode("0000000000000") is None


def test_find_by_barcode_active_only_ignores_inactive_article(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        category = Category(nom="Boissons")
        session.add(category)
        session.flush()
        _make_article(
            session, category, "ART-003B", code_barres="9990001112223",
            statut=StatutActifInactif.INACTIF,
        )
        session.flush()

        repo = ArticleRepository(session)
        # Sans filtre : trouvé (utilisé par les vérifications d'historique).
        assert repo.find_by_barcode("9990001112223") is not None
        # Avec active_only=True (scan/recherche opérationnelle) : ignoré.
        assert repo.find_by_barcode("9990001112223", active_only=True) is None


def test_search_matches_reference_designation_or_category(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        boissons = Category(nom="Boissons")
        epicerie = Category(nom="Épicerie")
        session.add_all([boissons, epicerie])
        session.flush()
        _make_article(session, boissons, "ART-EAU", designation="Eau minérale")
        _make_article(session, epicerie, "ART-RIZ", designation="Riz basmati")
        session.flush()

        repo = ArticleRepository(session)
        assert {a.reference for a in repo.search("eau")} == {"ART-EAU"}
        assert {a.reference for a in repo.search("riz")} == {"ART-RIZ"}
        # NB : SQLite ne replie que les caractères ASCII pour LIKE/ILIKE (pas
        # d'extension ICU) ; on garde donc la casse du caractère accentué.
        assert {a.reference for a in repo.search("Épic")} == {"ART-RIZ"}


def test_search_matches_barcode(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        category = Category(nom="Boissons")
        session.add(category)
        session.flush()
        _make_article(session, category, "ART-BAR", code_barres="7778889990001")
        _make_article(session, category, "ART-AUTRE", code_barres="1112223330009")
        session.flush()

        repo = ArticleRepository(session)
        assert {a.reference for a in repo.search("7778889990001")} == {"ART-BAR"}


def test_search_filters_by_category_id(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        boissons = Category(nom="Boissons")
        epicerie = Category(nom="Épicerie")
        session.add_all([boissons, epicerie])
        session.flush()
        _make_article(session, boissons, "ART-C1")
        _make_article(session, epicerie, "ART-C2")
        session.flush()

        repo = ArticleRepository(session)
        assert {a.reference for a in repo.search(category_id=boissons.id)} == {"ART-C1"}


def test_search_can_exclude_inactive_articles(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        category = Category(nom="Boissons")
        session.add(category)
        session.flush()
        _make_article(session, category, "ART-ACTIVE", statut=StatutActifInactif.ACTIF)
        _make_article(session, category, "ART-INACTIVE", statut=StatutActifInactif.INACTIF)
        session.flush()

        repo = ArticleRepository(session)
        assert {a.reference for a in repo.search(include_inactive=False)} == {"ART-ACTIVE"}


def test_search_low_stock_only(initialized_db: Settings) -> None:
    with session_scope(initialized_db) as session:
        category = Category(nom="Boissons")
        session.add(category)
        session.flush()
        _make_article(session, category, "ART-LOW", stock_actuel=Decimal("2"), stock_min=Decimal("5"))
        _make_article(session, category, "ART-OK", stock_actuel=Decimal("50"), stock_min=Decimal("5"))
        session.flush()

        repo = ArticleRepository(session)
        assert {a.reference for a in repo.search(low_stock_only=True)} == {"ART-LOW"}
