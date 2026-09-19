import pytest

from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError


# -- création --------------------------------------------------------------------------


def test_create_client_as_administrateur(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.clients.create_client(
        "Jean Dupont", telephone="0123456789", email="jean@example.com",
        adresse="1 rue de la Paix", observations="Client fidèle",
    )

    assert summary.id is not None
    assert summary.nom == "Jean Dupont"
    assert summary.telephone == "0123456789"
    assert summary.email == "jean@example.com"
    assert summary.adresse == "1 rue de la Paix"
    assert summary.observations == "Client fidèle"
    assert summary.actif is True


def test_create_client_with_only_required_field(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.clients.create_client("Client minimal")

    assert summary.nom == "Client minimal"
    assert summary.telephone is None
    assert summary.email is None
    assert summary.adresse is None
    assert summary.observations is None


def test_create_client_strips_whitespace(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.clients.create_client("  Client  ", telephone="  0102030405  ")

    assert summary.nom == "Client"
    assert summary.telephone == "0102030405"


def test_create_client_blank_optional_field_becomes_none(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.clients.create_client("Client", telephone="   ")

    assert summary.telephone is None


def test_create_client_empty_name_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.clients.create_client("   ")


def test_create_client_name_too_long_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.clients.create_client("x" * 151)


def test_create_client_invalid_email_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(ValidationError):
        stack.clients.create_client("Client", email="pas-un-email")


def test_create_client_duplicate_name_is_allowed(login_as) -> None:
    """Comme pour les fournisseurs, aucune contrainte d'unicité sur le nom :
    deux clients peuvent légitimement partager un nom."""
    stack, _ = login_as("Administrateur")
    stack.clients.create_client("Client Générique", telephone="0100000000")

    second = stack.clients.create_client("Client Générique", telephone="0200000000")

    assert second.nom == "Client Générique"
    assert len(stack.clients.list_clients(search="Client Générique")) == 2


# -- modification -----------------------------------------------------------------------


def test_update_client_changes_fields(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client", telephone="0100000000")

    updated = stack.clients.update_client(created.id, "Nouveau nom", telephone="0200000000")

    assert updated.nom == "Nouveau nom"
    assert updated.telephone == "0200000000"
    assert updated.id == created.id


def test_update_client_preserves_omitted_fields(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client(
        "Client", telephone="0100000000", email="a@b.com", adresse="12 rue X"
    )

    updated = stack.clients.update_client(created.id, "Client", observations="Nouvelle note")

    assert updated.telephone == "0100000000"
    assert updated.email == "a@b.com"
    assert updated.adresse == "12 rue X"
    assert updated.observations == "Nouvelle note"


def test_update_client_can_explicitly_clear_a_field(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client", telephone="0100000000")

    updated = stack.clients.update_client(created.id, "Client", telephone="")

    assert updated.telephone is None


def test_update_client_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Consultation")

    with pytest.raises(PermissionDeniedError):
        stack.clients.update_client(1, "Nouveau nom")


def test_update_client_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.clients.update_client(999999, "Peu importe")


def test_update_client_invalid_email_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client")

    with pytest.raises(ValidationError):
        stack.clients.update_client(created.id, "Client", email="invalide")


# -- recherche --------------------------------------------------------------------------


def test_search_clients_filters_by_name(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.clients.create_client("Martin SARL")
    stack.clients.create_client("Dupont SA")

    results = stack.clients.list_clients(search="martin")

    assert {c.nom for c in results} == {"Martin SARL"}


def test_search_clients_matches_telephone(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.clients.create_client("Client A", telephone="0102030405")
    stack.clients.create_client("Client B", telephone="0999999999")

    results = stack.clients.list_clients(search="0102")

    assert {c.nom for c in results} == {"Client A"}


def test_search_clients_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Consultation")

    with pytest.raises(PermissionDeniedError):
        stack.clients.list_clients()


# -- activation / désactivation ----------------------------------------------------------


def test_activate_client_requires_client_activate_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.clients.create_client("Client")
    admin_stack.clients.deactivate_client(created.id)

    vendeur_stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        vendeur_stack.clients.activate_client(created.id)


def test_activate_client_succeeds_for_gestionnaire_stock(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.clients.create_client("Client")
    admin_stack.clients.deactivate_client(created.id)

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    reactivated = gestionnaire_stack.clients.activate_client(created.id)

    assert reactivated.actif is True


def test_deactivate_client_requires_client_deactivate_permission(login_as) -> None:
    """Décision métier explicite : le Vendeur peut créer/modifier un client
    mais jamais l'activer/le désactiver."""
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.clients.create_client("Client")

    vendeur_stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        vendeur_stack.clients.deactivate_client(created.id)


def test_deactivate_client_does_not_delete_it(login_as) -> None:
    """Jamais de suppression physique : un client désactivé reste consultable."""
    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client")

    stack.clients.deactivate_client(created.id)

    still_there = stack.clients.get_client(created.id)
    assert still_there.actif is False
    assert still_there.nom == "Client"


def test_inactive_client_excluded_when_include_inactive_false(login_as) -> None:
    """Contrat utilisé par le sélecteur de SaleFormDialog : un client
    inactif ne doit plus être proposé pour une nouvelle vente."""
    stack, _ = login_as("Administrateur")
    active = stack.clients.create_client("Client actif")
    inactive = stack.clients.create_client("Client obsolète")
    stack.clients.deactivate_client(inactive.id)

    active_only = stack.clients.list_clients(include_inactive=False)
    names = {c.nom for c in active_only}
    assert "Client actif" in names
    assert "Client obsolète" not in names

    all_clients = stack.clients.list_clients(include_inactive=True)
    assert "Client obsolète" in {c.nom for c in all_clients}


def test_toggle_client_status_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    with pytest.raises(NotFoundError):
        stack.clients.deactivate_client(999999)


def test_get_client_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Consultation")

    with pytest.raises(PermissionDeniedError):
        stack.clients.get_client(1)


# -- matrice RBAC par rôle ----------------------------------------------------------------


def test_vendeur_has_view_create_update_but_not_activate(login_as) -> None:
    stack, _ = login_as("Vendeur")

    assert stack.permissions.has_permission("CLIENT_VIEW") is True
    assert stack.permissions.has_permission("CLIENT_CREATE") is True
    assert stack.permissions.has_permission("CLIENT_UPDATE") is True
    assert stack.permissions.has_permission("CLIENT_ACTIVATE") is False
    assert stack.permissions.has_permission("CLIENT_DEACTIVATE") is False


def test_gestionnaire_stock_has_all_client_permissions(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")

    for code in ("CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE", "CLIENT_ACTIVATE", "CLIENT_DEACTIVATE"):
        assert stack.permissions.has_permission(code) is True


def test_consultation_has_no_client_permissions(login_as) -> None:
    stack, _ = login_as("Consultation")

    for code in ("CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE", "CLIENT_ACTIVATE", "CLIENT_DEACTIVATE"):
        assert stack.permissions.has_permission(code) is False


def test_administrateur_has_all_client_permissions(login_as) -> None:
    stack, _ = login_as("Administrateur")

    for code in ("CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE", "CLIENT_ACTIVATE", "CLIENT_DEACTIVATE"):
        assert stack.permissions.has_permission(code) is True


# -- audit ------------------------------------------------------------------------------


def test_create_client_is_audited(login_as) -> None:
    from app.config.settings import get_settings
    from app.db.session import session_scope
    from app.models.audit import AuditLog

    stack, current_user = login_as("Administrateur")
    created = stack.clients.create_client("Client audité")

    with session_scope(get_settings()) as session:
        rows = session.query(AuditLog).filter_by(action="CLIENT_CREATE", entite_id=created.id).all()
    assert len(rows) == 1
    assert rows[0].entite == "clients"
    assert rows[0].user_id == current_user.id


def test_update_client_is_audited(login_as) -> None:
    from app.config.settings import get_settings
    from app.db.session import session_scope
    from app.models.audit import AuditLog

    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client")
    stack.clients.update_client(created.id, "Client renommé")

    with session_scope(get_settings()) as session:
        rows = session.query(AuditLog).filter_by(action="CLIENT_UPDATE", entite_id=created.id).all()
    assert len(rows) == 1
    assert rows[0].entite == "clients"


def test_activate_and_deactivate_client_are_audited(login_as) -> None:
    from app.config.settings import get_settings
    from app.db.session import session_scope
    from app.models.audit import AuditLog

    stack, _ = login_as("Administrateur")
    created = stack.clients.create_client("Client")
    stack.clients.deactivate_client(created.id)
    stack.clients.activate_client(created.id)

    with session_scope(get_settings()) as session:
        deactivate_rows = session.query(AuditLog).filter_by(action="CLIENT_DEACTIVATE", entite_id=created.id).all()
        activate_rows = session.query(AuditLog).filter_by(action="CLIENT_ACTIVATE", entite_id=created.id).all()
    assert len(deactivate_rows) == 1
    assert len(activate_rows) == 1
