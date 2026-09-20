from datetime import date
from decimal import Decimal

import pytest

from app.config.settings import get_settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.models.rbac import Permission, Role
from app.models.user import User
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import PermissionDeniedError, ValidationError


def _seed_full_business_data(stack):
    """Peuple articles/catégories/fournisseurs/clients/entrées/sorties/
    ventes (+paiement)/inventaires/mouvements — un jeu de données de test
    complet à réinitialiser."""
    from app.services.entries.entry_service import EntreeLigneInput
    from app.services.exits.exit_service import SortieLigneInput
    from app.services.inventory.inventory_service import InventaireLigneInput

    category = stack.categories.create_category("Boissons")
    supplier = stack.suppliers.create_supplier("Fournisseur Test")
    motif = stack.exit_reasons.create_exit_reason("Casse")
    client = stack.clients.create_client("Client Test")
    article = stack.articles.create_article(
        "ART-RESET", "Article de test", category.id, "unité",
        Decimal("100"), Decimal("150"), Decimal("0"), stock_initial=Decimal("10"),
    )

    entry = stack.entries.create_entry(
        supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("10"), Decimal("100"))]
    )
    stack.entries.validate_entry(entry.id)

    exit_doc = stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("2"))])
    stack.exits.validate_exit(exit_doc.id)

    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("2"), Decimal("150"))], client_id=client.id
    )
    validated_sale = stack.sales.validate_sale(sale.id, Decimal("100"))
    stack.sales.record_payment(validated_sale.id, Decimal("50"))

    inventory = stack.inventory.create_inventory(
        date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("5"))]
    )
    stack.inventory.validate_inventory(inventory.id)

    return {"category": category, "supplier": supplier, "motif": motif, "client": client, "article": article}


def _business_table_counts() -> dict[str, int]:
    from app.models.catalog import Article, Category, ExitReason, Supplier
    from app.models.client import Client
    from app.models.documents import Entree, EntreeLigne, Sortie, SortieLigne, Vente, VenteLigne
    from app.models.inventory import Inventaire, InventaireLigne
    from app.models.movement import MouvementStock
    from app.models.payment import Paiement

    models = {
        "articles": Article, "categories": Category, "fournisseurs": Supplier, "motifs_sortie": ExitReason,
        "clients": Client, "entrees": Entree, "entree_lignes": EntreeLigne, "sorties": Sortie,
        "sortie_lignes": SortieLigne, "ventes": Vente, "vente_lignes": VenteLigne,
        "inventaires": Inventaire, "inventaire_lignes": InventaireLigne,
        "mouvements_stock": MouvementStock, "paiements": Paiement,
    }
    with session_scope(get_settings()) as session:
        return {label: session.query(model).count() for label, model in models.items()}


# -- permissions ---------------------------------------------------------------------


def test_only_administrateur_has_reset_permission(login_as) -> None:
    admin_stack, _ = login_as("Administrateur")
    assert admin_stack.permissions.has_permission("SYSTEM_RESET_BUSINESS_DATA") is True

    for role_name in ("Gestionnaire de stock", "Vendeur", "Consultation"):
        stack, _ = login_as(role_name)
        assert stack.permissions.has_permission("SYSTEM_RESET_BUSINESS_DATA") is False


def test_reset_denied_without_permission(login_as) -> None:
    stack, _ = login_as("Vendeur")
    with pytest.raises(PermissionDeniedError):
        stack.data_reset.reset_business_data()


def test_reset_denied_for_every_non_administrateur_role(login_as) -> None:
    """CAS 9 (audit final avant commit) : un appel réel à
    reset_business_data() doit être refusé pour chacun des trois rôles non
    administrateur — pas seulement vérifié via has_permission()."""
    for role_name in ("Gestionnaire de stock", "Vendeur", "Consultation"):
        stack, _ = login_as(role_name)
        with pytest.raises(PermissionDeniedError):
            stack.data_reset.reset_business_data()


# -- réinitialisation réussie ----------------------------------------------------------


def test_reset_deletes_all_business_data(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)
    assert sum(_business_table_counts().values()) > 0

    result = stack.data_reset.reset_business_data()

    assert result.success is True
    counts_after = _business_table_counts()
    assert sum(counts_after.values()) == 0


def test_reset_reports_deleted_counts_per_table(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)

    result = stack.data_reset.reset_business_data()

    assert result.deleted_counts["articles"] == 1
    assert result.deleted_counts["clients"] == 1
    assert result.deleted_counts["ventes"] == 1
    # 1 paiement initial (à la validation) + 1 paiement ultérieur.
    assert result.deleted_counts["paiements"] == 2
    assert result.deleted_counts["mouvements_stock"] > 0


def test_reset_creates_and_reports_security_backup(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)

    result = stack.data_reset.reset_business_data()

    assert result.backup_path is not None
    assert result.backup_path.exists()


def test_reset_preserves_users_roles_permissions(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)

    with session_scope(get_settings()) as session:
        users_before = session.query(User).count()
        roles_before = session.query(Role).count()
        permissions_before = session.query(Permission).count()

    stack.data_reset.reset_business_data()

    with session_scope(get_settings()) as session:
        assert session.query(User).count() == users_before
        assert session.query(Role).count() == roles_before
        assert session.query(Permission).count() == permissions_before


def test_administrateur_can_still_authenticate_after_reset(login_as) -> None:
    """Le compte connecté avant la réinitialisation (même mot de passe)
    doit pouvoir se reconnecter après — la table ``users`` et les hachages
    de mot de passe ne sont jamais touchés par le reset."""
    from tests.conftest import DEFAULT_TEST_PASSWORD

    stack, current_user = login_as("Administrateur")
    _seed_full_business_data(stack)
    stack.data_reset.reset_business_data()

    relogged_in = stack.auth.login(current_user.username, DEFAULT_TEST_PASSWORD)
    assert relogged_in.username == current_user.username


def test_reset_preserves_company_settings_and_logo(login_as) -> None:
    stack, _ = login_as("Administrateur")
    stack.parameters.update_config(nom="Ma Boutique", adresse="123 rue Test", telephone=None, email=None, devise="EUR")
    _seed_full_business_data(stack)

    stack.data_reset.reset_business_data()

    config = stack.parameters.get_config()
    assert config.nom == "Ma Boutique"
    assert config.devise == "EUR"


def test_reset_preserves_audit_log(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)

    with session_scope(get_settings()) as session:
        audit_count_before = session.query(AuditLog).count()
    assert audit_count_before > 0

    stack.data_reset.reset_business_data()

    with session_scope(get_settings()) as session:
        audit_count_after = session.query(AuditLog).count()
    # Le journal d'audit n'a jamais été vidé, et un nouvel événement de
    # réinitialisation s'y est ajouté.
    assert audit_count_after > audit_count_before


def test_reset_creates_success_audit_event(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)

    stack.data_reset.reset_business_data()

    with session_scope(get_settings()) as session:
        entries = session.query(AuditLog).filter_by(action="BUSINESS_DATA_RESET_SUCCESS").all()
    assert len(entries) == 1
    assert entries[0].resultat == ResultatAudit.SUCCES
    assert entries[0].entite == "systeme"


def test_dashboard_is_empty_after_reset(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)

    stack.data_reset.reset_business_data()

    kpis = stack.dashboard.get_stock_kpis()
    assert kpis.total_quantity == Decimal("0")
    assert kpis.total_value == Decimal("0")


# -- échec de la sauvegarde préalable -> aucune suppression ---------------------------


def test_reset_aborted_when_backup_fails(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)
    counts_before = _business_table_counts()
    assert sum(counts_before.values()) > 0

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.backups.backup_engine.create_backup_file",
            lambda *a, **k: (_ for _ in ()).throw(OSError("disque plein (simulé)")),
        )
        with pytest.raises(ValidationError):
            stack.data_reset.reset_business_data()

    counts_after = _business_table_counts()
    assert counts_after == counts_before  # rien n'a été supprimé


def test_backup_failure_is_audited_as_failure(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _seed_full_business_data(stack)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.backups.backup_engine.create_backup_file",
            lambda *a, **k: (_ for _ in ()).throw(OSError("disque plein (simulé)")),
        )
        with pytest.raises(ValidationError):
            stack.data_reset.reset_business_data()

    with session_scope(get_settings()) as session:
        entries = session.query(AuditLog).filter_by(action="BUSINESS_DATA_RESET_FAILURE").all()
    assert len(entries) == 1
    assert entries[0].resultat == ResultatAudit.ECHEC


def test_reset_on_empty_database_succeeds_with_zero_counts(login_as) -> None:
    """Un client qui réinitialise sans jamais avoir saisi de données métier
    ne doit pas provoquer d'erreur — toutes les suppressions portent
    simplement sur zéro ligne."""
    stack, _ = login_as("Administrateur")

    result = stack.data_reset.reset_business_data()

    assert result.success is True
    assert all(count == 0 for count in result.deleted_counts.values())
