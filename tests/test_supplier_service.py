from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError


def test_create_supplier_as_administrateur(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.suppliers.create_supplier(
        "Établissements Martin",
        contact="Jean Martin",
        telephone="0123456789",
        email="contact@martin.example",
        adresse="1 rue de la Paix",
        ville="Paris",
        pays="France",
        observations="Fournisseur historique",
    )

    assert summary.id is not None
    assert summary.nom == "Établissements Martin"
    assert summary.contact == "Jean Martin"
    assert summary.ville == "Paris"
    assert summary.actif is True


def test_create_supplier_with_only_required_field(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.suppliers.create_supplier("Fournisseur minimal")

    assert summary.nom == "Fournisseur minimal"
    assert summary.contact is None
    assert summary.email is None


def test_create_supplier_strips_whitespace(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.suppliers.create_supplier("  Fournisseur  ", ville="  Lyon  ")

    assert summary.nom == "Fournisseur"
    assert summary.ville == "Lyon"


def test_create_supplier_blank_optional_field_becomes_none(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.suppliers.create_supplier("Fournisseur", contact="   ")

    assert summary.contact is None


def test_create_supplier_denied_without_permission(login_as) -> None:
    """Le Vendeur n'a pas SUPPLIER_CREATE."""
    stack, _ = login_as("Vendeur")

    try:
        stack.suppliers.create_supplier("Fournisseur")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_create_supplier_empty_name_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.suppliers.create_supplier("   ")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_supplier_name_too_long_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.suppliers.create_supplier("x" * 151)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_supplier_invalid_email_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.suppliers.create_supplier("Fournisseur", email="pas-un-email")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_supplier_duplicate_name_is_allowed(login_as) -> None:
    """Contrairement aux catégories, le modèle validé ne définit aucune unicité
    sur le nom d'un fournisseur : deux fournisseurs peuvent partager un nom."""
    stack, _ = login_as("Administrateur")
    stack.suppliers.create_supplier("Fournisseur Générique", ville="Paris")

    second = stack.suppliers.create_supplier("Fournisseur Générique", ville="Lyon")

    assert second.nom == "Fournisseur Générique"
    assert len(stack.suppliers.list_suppliers(search="Fournisseur Générique")) == 2


def test_update_supplier_changes_fields(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur", ville="Paris")

    updated = stack.suppliers.update_supplier(created.id, "Nouveau nom", ville="Marseille")

    assert updated.nom == "Nouveau nom"
    assert updated.ville == "Marseille"
    assert updated.id == created.id


def test_update_supplier_preserves_omitted_fields(login_as) -> None:
    """Régression : un champ non transmis à update_supplier ne doit jamais être
    effacé silencieusement — seul un champ explicitement fourni est modifié."""
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier(
        "Fournisseur", contact="Jean Martin", email="jean@example.com", pays="France"
    )

    updated = stack.suppliers.update_supplier(created.id, "Fournisseur", ville="Marseille")

    assert updated.ville == "Marseille"
    assert updated.contact == "Jean Martin"
    assert updated.email == "jean@example.com"
    assert updated.pays == "France"


def test_update_supplier_can_explicitly_clear_a_field(login_as) -> None:
    """Un champ explicitement fourni comme vide/None est bien effacé (ce n'est
    que l'omission d'un paramètre qui préserve la valeur actuelle)."""
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur", contact="Jean Martin")

    updated = stack.suppliers.update_supplier(created.id, "Fournisseur", contact="")

    assert updated.contact is None


def test_update_supplier_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Consultation")

    try:
        stack.suppliers.update_supplier(1, "Nouveau nom")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_update_supplier_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.suppliers.update_supplier(999999, "Peu importe")
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_update_supplier_invalid_email_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur")

    try:
        stack.suppliers.update_supplier(created.id, "Fournisseur", email="invalide")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_search_suppliers_filters_by_name(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.suppliers.create_supplier("Martin SARL")
    stack.suppliers.create_supplier("Dupont SA")

    results = stack.suppliers.list_suppliers(search="martin")

    names = {s.nom for s in results}
    assert names == {"Martin SARL"}


def test_search_suppliers_matches_city(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.suppliers.create_supplier("Martin SARL", ville="Lyon")
    stack.suppliers.create_supplier("Dupont SA", ville="Paris")

    results = stack.suppliers.list_suppliers(search="lyon")

    names = {s.nom for s in results}
    assert names == {"Martin SARL"}


def test_search_suppliers_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    try:
        stack.suppliers.list_suppliers()
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_activate_supplier_requires_supplier_activate_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.suppliers.create_supplier("Fournisseur")
    admin_stack.suppliers.deactivate_supplier(created.id)

    consultation_stack, _ = login_as("Consultation")
    try:
        consultation_stack.suppliers.activate_supplier(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_activate_supplier_succeeds_for_gestionnaire_stock(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.suppliers.create_supplier("Fournisseur")
    admin_stack.suppliers.deactivate_supplier(created.id)

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    reactivated = gestionnaire_stack.suppliers.activate_supplier(created.id)

    assert reactivated.actif is True


def test_deactivate_supplier_requires_supplier_deactivate_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.suppliers.create_supplier("Fournisseur")

    consultation_stack, _ = login_as("Consultation")
    try:
        consultation_stack.suppliers.deactivate_supplier(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_deactivate_supplier_does_not_delete_it(login_as) -> None:
    """Jamais de suppression physique : un fournisseur désactivé reste consultable."""
    stack, _ = login_as("Administrateur")
    created = stack.suppliers.create_supplier("Fournisseur")

    stack.suppliers.deactivate_supplier(created.id)

    still_there = stack.suppliers.get_supplier(created.id)
    assert still_there.actif is False
    assert still_there.nom == "Fournisseur"


def test_inactive_supplier_excluded_when_include_inactive_false(login_as) -> None:
    """Contrat utilisé par les futurs modules Articles/Entrées : un fournisseur inactif
    ne doit plus être proposé pour de nouvelles opérations."""
    stack, _ = login_as("Administrateur")
    active = stack.suppliers.create_supplier("Fournisseur actif")
    inactive = stack.suppliers.create_supplier("Fournisseur obsolète")
    stack.suppliers.deactivate_supplier(inactive.id)

    active_only = stack.suppliers.list_suppliers(include_inactive=False)
    names = {s.nom for s in active_only}
    assert "Fournisseur actif" in names
    assert "Fournisseur obsolète" not in names

    all_suppliers = stack.suppliers.list_suppliers(include_inactive=True)
    assert "Fournisseur obsolète" in {s.nom for s in all_suppliers}


def test_toggle_supplier_status_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.suppliers.deactivate_supplier(999999)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_get_supplier_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    try:
        stack.suppliers.get_supplier(1)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass
