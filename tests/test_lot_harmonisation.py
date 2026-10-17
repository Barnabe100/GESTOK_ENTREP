"""Tests d'harmonisation (lot dédié) : invariants métier transversaux,
communs à plusieurs services, après la reconstruction des lots 1
(Locations), 2 (visibilité des mots de passe), 3 (récupération
administrateur), 5 (créances), 6 (export Excel) et 10 (correction
DataResetService).

Chaque test ici porte sur une interaction entre AU MOINS deux modules —
jamais la simple répétition d'un test déjà existant dans un fichier dédié
(``test_sale_service.py``, ``test_location_service.py``,
``test_data_reset_service.py``, ``test_account_recovery_service.py``,
``test_report_service.py``, etc.), dont la couverture a été vérifiée avant
d'écrire ce fichier pour éviter tout doublon inutile.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.db.seed import ROLE_PERMISSIONS_MATRIX
from app.models.enums import ModeGestionArticle, StatutLocation, StatutOperation, StatutPaiement, TypeMouvement
from app.services.rentals.location_service import LocationLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import ConflictError, PermissionDeniedError, ValidationError
from app.views.pages.receivables_page import ReceivablesPage


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Évite tout blocage sous pytest-qt offscreen : ``ReportsPage._export_to``/
    ``_export_xlsx_to`` affichent une vraie ``QMessageBox.information`` au
    succès (voir la leçon déjà documentée dans test_reports_page.py)."""
    monkeypatch.setattr("app.views.pages.reports_page.QMessageBox.information", lambda *a, **k: None)
    monkeypatch.setattr("app.views.pages.reports_page.QMessageBox.warning", lambda *a, **k: None)


def _make_category(stack, nom="Boissons"):
    return stack.categories.create_category(nom)


def _make_article(stack, reference="ART-0001", stock_initial=Decimal("0"), category_id=None, prix_vente=Decimal("150")):
    if category_id is None:
        category_id = _make_category(stack, f"Cat-{reference}").id
    return stack.articles.create_article(
        reference, "Article de test", category_id, "unité",
        Decimal("100"), prix_vente, Decimal("0"), stock_initial=stock_initial,
    )


def _make_rental_article(stack, reference="ART-LOC", stock_initial=Decimal("10"), tarif_jour=Decimal("500")):
    category = _make_category(stack, f"Cat-{reference}")
    article = stack.articles.create_article(
        reference, "Article de location", category.id, "unité",
        Decimal("1000"), Decimal("0"), Decimal("0"),
        stock_initial=stock_initial, tarif_location_jour=tarif_jour,
    )
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    return stack.articles.get_article(article.id)


# =====================================================================================
# 1. Brouillons et validations — invariant transversal à tous les documents
# =====================================================================================


def test_every_document_type_draft_has_zero_stock_impact(login_as) -> None:
    """Invariant commun à Entrées/Sorties/Ventes/Inventaires/Locations : un
    document en brouillon ne doit jamais générer de mouvement de stock ni
    modifier Article.stock_actuel — vérifié ici pour les cinq types dans un
    seul test, plutôt que cinq tests isolés déjà existants par service.
    ``stock_initial=0`` à la création des articles : un stock initial non
    nul génère lui-même un mouvement AJUSTEMENT (ArticleService), sans
    rapport avec l'invariant testé ici — jamais souhaitable de le mélanger
    au comptage."""
    from app.services.entries.entry_service import EntreeLigneInput
    from app.services.exits.exit_service import SortieLigneInput
    from app.services.inventory.inventory_service import InventaireLigneInput

    stack, _ = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur Harmonisation")
    motif = stack.exit_reasons.create_exit_reason("Motif Harmonisation")
    client = stack.clients.create_client("Client Harmonisation")
    article = _make_article(stack, stock_initial=Decimal("0"))
    rental_article = _make_rental_article(stack, stock_initial=Decimal("0"))

    stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))])
    stack.exits.create_exit(motif.id, date(2026, 1, 1), [SortieLigneInput(article.id, Decimal("5"))])
    stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])
    stack.inventory.create_inventory(date(2026, 1, 1), [InventaireLigneInput(article.id, Decimal("40"))])
    stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(rental_article.id, Decimal("2"))])

    assert stack.articles.get_article(article.id).stock_actuel == Decimal("0")
    assert stack.articles.get_article(rental_article.id).stock_actuel == Decimal("0")
    assert stack.movements.list_movements(article_id=article.id) == []
    assert stack.movements.list_movements(article_id=rental_article.id) == []


def test_sale_validation_applies_stock_effect_exactly_once(login_as) -> None:
    """La validation (seul point d'écriture du stock, voir SaleService) ne
    doit produire qu'un seul mouvement par ligne, même après plusieurs
    lectures ultérieures du document (get_sale ne doit jamais ré-appliquer
    d'effet métier) — invariant transversal lecture/écriture."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("5"), Decimal("150"))])

    stack.sales.validate_sale(sale.id)
    for _ in range(3):
        stack.sales.get_sale(sale.id)

    def _vente_movements():
        return [m for m in stack.movements.list_movements(article_id=article.id) if m.type == TypeMouvement.VENTE]

    assert len(_vente_movements()) == 1
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("45")

    with pytest.raises(ConflictError):
        stack.sales.validate_sale(sale.id)  # déjà validée : refusée, pas de second mouvement
    assert len(_vente_movements()) == 1


# =====================================================================================
# 2. Atomicité — une ligne en échec annule tout le document, pas seulement elle-même
# =====================================================================================


def test_sale_validation_failure_on_second_line_rolls_back_first_line_too(login_as) -> None:
    """Une vente à deux lignes dont la seconde dépasse le stock disponible
    doit voir l'INTÉGRALITÉ de la transaction annulée — y compris l'effet
    que la première ligne, valide isolément, aurait produit. Aucun test
    existant ne vérifie ce cas à deux lignes (chaque service ne teste
    jusqu'ici qu'un dépassement de stock à une seule ligne)."""
    stack, _ = login_as("Administrateur")
    category = _make_category(stack)
    article_1 = _make_article(stack, reference="ART-OK", stock_initial=Decimal("50"), category_id=category.id)
    article_2 = _make_article(stack, reference="ART-KO", stock_initial=Decimal("2"), category_id=category.id)

    sale = stack.sales.create_sale(
        date(2026, 1, 1),
        [
            VenteLigneInput(article_1.id, Decimal("10"), Decimal("150")),
            VenteLigneInput(article_2.id, Decimal("100"), Decimal("150")),  # dépasse largement le stock
        ],
    )

    with pytest.raises(ValidationError):
        stack.sales.validate_sale(sale.id)

    # La première ligne, pourtant valide isolément, n'a produit aucun effet
    # (seul le mouvement AJUSTEMENT du stock initial à la création subsiste,
    # sans rapport avec cette tentative de validation).
    assert stack.articles.get_article(article_1.id).stock_actuel == Decimal("50")
    assert stack.articles.get_article(article_2.id).stock_actuel == Decimal("2")
    assert [m for m in stack.movements.list_movements(article_id=article_1.id) if m.type == TypeMouvement.VENTE] == []
    assert [m for m in stack.movements.list_movements(article_id=article_2.id) if m.type == TypeMouvement.VENTE] == []
    assert stack.sales.get_sale(sale.id).statut == StatutOperation.BROUILLON


def test_location_depart_failure_on_second_line_rolls_back_first_line_too(login_as) -> None:
    """Même invariant que ci-dessus, pour une location à deux lignes au
    départ (LocationService.depart_location)."""
    stack, _ = login_as("Administrateur")
    article_ok = _make_rental_article(stack, reference="ART-LOC-OK", stock_initial=Decimal("20"))
    article_ko = _make_rental_article(stack, reference="ART-LOC-KO", stock_initial=Decimal("1"))
    client = stack.clients.create_client("Client Atomicité")

    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id,
        [LocationLigneInput(article_ok.id, Decimal("5")), LocationLigneInput(article_ko.id, Decimal("50"))],
    )
    confirmed = stack.rentals.confirm_location(location.id)

    with pytest.raises(ValidationError):
        stack.rentals.depart_location(confirmed.id, date(2026, 1, 1))

    assert stack.articles.get_article(article_ok.id).stock_actuel == Decimal("20")
    assert stack.articles.get_article(article_ko.id).stock_actuel == Decimal("1")
    assert [
        m for m in stack.movements.list_movements(article_id=article_ok.id)
        if m.type == TypeMouvement.LOCATION_SORTIE
    ] == []
    assert stack.rentals.get_location(location.id).statut == StatutLocation.CONFIRMEE


# =====================================================================================
# 3. Ventes et paiements — cohérence des montants sur une séquence de paiements
# =====================================================================================


def test_sequence_of_partial_payments_stays_consistent_at_every_step(login_as) -> None:
    """Après plusieurs paiements partiels successifs, à chaque étape :
    montant_paye == somme des Paiement enregistrés, reste_a_payer == total -
    montant_paye, et statut_paiement cohérent avec les deux — jamais
    vérifié ici sur une séquence de plus d'un paiement."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"), prix_vente=Decimal("1000"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("1000"))])
    validated = stack.sales.validate_sale(sale.id)
    assert validated.total == Decimal("1000")

    running_total = Decimal("0")
    for montant in (Decimal("200"), Decimal("300"), Decimal("500")):
        running_total += montant
        updated = stack.sales.record_payment(validated.id, montant)
        payments_sum = sum((p.montant for p in stack.sales.list_payments(validated.id)), Decimal("0"))

        assert updated.montant_paye == running_total == payments_sum
        assert updated.reste_a_payer == Decimal("1000") - running_total
        if running_total >= Decimal("1000"):
            assert updated.statut_paiement == StatutPaiement.PAYEE
        else:
            assert updated.statut_paiement == StatutPaiement.PARTIELLEMENT_PAYEE


def test_payment_never_exceeds_total_even_after_several_partial_payments(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"), prix_vente=Decimal("1000"))
    sale = stack.sales.create_sale(date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("1000"))])
    validated = stack.sales.validate_sale(sale.id)
    stack.sales.record_payment(validated.id, Decimal("900"))

    with pytest.raises(ValidationError):
        stack.sales.record_payment(validated.id, Decimal("200"))  # 900 + 200 > 1000

    reloaded = stack.sales.get_sale(validated.id)
    assert reloaded.montant_paye == Decimal("900")  # le paiement refusé n'a rien modifié


# =====================================================================================
# 4. Créances — cohérence ventes / paiements / filtre de la page
# =====================================================================================


def test_receivables_page_reflects_sale_through_full_payment_lifecycle(qtbot, login_as) -> None:
    """Scénario transversal complet SaleService -> ReceivablesPage, sur
    plusieurs étapes de paiement (les tests existants de
    test_receivables_page.py ne couvrent qu'un seul paiement par
    scénario) : non payée (visible, défaut) -> partiellement payée
    (visible, défaut) -> payée (masquée par défaut, visible via le filtre
    explicite) -> annulée (toujours absente, quel que soit le filtre)."""
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"), prix_vente=Decimal("1000"))
    client = stack.clients.create_client("Client Créances Harmonisation")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("1000"))], client_id=client.id
    )
    validated = stack.sales.validate_sale(sale.id)

    page = ReceivablesPage(stack.sales, stack.clients, stack.permissions)
    qtbot.addWidget(page)
    assert validated.numero in {page.table.item(r, 1).text() for r in range(page.table.rowCount())}

    stack.sales.record_payment(validated.id, Decimal("400"))
    page.refresh()
    assert validated.numero in {page.table.item(r, 1).text() for r in range(page.table.rowCount())}

    stack.sales.record_payment(validated.id, Decimal("600"))  # intégralement payée
    page.refresh()
    assert validated.numero not in {page.table.item(r, 1).text() for r in range(page.table.rowCount())}

    index = page.statut_paiement_combo.findData(None)  # « Toutes »
    page.statut_paiement_combo.setCurrentIndex(index)
    assert validated.numero in {page.table.item(r, 1).text() for r in range(page.table.rowCount())}


def test_cancelled_sale_never_appears_in_receivables_regardless_of_filter(qtbot, login_as) -> None:
    stack, _ = login_as("Administrateur")
    article = _make_article(stack, stock_initial=Decimal("50"))
    client = stack.clients.create_client("Client Annulée")
    sale = stack.sales.create_sale(
        date(2026, 1, 1), [VenteLigneInput(article.id, Decimal("1"), Decimal("150"))], client_id=client.id
    )
    validated = stack.sales.validate_sale(sale.id)
    cancelled = stack.sales.cancel_sale(validated.id, "Motif de test valide")

    page = ReceivablesPage(stack.sales, stack.clients, stack.permissions)
    qtbot.addWidget(page)

    for index in range(page.statut_paiement_combo.count()):
        page.statut_paiement_combo.setCurrentIndex(index)
        numeros = {page.table.item(r, 1).text() for r in range(page.table.rowCount())}
        assert cancelled.numero not in numeros


# =====================================================================================
# 5/6. Locations — cycle complet, mouvements génériques, et distinction caution/paiement
# =====================================================================================


def test_location_movements_appear_correctly_in_generic_movement_service(login_as) -> None:
    """LOCATION_SORTIE/LOCATION_RETOUR doivent apparaître dans
    MovementService.list_movements (page Mouvements générique) exactement
    comme tout autre type de mouvement — jamais vérifié jusqu'ici via ce
    service partagé (seul LocationService lui-même était testé)."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"))
    client = stack.clients.create_client("Client Mouvements")
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("3"))]
    )
    confirmed = stack.rentals.confirm_location(location.id)
    departed = stack.rentals.depart_location(confirmed.id, date(2026, 1, 1))
    stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("2"),
        quantite_immobilisee=Decimal("1"),
    )

    movements = stack.movements.list_movements(article_id=article.id)
    types = [m.type for m in movements]
    assert TypeMouvement.LOCATION_SORTIE in types
    assert TypeMouvement.LOCATION_RETOUR in types

    sortie = next(m for m in movements if m.type == TypeMouvement.LOCATION_SORTIE)
    retour = next(m for m in movements if m.type == TypeMouvement.LOCATION_RETOUR)
    assert sortie.quantite == Decimal("-3")
    assert retour.quantite == Decimal("2")  # seule la quantité en bon état est remise en stock
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("9")  # 10 - 3 + 2


def test_full_location_lifecycle_billing_and_stock_stay_consistent(login_as) -> None:
    """Cycle complet (création -> confirmation -> départ -> deux retours
    partiels) : vérifie simultanément la cohérence du stock, des mouvements
    et de la facturation cumulée — invariant transversal non couvert par un
    seul test existant (qui ne testent chacun qu'un sous-ensemble)."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, stock_initial=Decimal("10"), tarif_jour=Decimal("200"))
    client = stack.clients.create_client("Client Cycle Complet")

    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("4"))]
    )
    confirmed = stack.rentals.confirm_location(location.id)
    departed = stack.rentals.depart_location(confirmed.id, date(2026, 1, 1))
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("6")

    ligne_id = departed.lignes[0].id
    first_return = stack.rentals.return_location_line(
        departed.id, ligne_id, date(2026, 1, 3), quantite_bon_etat=Decimal("2")
    )
    # 2 jours (1 -> 3 janvier) * 200 * 2 unités = 800
    assert first_return.lignes[0].montant_facture_total == Decimal("800")
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("8")
    assert first_return.statut == StatutLocation.EN_COURS

    final_return = stack.rentals.return_location_line(
        first_return.id, ligne_id, date(2026, 1, 5), quantite_bon_etat=Decimal("2")
    )
    # + 4 jours (1 -> 5 janvier) * 200 * 2 unités = 1600 -> total 2400
    assert final_return.lignes[0].montant_facture_total == Decimal("2400")
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("10")
    assert final_return.statut == StatutLocation.RETOURNEE
    assert final_return.montant_total_facture == Decimal("2400")

    paid = stack.rentals.record_payment(final_return.id, Decimal("2400"))
    assert paid.reste_a_payer == Decimal("0")
    assert paid.statut == StatutLocation.RETOURNEE  # le paiement ne change jamais le statut de cycle de vie


def test_caution_and_rental_payment_ledgers_never_interfere(login_as) -> None:
    """Invariant transversal non encore testé : enregistrer un paiement de
    location (LocationPaiement) ne doit jamais affecter caution_rendue, et
    restituer une caution ne doit jamais affecter montant_paye — deux
    journaux totalement indépendants malgré un point d'entrée UI commun
    (LocationDetailDialog)."""
    stack, _ = login_as("Administrateur")
    article = _make_rental_article(stack, tarif_jour=Decimal("300"))
    client = stack.clients.create_client("Client Caution Indépendante")
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))]
    )
    stack.rentals.set_caution_montant(location.id, Decimal("5000"))
    confirmed = stack.rentals.confirm_location(location.id)
    departed = stack.rentals.depart_location(confirmed.id, date(2026, 1, 1))
    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("1")
    )
    assert returned.montant_total_facture == Decimal("300")

    after_payment = stack.rentals.record_payment(returned.id, Decimal("300"))
    assert after_payment.caution_montant == Decimal("5000")
    assert after_payment.caution_rendue == Decimal("0")

    after_caution_return = stack.rentals.record_caution_return(returned.id, Decimal("5000"))
    assert after_caution_return.montant_paye == Decimal("300")
    assert after_caution_return.reste_a_payer == Decimal("0")


def test_caution_return_history_never_exceeds_montant_across_multiple_steps(login_as) -> None:
    """Trois restitutions partielles successives : la somme cumulée ne doit
    jamais dépasser caution_montant, et la troisième tentative (qui le
    ferait) doit être refusée sans rien modifier."""
    stack, _ = login_as("Administrateur")
    client = stack.clients.create_client("Client Caution Multi")
    article = _make_rental_article(stack)
    location = stack.rentals.create_location(date(2026, 1, 1), client.id, [LocationLigneInput(article.id, Decimal("1"))])
    stack.rentals.set_caution_montant(location.id, Decimal("9000"))

    stack.rentals.record_caution_return(location.id, Decimal("3000"))
    after_second = stack.rentals.record_caution_return(location.id, Decimal("4000"))
    assert after_second.caution_rendue == Decimal("7000")

    with pytest.raises(ValidationError):
        stack.rentals.record_caution_return(location.id, Decimal("3000"))  # 7000 + 3000 > 9000

    final = stack.rentals.get_location(location.id)
    assert final.caution_rendue == Decimal("7000")  # la tentative refusée n'a rien modifié


# =====================================================================================
# 7. Permissions — la matrice déclarée (seed.py) doit correspondre au comportement réel
# =====================================================================================


@pytest.mark.parametrize("role_name", list(ROLE_PERMISSIONS_MATRIX.keys()))
def test_granted_permissions_match_declared_matrix_exactly(login_as, role_name) -> None:
    """Pour chaque rôle, l'ensemble des permissions réellement accordées
    (PermissionService.has_permission) doit correspondre EXACTEMENT à
    ROLE_PERMISSIONS_MATRIX[role] — un test unique couvrant la totalité des
    permissions de tous les lots (1, 3, 6 compris), plutôt qu'un rôle/
    permission vérifié isolément dans chaque fichier de test de service."""
    from app.db.seed import PERMISSIONS

    stack, _ = login_as(role_name)
    all_codes = [code for code, _, _ in PERMISSIONS]
    expected = set(ROLE_PERMISSIONS_MATRIX[role_name])

    granted = {code for code in all_codes if stack.permissions.has_permission(code)}
    assert granted == expected


def test_location_permissions_are_denied_for_consultation_role(login_as) -> None:
    """Confort : un appel réel (pas seulement has_permission) est refusé
    pour chacune des actions d'écriture Locations, pour le rôle
    Consultation — à l'identique de ce qui est déjà fait pour SALE_* dans
    test_sale_service.py, étendu ici à LOCATION_*."""
    stack, _ = login_as("Consultation")

    with pytest.raises(PermissionDeniedError):
        stack.rentals.create_location(date(2026, 1, 1), 1, [])
    with pytest.raises(PermissionDeniedError):
        stack.rentals.confirm_location(1)
    with pytest.raises(PermissionDeniedError):
        stack.rentals.depart_location(1, date(2026, 1, 1))
    with pytest.raises(PermissionDeniedError):
        stack.rentals.cancel_location(1, "Motif quelconque")


# =====================================================================================
# 8. Réinitialisation — scénario combiné de tous les lots reconstruits
# =====================================================================================


def test_full_reset_with_every_lot_data_combined_succeeds_and_preserves_recovery_code(login_as) -> None:
    """Scénario combiné unique : données ordinaires (vente/entrée/sortie/
    inventaire) + Locations (avec retour et caution) + un code de
    récupération administrateur généré (lot 3) — la réinitialisation doit
    réussir sans violation de clé étrangère, et le code de récupération
    (table admin_recovery_codes, jamais mentionnée dans _DELETE_ORDER ni
    _PRESERVED_MODELS) doit survivre, à l'identique du mot de passe de
    l'utilisateur qui le porte."""
    from app.models.account_recovery import AdminRecoveryCode
    from app.db.session import session_scope
    from app.config.settings import get_settings
    from app.services.entries.entry_service import EntreeLigneInput

    stack, admin_user = login_as("Administrateur")
    supplier = stack.suppliers.create_supplier("Fournisseur Combiné")
    article = _make_article(stack, stock_initial=Decimal("20"))
    entry = stack.entries.create_entry(supplier.id, date(2026, 1, 1), [EntreeLigneInput(article.id, Decimal("5"), Decimal("100"))])
    stack.entries.validate_entry(entry.id)

    rental_article = _make_rental_article(stack, tarif_jour=Decimal("500"))
    client = stack.clients.create_client("Client Combiné")
    location = stack.rentals.create_location(
        date(2026, 1, 1), client.id, [LocationLigneInput(rental_article.id, Decimal("1"))]
    )
    stack.rentals.set_caution_montant(location.id, Decimal("2000"))
    confirmed = stack.rentals.confirm_location(location.id)
    departed = stack.rentals.depart_location(confirmed.id, date(2026, 1, 1))
    stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date(2026, 1, 2), quantite_bon_etat=Decimal("1")
    )

    stack.account_recovery.generate_code()
    with session_scope(get_settings()) as session:
        recovery_count_before = session.query(AdminRecoveryCode).count()
    assert recovery_count_before == 1

    result = stack.data_reset.reset_business_data()

    assert result.success is True
    with session_scope(get_settings()) as session:
        recovery_count_after = session.query(AdminRecoveryCode).count()
    assert recovery_count_after == 1  # jamais touchée par la réinitialisation des données métier


# =====================================================================================
# 10. Export Excel — cohérence avec le rapport affiché et le CSV, sans régression
# =====================================================================================


def test_excel_and_csv_exports_of_the_same_report_agree_with_the_displayed_table(qtbot, login_as, tmp_path) -> None:
    """Exporte le même rapport (État du stock) en CSV et en Excel à partir
    du même état affiché, et vérifie que les trois sources (tableau Qt,
    CSV, Excel) portent la même information — jamais comparé directement
    entre eux jusqu'ici (chaque format est testé isolément)."""
    import csv as csv_module

    import openpyxl

    from app.views.pages.reports_page import ReportsPage

    stack, _ = login_as("Administrateur")
    _make_article(stack, reference="ART-EXPORT", stock_initial=Decimal("12"), prix_vente=Decimal("777"))

    page = ReportsPage(stack.reports, stack.categories, stack.articles, stack.exit_reasons, stack.permissions)
    qtbot.addWidget(page)

    table_reference = page.table.item(0, 0).text()
    table_stock = page.table.item(0, 5).text()

    csv_path = tmp_path / "export.csv"
    xlsx_path = tmp_path / "export.xlsx"
    assert page._export_to(str(csv_path)) is True
    assert page._export_xlsx_to(str(xlsx_path)) is True

    with open(csv_path, encoding="utf-8-sig") as handle:
        rows = list(csv_module.reader(handle, delimiter=";"))
    assert rows[1][0] == table_reference
    assert rows[1][5] == table_stock

    workbook = openpyxl.load_workbook(xlsx_path)
    sheet = workbook.active
    assert sheet.cell(row=2, column=1).value == table_reference
    assert float(sheet.cell(row=2, column=6).value) == float(table_stock.replace(" ", "").replace(",", "."))
