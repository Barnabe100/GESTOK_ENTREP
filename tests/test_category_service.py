from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def test_create_category_as_administrateur(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.categories.create_category("Boissons")

    assert summary.id is not None
    assert summary.nom == "Boissons"
    assert summary.actif is True


def test_create_category_strips_whitespace(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.categories.create_category("  Épicerie  ")

    assert summary.nom == "Épicerie"


def test_create_category_denied_without_permission(login_as) -> None:
    """Le Vendeur n'a pas CATEGORY_CREATE."""
    stack, _ = login_as("Vendeur")

    try:
        stack.categories.create_category("Boissons")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_create_category_empty_name_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.categories.create_category("   ")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_category_name_too_long_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.categories.create_category("x" * 101)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_category_duplicate_name_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.categories.create_category("Boissons")

    try:
        stack.categories.create_category("Boissons")
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_update_category_renames_successfully(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.categories.create_category("Boissons")

    updated = stack.categories.update_category(created.id, "Boissons fraîches")

    assert updated.nom == "Boissons fraîches"
    assert updated.id == created.id


def test_update_category_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Consultation")

    try:
        stack.categories.update_category(1, "Nouveau nom")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_update_category_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.categories.update_category(999999, "Peu importe")
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_update_category_to_existing_name_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.categories.create_category("Boissons")
    second = stack.categories.create_category("Épicerie")

    try:
        stack.categories.update_category(second.id, "Boissons")
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_update_category_can_keep_its_own_name(login_as) -> None:
    """Renommer une catégorie avec son propre nom actuel ne doit pas être vu comme un doublon."""
    stack, _ = login_as("Administrateur")
    created = stack.categories.create_category("Boissons")

    updated = stack.categories.update_category(created.id, "Boissons")

    assert updated.nom == "Boissons"


def test_search_categories_filters_by_name(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.categories.create_category("Boissons")
    stack.categories.create_category("Épicerie")

    results = stack.categories.list_categories(search="bois")

    names = {c.nom for c in results}
    assert names == {"Boissons"}


def test_search_categories_denied_without_permission(login_as) -> None:
    """Le Vendeur n'a pas CATEGORY_VIEW."""
    stack, _ = login_as("Vendeur")

    try:
        stack.categories.list_categories()
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_activate_category_requires_category_activate_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.categories.create_category("Boissons")
    admin_stack.categories.deactivate_category(created.id)

    consultation_stack, _ = login_as("Consultation")
    try:
        consultation_stack.categories.activate_category(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_activate_category_succeeds_for_gestionnaire_stock(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.categories.create_category("Boissons")
    admin_stack.categories.deactivate_category(created.id)

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    reactivated = gestionnaire_stack.categories.activate_category(created.id)

    assert reactivated.actif is True


def test_deactivate_category_requires_category_deactivate_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.categories.create_category("Boissons")

    consultation_stack, _ = login_as("Consultation")
    try:
        consultation_stack.categories.deactivate_category(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_deactivate_category_does_not_delete_it(login_as) -> None:
    """Jamais de suppression physique : une catégorie désactivée reste consultable."""
    stack, _ = login_as("Administrateur")
    created = stack.categories.create_category("Boissons")

    stack.categories.deactivate_category(created.id)

    still_there = stack.categories.get_category(created.id)
    assert still_there.actif is False
    assert still_there.nom == "Boissons"


def test_inactive_category_excluded_when_include_inactive_false(login_as) -> None:
    """Contrat utilisé par le futur module Articles : une catégorie inactive ne doit
    plus être proposée pour de nouvelles opérations."""
    stack, _ = login_as("Administrateur")
    active = stack.categories.create_category("Boissons")
    inactive = stack.categories.create_category("Obsolète")
    stack.categories.deactivate_category(inactive.id)

    active_only = stack.categories.list_categories(include_inactive=False)

    names = {c.nom for c in active_only}
    assert "Boissons" in names
    assert "Obsolète" not in names

    all_categories = stack.categories.list_categories(include_inactive=True)
    assert "Obsolète" in {c.nom for c in all_categories}


def test_toggle_category_status_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.categories.deactivate_category(999999)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_get_category_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    try:
        stack.categories.get_category(1)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass
