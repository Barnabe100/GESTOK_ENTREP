from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError


def test_create_exit_reason_as_administrateur(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.exit_reasons.create_exit_reason("Perte", "Marchandise perdue ou volée")

    assert summary.id is not None
    assert summary.libelle == "Perte"
    assert summary.description == "Marchandise perdue ou volée"
    assert summary.actif is True


def test_create_exit_reason_without_description(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.exit_reasons.create_exit_reason("Casse")

    assert summary.description is None


def test_create_exit_reason_strips_whitespace(login_as) -> None:
    stack, _ = login_as("Administrateur")

    summary = stack.exit_reasons.create_exit_reason("  Don  ", "  Offert à un client  ")

    assert summary.libelle == "Don"
    assert summary.description == "Offert à un client"


def test_create_exit_reason_denied_for_gestionnaire_stock(login_as) -> None:
    """Décision métier de cette phase : la gestion des motifs est réservée à
    l'Administrateur, y compris pour le Gestionnaire de stock."""
    stack, _ = login_as("Gestionnaire de stock")

    try:
        stack.exit_reasons.create_exit_reason("Perte")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_create_exit_reason_denied_for_vendeur(login_as) -> None:
    stack, _ = login_as("Vendeur")

    try:
        stack.exit_reasons.create_exit_reason("Perte")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_create_exit_reason_empty_label_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.exit_reasons.create_exit_reason("   ")
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_exit_reason_label_too_long_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.exit_reasons.create_exit_reason("x" * 151)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_exit_reason_description_too_long_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.exit_reasons.create_exit_reason("Perte", "x" * 501)
        assert False, "devait lever ValidationError"
    except ValidationError:
        pass


def test_create_exit_reason_duplicate_label_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")

    try:
        stack.exit_reasons.create_exit_reason("Perte")
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_create_exit_reason_duplicate_ignoring_case_and_whitespace_is_rejected(login_as) -> None:
    """« Perte », «  perte  » et « PERTE » ne doivent pas pouvoir coexister."""
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")

    for variant in (" perte ", "PERTE", "PeRtE", "  Perte"):
        try:
            stack.exit_reasons.create_exit_reason(variant)
            assert False, f"devait lever ConflictError pour la variante {variant!r}"
        except ConflictError:
            pass

    assert len(stack.exit_reasons.list_exit_reasons()) == 1


def test_update_exit_reason_changes_fields(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")

    updated = stack.exit_reasons.update_exit_reason(created.id, "Perte constatée", "Suite à inventaire")

    assert updated.libelle == "Perte constatée"
    assert updated.description == "Suite à inventaire"
    assert updated.id == created.id


def test_update_exit_reason_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")

    try:
        stack.exit_reasons.update_exit_reason(1, "Nouveau libellé")
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_update_exit_reason_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.exit_reasons.update_exit_reason(999999, "Peu importe")
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_update_exit_reason_to_existing_label_is_rejected_ignoring_case(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")
    second = stack.exit_reasons.create_exit_reason("Casse")

    try:
        stack.exit_reasons.update_exit_reason(second.id, "  PERTE  ")
        assert False, "devait lever ConflictError"
    except ConflictError:
        pass


def test_update_exit_reason_can_keep_its_own_label(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")

    updated = stack.exit_reasons.update_exit_reason(created.id, "Perte", "Description ajoutée")

    assert updated.libelle == "Perte"
    assert updated.description == "Description ajoutée"


def test_search_exit_reasons_filters_by_label(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.exit_reasons.create_exit_reason("Perte")
    stack.exit_reasons.create_exit_reason("Casse")

    results = stack.exit_reasons.list_exit_reasons(search="per")

    assert {r.libelle for r in results} == {"Perte"}


def test_list_exit_reasons_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")

    try:
        stack.exit_reasons.list_exit_reasons()
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_activate_exit_reason_requires_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.exit_reasons.create_exit_reason("Perte")
    admin_stack.exit_reasons.deactivate_exit_reason(created.id)

    gestionnaire_stack, _ = login_as("Gestionnaire de stock")
    try:
        gestionnaire_stack.exit_reasons.activate_exit_reason(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_deactivate_exit_reason_requires_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    created = admin_stack.exit_reasons.create_exit_reason("Perte")

    vendeur_stack, _ = login_as("Vendeur")
    try:
        vendeur_stack.exit_reasons.deactivate_exit_reason(created.id)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass


def test_deactivate_exit_reason_does_not_delete_it(login_as) -> None:
    """Jamais de suppression physique : un motif désactivé reste consultable
    (préservation de l'historique)."""
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")

    stack.exit_reasons.deactivate_exit_reason(created.id)

    still_there = stack.exit_reasons.get_exit_reason(created.id)
    assert still_there.actif is False
    assert still_there.libelle == "Perte"


def test_inactive_exit_reason_excluded_when_include_inactive_false(login_as) -> None:
    """Contrat utilisé par le futur module Sorties : un motif inactif ne doit
    plus être proposé pour une nouvelle sortie."""
    stack, _ = login_as("Administrateur")
    active = stack.exit_reasons.create_exit_reason("Perte")
    inactive = stack.exit_reasons.create_exit_reason("Motif obsolète")
    stack.exit_reasons.deactivate_exit_reason(inactive.id)

    active_only = stack.exit_reasons.list_exit_reasons(include_inactive=False)
    labels = {r.libelle for r in active_only}
    assert "Perte" in labels
    assert "Motif obsolète" not in labels

    all_reasons = stack.exit_reasons.list_exit_reasons(include_inactive=True)
    assert "Motif obsolète" in {r.libelle for r in all_reasons}


def test_reactivating_a_reason_makes_it_selectable_again(login_as) -> None:
    stack, _ = login_as("Administrateur")
    created = stack.exit_reasons.create_exit_reason("Perte")
    stack.exit_reasons.deactivate_exit_reason(created.id)
    assert stack.exit_reasons.list_exit_reasons(include_inactive=False) == []

    stack.exit_reasons.activate_exit_reason(created.id)

    active_only = stack.exit_reasons.list_exit_reasons(include_inactive=False)
    assert {r.libelle for r in active_only} == {"Perte"}


def test_toggle_exit_reason_status_unknown_id_raises_not_found(login_as) -> None:
    stack, _ = login_as("Administrateur")

    try:
        stack.exit_reasons.deactivate_exit_reason(999999)
        assert False, "devait lever NotFoundError"
    except NotFoundError:
        pass


def test_get_exit_reason_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Consultation")

    try:
        stack.exit_reasons.get_exit_reason(1)
        assert False, "devait lever PermissionDeniedError"
    except PermissionDeniedError:
        pass
