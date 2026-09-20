import inspect
from decimal import Decimal

from app.models.enums import TypeMouvement
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def _make_category(stack, nom="Boissons"):
    return stack.categories.create_category(nom)


def _make_supplier(stack, nom="Fournisseur Test"):
    return stack.suppliers.create_supplier(nom)


# -- création -----------------------------------------------------------------


def test_create_article_as_administrateur(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-0001", "Eau minérale 1.5L", category.id, "carton",
        Decimal("500.00"), Decimal("800.00"), Decimal("10.000"),
    )

    assert article.id is not None
    assert article.reference == "ART-0001"
    assert article.category_nom == "Boissons"
    assert article.actif is True


def test_create_article_denied_for_vendeur(login_as) -> None:
    stack, _ = login_as("Vendeur")

    try:
        stack.articles.create_article("ART-0001", "Article", 1, "pièce", Decimal("1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_create_article_denied_for_consultation(login_as) -> None:
    stack, _ = login_as("Consultation")

    try:
        stack.articles.create_article("ART-0001", "Article", 1, "pièce", Decimal("1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_create_article_succeeds_for_gestionnaire_stock(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-G1", "Article gestionnaire", category.id, "pièce", Decimal("10"), Decimal("15"), Decimal("0")
    )

    assert article.reference == "ART-G1"


def test_create_article_with_supplier(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    supplier = _make_supplier(stack)

    article = stack.articles.create_article(
        "ART-0002", "Article avec fournisseur", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"),
        fournisseur_principal_id=supplier.id,
    )

    assert article.fournisseur_principal_id == supplier.id
    assert article.fournisseur_principal_nom == supplier.nom


def test_create_article_without_supplier_is_allowed(login_as) -> None:
    """Le fournisseur principal est facultatif."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-0003", "Article sans fournisseur", category.id, "unité",
        Decimal("10"), Decimal("20"), Decimal("0"),
    )

    assert article.fournisseur_principal_id is None
    assert article.fournisseur_principal_nom is None


# -- référence unique -----------------------------------------------------------


def test_create_article_duplicate_reference_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    stack.articles.create_article("ART-DUP", "Premier", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    try:
        stack.articles.create_article("ART-DUP", "Second", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_create_article_empty_reference_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    try:
        stack.articles.create_article("   ", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


# -- catégorie ------------------------------------------------------------------


def test_create_article_unknown_category_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.articles.create_article("ART-X", "Article", 999999, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_create_article_inactive_category_is_rejected(login_as) -> None:
    """Une catégorie inactive ne doit pas pouvoir être sélectionnée pour un nouvel article."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    stack.categories.deactivate_category(category.id)

    try:
        stack.articles.create_article("ART-INACTIVE-CAT", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


# -- fournisseur ------------------------------------------------------------------


def test_create_article_unknown_supplier_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    try:
        stack.articles.create_article(
            "ART-Y", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
            fournisseur_principal_id=999999,
        )
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_create_article_inactive_supplier_is_rejected(login_as) -> None:
    """Un fournisseur désactivé ne doit plus pouvoir être sélectionné pour un nouvel article."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    supplier = _make_supplier(stack)
    stack.suppliers.deactivate_supplier(supplier.id)

    try:
        stack.articles.create_article(
            "ART-INACTIVE-SUP", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
            fournisseur_principal_id=supplier.id,
        )
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


# -- prix ---------------------------------------------------------------------


def test_create_article_negative_purchase_price_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    try:
        stack.articles.create_article("ART-NEG1", "Article", category.id, "unité", Decimal("-1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_article_negative_sale_price_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    try:
        stack.articles.create_article("ART-NEG2", "Article", category.id, "unité", Decimal("1"), Decimal("-2"), Decimal("0"))
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_article_prices_are_decimal(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-DEC", "Article", category.id, "unité", Decimal("19.99"), Decimal("29.99"), Decimal("0")
    )

    assert isinstance(article.prix_achat, Decimal)
    assert isinstance(article.prix_vente, Decimal)
    assert isinstance(article.cout_moyen_pondere, Decimal)


# -- stock minimum / maximum -----------------------------------------------------


def test_create_article_negative_stock_min_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    try:
        stack.articles.create_article("ART-SMIN", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("-5"))
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_article_negative_stock_max_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    try:
        stack.articles.create_article(
            "ART-SMAX", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
            stock_max=Decimal("-1"),
        )
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_article_stock_max_below_stock_min_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    try:
        stack.articles.create_article(
            "ART-SMAXMIN", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("10"),
            stock_max=Decimal("5"),
        )
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_article_stock_max_equal_stock_min_is_allowed(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-SMAXEQ", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("5"),
        stock_max=Decimal("5"),
    )

    assert article.stock_max == Decimal("5")


# -- code-barres ----------------------------------------------------------------


def test_create_article_with_barcode(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-BC1", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        code_barres="1234567890123",
    )

    assert article.code_barres == "1234567890123"


def test_create_article_without_barcode_is_allowed(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-BC2", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0")
    )

    assert article.code_barres is None


def test_create_article_duplicate_barcode_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    stack.articles.create_article(
        "ART-BC3", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        code_barres="9999999999999",
    )

    try:
        stack.articles.create_article(
            "ART-BC4", "Article 2", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
            code_barres="9999999999999",
        )
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_two_articles_without_barcode_do_not_conflict(login_as) -> None:
    """Le code-barres est unique seulement lorsqu'il est renseigné (NULL autorisé plusieurs fois)."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    a1 = stack.articles.create_article("ART-NB1", "Article 1", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    a2 = stack.articles.create_article("ART-NB2", "Article 2", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    assert a1.code_barres is None
    assert a2.code_barres is None


def test_find_by_barcode_returns_matching_active_article(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-BC5", "Article scanné", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        code_barres="1112223330000",
    )

    found = stack.articles.find_by_barcode("1112223330000")

    assert found is not None
    assert found.id == created.id


def test_find_by_barcode_unknown_returns_none(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.articles.find_by_barcode("0000000000001") is None


def test_find_by_barcode_ignores_deactivated_article(login_as) -> None:
    """Un scan doit toujours retomber sur l'article vendable actuel, jamais
    sur un article désactivé conservé pour son historique."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-BC6", "Article désactivé", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        code_barres="2223334440000",
    )
    stack.articles.deactivate_article(created.id)

    assert stack.articles.find_by_barcode("2223334440000") is None


def test_deactivated_article_barcode_can_be_reused_by_new_active_article(login_as) -> None:
    """La contrainte d'unicité (migration 0008) ne porte que sur les
    articles actifs : un code-barres libéré par désactivation doit pouvoir
    être repris par un nouvel article actif, sans jamais effacer
    l'historique de l'article désactivé."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    old_article = stack.articles.create_article(
        "ART-BC7", "Ancien article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        code_barres="3334445550000",
    )
    stack.articles.deactivate_article(old_article.id)

    new_article = stack.articles.create_article(
        "ART-BC8", "Nouvel article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        code_barres="3334445550000",
    )

    assert new_article.code_barres == "3334445550000"
    # L'historique de l'article désactivé reste intact (code-barres conservé).
    old_reloaded = stack.articles.get_article(old_article.id)
    assert old_reloaded.code_barres == "3334445550000"
    assert old_reloaded.actif is False
    # Le scan retrouve désormais le nouvel article actif, jamais l'ancien.
    found = stack.articles.find_by_barcode("3334445550000")
    assert found is not None
    assert found.id == new_article.id


def test_two_active_articles_cannot_share_barcode_on_update(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    stack.articles.create_article(
        "ART-BC9", "Article 1", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        code_barres="4445556660000",
    )
    other = stack.articles.create_article(
        "ART-BC10", "Article 2", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
    )

    try:
        stack.articles.update_article(
            other.id, other.reference, other.designation, category.id, other.unite,
            other.prix_achat, other.prix_vente, other.stock_min, code_barres="4445556660000",
        )
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_search_by_barcode_finds_article(login_as) -> None:
    """Le champ de recherche libre du catalogue doit aussi matcher sur le
    code-barres, pas seulement référence/désignation/catégorie."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-BC11", "Article recherché", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        code_barres="5556667770000",
    )

    results = stack.articles.list_articles(search="5556667770000")

    assert [a.id for a in results] == [created.id]


# -- stock initial et traçabilité ------------------------------------------------


def test_create_article_without_initial_stock_has_zero_stock_and_no_movement(login_as, initialized_db) -> None:
    from app.db.session import session_scope
    from app.models.movement import MouvementStock

    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-NOSTOCK", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0")
    )

    assert article.stock_actuel == Decimal("0")
    with session_scope(initialized_db) as session:
        movements = session.query(MouvementStock).filter_by(article_id=article.id).all()
    assert movements == []


def test_create_article_with_initial_stock_sets_stock_actuel(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-STOCK1", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("5"),
        stock_initial=Decimal("50"),
    )

    assert article.stock_actuel == Decimal("50")


def test_create_article_with_initial_stock_generates_traceable_movement(login_as, initialized_db) -> None:
    """§9 : le stock initial doit être tracé par un mouvement, pas une simple
    affectation directe de stock_actuel."""
    from app.db.session import session_scope
    from app.models.movement import MouvementStock

    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-STOCK2", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("5"),
        stock_initial=Decimal("50"),
    )

    with session_scope(initialized_db) as session:
        movements = session.query(MouvementStock).filter_by(article_id=article.id).all()
        assert len(movements) == 1
        movement = movements[0]
        assert movement.type == TypeMouvement.AJUSTEMENT
        assert movement.quantite == Decimal("50")
        assert movement.stock_avant == Decimal("0")
        assert movement.stock_apres == Decimal("50")
        assert movement.cout_unitaire == Decimal("100")
        assert "initial" in (movement.commentaire or "").lower()


def test_create_article_initial_cmup_equals_purchase_price(login_as) -> None:
    """§7 : en l'absence d'historique, le CMUP initial est dérivé du prix d'achat."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    article = stack.articles.create_article(
        "ART-CMUP1", "Article", category.id, "unité", Decimal("42.50"), Decimal("60"), Decimal("0"),
        stock_initial=Decimal("10"),
    )

    assert article.cout_moyen_pondere == Decimal("42.50")


def test_create_article_with_initial_stock_uses_stock_service_apply_movement(login_as, monkeypatch) -> None:
    """§Lot G : le stock initial positif doit obligatoirement passer par
    StockService.apply_movement (plus de construction manuelle de
    MouvementStock / écriture directe de stock_actuel dans ArticleService)."""
    from app.services.stock.stock_service import StockService

    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    calls: list[tuple] = []
    original_apply_movement = StockService.apply_movement

    def _spy_apply_movement(self, session, article, type_mouvement, quantite_signee, **kwargs):
        calls.append((type_mouvement, quantite_signee, kwargs))
        return original_apply_movement(self, session, article, type_mouvement, quantite_signee, **kwargs)

    monkeypatch.setattr(StockService, "apply_movement", _spy_apply_movement)

    article = stack.articles.create_article(
        "ART-STOCKSVC", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("5"),
        stock_initial=Decimal("50"),
    )

    assert len(calls) == 1
    type_mouvement, quantite_signee, kwargs = calls[0]
    assert type_mouvement == TypeMouvement.AJUSTEMENT
    assert quantite_signee == Decimal("50")
    assert kwargs["cout_unitaire"] == Decimal("100")
    assert article.stock_actuel == Decimal("50")


def test_create_article_without_initial_stock_does_not_call_apply_movement(login_as, monkeypatch) -> None:
    """§Lot G : si stock_initial = 0, aucun mouvement n'est créé et
    StockService.apply_movement n'est donc pas appelé."""
    from app.services.stock.stock_service import StockService

    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    calls: list[tuple] = []
    monkeypatch.setattr(
        StockService,
        "apply_movement",
        lambda self, *args, **kwargs: calls.append((args, kwargs)),
    )

    article = stack.articles.create_article(
        "ART-NOSTOCKSVC", "Article", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("5"),
    )

    assert calls == []
    assert article.stock_actuel == Decimal("0")


def test_negative_initial_stock_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)

    try:
        stack.articles.create_article(
            "ART-NEGSTOCK", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
            stock_initial=Decimal("-1"),
        )
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


# -- impossibilité de modifier directement stock/CMUP ----------------------------


def test_update_article_signature_has_no_stock_or_cmup_parameter() -> None:
    """Garde-fou structurel : personne ne doit pouvoir réintroduire un paramètre
    stock_actuel/cout_moyen_pondere dans update_article par erreur."""
    from app.services.articles.article_service import ArticleService

    parameters = inspect.signature(ArticleService.update_article).parameters
    assert "stock_actuel" not in parameters
    assert "cout_moyen_pondere" not in parameters
    assert "stock_initial" not in parameters


def test_update_article_never_changes_stock_actuel(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-NOTOUCH1", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        stock_initial=Decimal("30"),
    )

    updated = stack.articles.update_article(
        created.id, "ART-NOTOUCH1", "Nouvelle désignation", category.id, "carton",
        Decimal("15"), Decimal("25"), Decimal("0"),
    )

    assert updated.stock_actuel == Decimal("30")


def test_update_article_never_changes_cmup(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-NOTOUCH2", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0")
    )

    # Même en changeant le prix d'achat par défaut, le CMUP déjà fixé ne doit pas bouger.
    updated = stack.articles.update_article(
        created.id, "ART-NOTOUCH2", "Article", category.id, "unité",
        Decimal("999"), Decimal("20"), Decimal("0"),
    )

    assert updated.cout_moyen_pondere == Decimal("10")
    assert updated.prix_achat == Decimal("999")


# -- modification ---------------------------------------------------------------


def test_update_article_changes_fields(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-UPD1", "Ancien nom", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0")
    )

    updated = stack.articles.update_article(
        created.id, "ART-UPD1-BIS", "Nouveau nom", category.id, "carton",
        Decimal("12"), Decimal("22"), Decimal("2"), stock_max=Decimal("100"),
        emplacement="Rayon A1", description="Une description", code_barres="1112223334445",
    )

    assert updated.reference == "ART-UPD1-BIS"
    assert updated.designation == "Nouveau nom"
    assert updated.unite == "carton"
    assert updated.prix_achat == Decimal("12")
    assert updated.prix_vente == Decimal("22")
    assert updated.stock_min == Decimal("2")
    assert updated.stock_max == Decimal("100")
    assert updated.emplacement == "Rayon A1"
    assert updated.description == "Une description"
    assert updated.code_barres == "1112223334445"


def test_update_article_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    try:
        stack.articles.update_article(1, "REF", "Article", 1, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_update_article_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.articles.update_article(999999, "REF", "Article", 1, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_update_article_preserves_omitted_optional_fields(login_as) -> None:
    """Même principe que la correction apportée à SupplierService : un champ
    optionnel non transmis ne doit jamais être effacé silencieusement."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    supplier = _make_supplier(stack)
    created = stack.articles.create_article(
        "ART-PRESERVE", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        fournisseur_principal_id=supplier.id, emplacement="Rayon B2", code_barres="5556667778889",
    )

    updated = stack.articles.update_article(
        created.id, "ART-PRESERVE", "Article", category.id, "unité", Decimal("11"), Decimal("21"), Decimal("0"),
    )

    assert updated.fournisseur_principal_id == supplier.id
    assert updated.emplacement == "Rayon B2"
    assert updated.code_barres == "5556667778889"


def test_update_article_keeps_inactive_category_if_unchanged(login_as) -> None:
    """Un article déjà associé à une catégorie devenue inactive reste modifiable
    sur ses autres champs sans être forcé de changer de catégorie."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-KEEPCAT", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0")
    )
    stack.categories.deactivate_category(category.id)

    updated = stack.articles.update_article(
        created.id, "ART-KEEPCAT", "Nom modifié", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
    )

    assert updated.designation == "Nom modifié"
    assert updated.category_id == category.id


def test_update_article_cannot_switch_to_inactive_category(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category_a = _make_category(stack, "Catégorie A")
    category_b = _make_category(stack, "Catégorie B")
    stack.categories.deactivate_category(category_b.id)
    created = stack.articles.create_article(
        "ART-SWITCHCAT", "Article", category_a.id, "unité", Decimal("10"), Decimal("20"), Decimal("0")
    )

    try:
        stack.articles.update_article(
            created.id, "ART-SWITCHCAT", "Article", category_b.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        )
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_update_article_keeps_inactive_supplier_if_unchanged(login_as) -> None:
    """Les articles existants doivent conserver leur référence historique au fournisseur."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    supplier = _make_supplier(stack)
    created = stack.articles.create_article(
        "ART-KEEPSUP", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        fournisseur_principal_id=supplier.id,
    )
    stack.suppliers.deactivate_supplier(supplier.id)

    updated = stack.articles.update_article(
        created.id, "ART-KEEPSUP", "Nom modifié", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        fournisseur_principal_id=supplier.id,
    )

    assert updated.fournisseur_principal_id == supplier.id


def test_update_article_cannot_switch_to_inactive_supplier(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    supplier = _make_supplier(stack)
    stack.suppliers.deactivate_supplier(supplier.id)
    created = stack.articles.create_article(
        "ART-SWITCHSUP", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0")
    )

    try:
        stack.articles.update_article(
            created.id, "ART-SWITCHSUP", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
            fournisseur_principal_id=supplier.id,
        )
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_update_article_can_remove_supplier(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    supplier = _make_supplier(stack)
    created = stack.articles.create_article(
        "ART-REMOVESUP", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        fournisseur_principal_id=supplier.id,
    )

    updated = stack.articles.update_article(
        created.id, "ART-REMOVESUP", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        fournisseur_principal_id=None,
    )

    assert updated.fournisseur_principal_id is None


def test_update_article_duplicate_reference_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    stack.articles.create_article("ART-TAKEN", "Article 1", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    second = stack.articles.create_article("ART-FREE", "Article 2", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    try:
        stack.articles.update_article(
            second.id, "ART-TAKEN", "Article 2", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"),
        )
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


# -- consultation, recherche, filtres ---------------------------------------------


def test_get_article_returns_full_details(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-GET", "Article détaillé", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        emplacement="Rayon C3",
    )

    fetched = stack.articles.get_article(created.id)

    assert fetched.reference == "ART-GET"
    assert fetched.emplacement == "Rayon C3"


def test_get_article_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.articles.get_article(999999)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_get_article_denied_when_not_authenticated(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.auth.logout()

    try:
        stack.articles.get_article(1)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_search_articles_by_reference(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    stack.articles.create_article("ART-SEARCH1", "Premier", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.create_article("AUTRE-REF", "Second", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    results = stack.articles.list_articles(search="SEARCH")

    assert {a.reference for a in results} == {"ART-SEARCH1"}


def test_search_articles_by_designation(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    stack.articles.create_article("ART-D1", "Chaise en bois", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.create_article("ART-D2", "Table en verre", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    results = stack.articles.list_articles(search="chaise")

    assert {a.reference for a in results} == {"ART-D1"}


def test_search_articles_by_category_name(login_as) -> None:
    stack, _ = login_as("Administrateur")
    boissons = _make_category(stack, "Boissons")
    epicerie = _make_category(stack, "Épicerie")
    stack.articles.create_article("ART-C1", "Article 1", boissons.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.create_article("ART-C2", "Article 2", epicerie.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    results = stack.articles.list_articles(search="boissons")

    assert {a.reference for a in results} == {"ART-C1"}


def test_filter_articles_by_category_id(login_as) -> None:
    stack, _ = login_as("Administrateur")
    boissons = _make_category(stack, "Boissons")
    epicerie = _make_category(stack, "Épicerie")
    stack.articles.create_article("ART-F1", "Article 1", boissons.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.create_article("ART-F2", "Article 2", epicerie.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))

    results = stack.articles.list_articles(category_id=boissons.id)

    assert {a.reference for a in results} == {"ART-F1"}


def test_filter_articles_low_stock_only(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    stack.articles.create_article(
        "ART-LOW", "Stock faible", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("10"),
        stock_initial=Decimal("5"),
    )
    stack.articles.create_article(
        "ART-OK", "Stock suffisant", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("10"),
        stock_initial=Decimal("50"),
    )

    results = stack.articles.list_articles(low_stock_only=True)

    assert {a.reference for a in results} == {"ART-LOW"}


def test_list_articles_allowed_for_vendeur(login_as) -> None:
    """Contrôle positif : le Vendeur dispose bien d'ARTICLE_VIEW dans la matrice actuelle."""
    stack, _ = login_as("Vendeur")
    stack.articles.list_articles()  # ne doit pas lever


def test_list_articles_denied_for_role_without_article_view(login_as) -> None:
    """Vérifie le contrôle négatif via require_permission directement (aucun rôle
    actuel n'est dépourvu d'ARTICLE_VIEW hormis un utilisateur non connecté)."""
    stack, _ = login_as("Administrateur")
    stack.auth.logout()

    try:
        stack.articles.list_articles()
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


# -- activation / désactivation ---------------------------------------------------


def test_activate_article_requires_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    category = _make_category(admin_stack)
    created = admin_stack.articles.create_article(
        "ART-ACT1", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0")
    )
    admin_stack.articles.deactivate_article(created.id)

    vendeur_stack, _ = login_as("Vendeur")
    try:
        vendeur_stack.articles.activate_article(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_deactivate_article_requires_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    category = _make_category(admin_stack)
    created = admin_stack.articles.create_article(
        "ART-DEACT1", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0")
    )

    vendeur_stack, _ = login_as("Vendeur")
    try:
        vendeur_stack.articles.deactivate_article(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_deactivate_article_does_not_delete_it(login_as) -> None:
    """Jamais de suppression physique : un article désactivé reste consultable
    avec toutes ses données historiques."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-DEACT2", "Article", category.id, "unité", Decimal("10"), Decimal("20"), Decimal("0"),
        stock_initial=Decimal("5"),
    )

    stack.articles.deactivate_article(created.id)

    still_there = stack.articles.get_article(created.id)
    assert still_there.actif is False
    assert still_there.reference == "ART-DEACT2"
    assert still_there.stock_actuel == Decimal("5")


def test_reactivating_an_article_works(login_as) -> None:
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    created = stack.articles.create_article(
        "ART-REACT", "Article", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0")
    )
    stack.articles.deactivate_article(created.id)

    reactivated = stack.articles.activate_article(created.id)

    assert reactivated.actif is True


def test_inactive_article_excluded_when_include_inactive_false(login_as) -> None:
    """Un article inactif ne doit plus être proposé pour de nouvelles opérations."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    active = stack.articles.create_article("ART-VISIBLE", "Article actif", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    inactive = stack.articles.create_article("ART-HIDDEN", "Article inactif", category.id, "unité", Decimal("1"), Decimal("2"), Decimal("0"))
    stack.articles.deactivate_article(inactive.id)

    active_only = stack.articles.list_articles(include_inactive=False)
    references = {a.reference for a in active_only}
    assert "ART-VISIBLE" in references
    assert "ART-HIDDEN" not in references
