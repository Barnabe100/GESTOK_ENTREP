from decimal import Decimal

from app.db.unite_article_seed import CANONICAL_UNITES_ARTICLE
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def test_list_unites_includes_canonical_values(login_as) -> None:
    """La base de test est synchronisée (voir tests/conftest.py) exactement
    comme une installation réelle au démarrage — les valeurs canoniques
    (§7.1) doivent déjà être proposées sans aucune action manuelle."""
    stack, _ = login_as("Administrateur")

    libelles = {u.libelle for u in stack.unites_article.list_unites()}

    assert libelles == set(CANONICAL_UNITES_ARTICLE)


def test_create_unite_as_gestionnaire_stock(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")

    summary = stack.unites_article.create_unite("Botte")

    assert summary.id is not None
    assert summary.libelle == "Botte"
    assert "Botte" in {u.libelle for u in stack.unites_article.list_unites()}


def test_create_unite_as_administrateur(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.unites_article.create_unite("Plateau")

    assert summary.libelle == "Plateau"


def test_create_unite_strips_whitespace(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.unites_article.create_unite("  Rouleau  ")

    assert summary.libelle == "Rouleau"


def test_create_unite_denied_for_vendeur(login_as) -> None:
    """Le Vendeur ne crée ni ne modifie d'article (ARTICLE_CREATE/UPDATE
    absentes de son rôle) : il ne doit pas non plus pouvoir créer une
    nouvelle unité."""
    stack, _ = login_as("Vendeur")

    try:
        stack.unites_article.create_unite("Bidon")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_create_unite_empty_label_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.unites_article.create_unite("   ")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_unite_too_long_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.unites_article.create_unite("x" * 21)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_unite_rejects_exact_duplicate(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.unites_article.create_unite("Pièce")
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_create_unite_rejects_case_insensitive_duplicate(login_as) -> None:
    """§7.3 : empêcher les doublons insensibles à la casse (ex. « pièce »
    alors que « Pièce » existe déjà)."""
    stack, _ = login_as("Administrateur")

    try:
        stack.unites_article.create_unite("pièce")
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass

    try:
        stack.unites_article.create_unite("  PIÈCE  ")
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_create_unite_rejects_duplicate_of_custom_unit(login_as) -> None:
    """Le doublon est détecté aussi contre une unité déjà créée via le
    bouton « Nouveau », pas seulement contre la liste canonique initiale."""
    stack, _ = login_as("Administrateur")
    stack.unites_article.create_unite("Botte")

    try:
        stack.unites_article.create_unite("botte")
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_list_unites_is_ordered_alphabetically(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.unites_article.create_unite("Zeste")
    stack.unites_article.create_unite("Ampoule")

    libelles = [u.libelle for u in stack.unites_article.list_unites()]

    assert libelles == sorted(libelles)


# -- suppression d'une unité (Mission 4, §4) ----------------------------------


def test_delete_unite_removes_unused_unite(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.unites_article.create_unite("Botte")

    stack.unites_article.delete_unite(created.id)

    assert "Botte" not in {u.libelle for u in stack.unites_article.list_unites()}


def test_delete_unite_denied_when_used_by_an_article(login_as) -> None:
    """§4.3 : une unité référencée par un article existant ne doit jamais
    pouvoir être supprimée, même par un administrateur."""
    stack, _ = login_as("Administrateur")
    created = stack.unites_article.create_unite("Botte")
    category = stack.categories.create_category("Matériel")
    stack.articles.create_article(
        "ART-BOTTE", "Botte de paille", category.id, "Botte",
        Decimal("1000"), Decimal("1500"), Decimal("0"),
    )

    try:
        stack.unites_article.delete_unite(created.id)
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass

    assert "Botte" in {u.libelle for u in stack.unites_article.list_unites()}


def test_delete_unite_denied_when_used_case_insensitive(login_as) -> None:
    """La vérification d'usage ignore la casse et les espaces superflus,
    comme la détection de doublon à la création."""
    stack, _ = login_as("Administrateur")
    created = stack.unites_article.create_unite("Botte")
    category = stack.categories.create_category("Matériel")
    stack.articles.create_article(
        "ART-BOTTE", "Botte de paille", category.id, "  botte  ",
        Decimal("1000"), Decimal("1500"), Decimal("0"),
    )

    try:
        stack.unites_article.delete_unite(created.id)
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_is_unite_used_reflects_article_usage(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.unites_article.create_unite("Botte")

    assert stack.unites_article.is_unite_used(created.id) is False

    category = stack.categories.create_category("Matériel")
    stack.articles.create_article(
        "ART-BOTTE", "Botte de paille", category.id, "Botte",
        Decimal("1000"), Decimal("1500"), Decimal("0"),
    )

    assert stack.unites_article.is_unite_used(created.id) is True


def test_delete_unite_denied_for_vendeur(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.unites_article.create_unite("Botte")
    vendeur_stack, _ = login_as("Vendeur")

    try:
        vendeur_stack.unites_article.delete_unite(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_delete_unite_nonexistent_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.unites_article.delete_unite(999999)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_is_unite_used_nonexistent_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.unites_article.is_unite_used(999999)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass
