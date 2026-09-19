"""Tests de ``AuditService`` : permissions, licence, filtres, jointure
externe sur un ``user_id`` nul, et garantie de lecture seule (Lot B —
Journal d'audit consultable)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.enums import EditionLicence
from app.services.licensing.license_payload import DEFAULT_FEATURES_BY_EDITION
from app.utils.exceptions import LicenseError, PermissionDeniedError


# -- permissions --------------------------------------------------------------------


def test_list_audits_as_administrateur_succeeds(login_as) -> None:
    stack, _ = login_as("Administrateur")

    audits = stack.audit.list_audits()

    # Le login de l'Administrateur lui-même a déjà écrit une entrée LOGIN.
    assert any(a.action == "LOGIN" for a in audits)


def test_list_audits_denied_for_vendeur(login_as) -> None:
    stack, _ = login_as("Vendeur")

    with pytest.raises(PermissionDeniedError):
        stack.audit.list_audits()


def test_list_audits_denied_for_gestionnaire_stock(login_as) -> None:
    stack, _ = login_as("Gestionnaire de stock")

    with pytest.raises(PermissionDeniedError):
        stack.audit.list_audits()


def test_list_entites_denied_for_role_without_audit_view(login_as) -> None:
    stack, _ = login_as("Consultation")

    with pytest.raises(PermissionDeniedError):
        stack.audit.list_entites()


# -- licence ---------------------------------------------------------------------------


def test_list_audits_allowed_with_full_access_license(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.permissions.has_permission("AUDIT_VIEW") is True
    stack.audit.list_audits()  # ne doit pas lever


def test_list_audits_blocked_without_audit_feature_even_for_administrateur(
    login_as, license_envelope_factory
) -> None:
    """Licence DEMO (sans FEATURE_AUDIT, voir DEFAULT_FEATURES_BY_EDITION) :
    bloque l'accès même pour un Administrateur — même principe déjà vérifié
    pour le Dashboard (§8 de la phase Licences), jamais de contournement du
    FeatureGate."""
    stack, _ = login_as("Administrateur")
    envelope = license_envelope_factory(
        edition="DEMO", features=sorted(DEFAULT_FEATURES_BY_EDITION[EditionLicence.DEMO])
    )
    stack.licenses.activate_license(envelope)

    assert stack.permissions.has_permission("AUDIT_VIEW") is False
    with pytest.raises(LicenseError):
        stack.audit.list_audits()


# -- contenu / user_id nul (LOGIN échoué avec identifiant inconnu) ---------------------


def test_audit_with_null_user_id_is_included_via_left_join(login_as) -> None:
    """§ contrainte impérative : LEFT JOIN, jamais INNER JOIN — sinon les
    entrées avec ``user_id`` nul (ex. LOGIN avec identifiant inconnu)
    disparaîtraient silencieusement du journal consultable."""
    stack, _ = login_as("Administrateur")
    with pytest.raises(Exception):
        stack.auth.login("identifiant_totalement_inconnu", "peu importe")

    audits = stack.audit.list_audits(term="identifiant_totalement_inconnu")

    unknown_login = next(a for a in audits if a.action == "LOGIN" and a.user_id is None)
    assert unknown_login.username is None
    assert "identifiant_totalement_inconnu" in (unknown_login.details or "")


# -- filtres --------------------------------------------------------------------------


def _make_article(stack, reference="ART-1"):
    category = stack.categories.create_category(f"Cat-{reference}")
    return stack.articles.create_article(
        reference, "Article de test", category.id, "unité", Decimal("100"), Decimal("150"), Decimal("0"),
    )


def test_filtered_by_period(login_as) -> None:
    stack, _ = login_as("Administrateur")
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    assert len(stack.audit.list_audits(date_from=today, date_to=today, term="LOGIN")) >= 1
    assert stack.audit.list_audits(date_from=tomorrow, date_to=tomorrow, term="LOGIN") == []
    assert stack.audit.list_audits(date_from=yesterday, date_to=yesterday, term="LOGIN") == []


def test_filtered_by_entite(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)

    audits_articles = stack.audit.list_audits(entite="articles")
    audits_clients = stack.audit.list_audits(entite="clients")

    assert len(audits_articles) == 1
    assert audits_articles[0].action == "ARTICLE_CREATE"
    assert audits_clients == []


def test_search_term_matches_username(login_as) -> None:
    stack, current_user = login_as("Administrateur")

    audits = stack.audit.list_audits(term=current_user.username)
    assert any(a.username == current_user.username for a in audits)

    no_match = stack.audit.list_audits(term="terme-totalement-inexistant-xyz")
    assert no_match == []


def test_search_term_matches_action(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)

    audits = stack.audit.list_audits(term="ARTICLE_CREATE")

    assert any(a.action == "ARTICLE_CREATE" for a in audits)


def test_combined_filters(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)
    today = date.today()

    audits = stack.audit.list_audits(term="ARTICLE_CREATE", entite="articles", date_from=today, date_to=today)

    assert len(audits) == 1


def test_no_results_returns_empty_list(login_as) -> None:
    stack, _ = login_as("Administrateur")

    assert stack.audit.list_audits(entite="entite-inexistante") == []


def test_list_entites_returns_distinct_values_actually_present(login_as) -> None:
    stack, _ = login_as("Administrateur")
    _make_article(stack)

    entites = stack.audit.list_entites()

    assert "auth" in entites  # écrit par le login effectué ci-dessus
    assert "articles" in entites
    assert len(entites) == len(set(entites))  # pas de doublon


# -- lecture seule ----------------------------------------------------------------------


def test_audit_service_never_writes_and_leaves_count_unchanged(login_as) -> None:
    from app.db.session import session_scope
    from app.models.audit import AuditLog

    stack, _ = login_as("Administrateur")
    with session_scope(None) as session:
        count_before = session.query(AuditLog).count()

    stack.audit.list_audits()
    stack.audit.list_audits(term="LOGIN", entite="auth")
    stack.audit.list_entites()

    with session_scope(None) as session:
        count_after = session.query(AuditLog).count()

    assert count_after == count_before


def test_audit_service_exposes_no_mutation_methods() -> None:
    from app.services.audit.audit_service import AuditService

    for forbidden in ("create_audit", "update_audit", "delete_audit", "purge", "archive"):
        assert not hasattr(AuditService, forbidden)
