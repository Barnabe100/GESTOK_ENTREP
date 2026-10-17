"""Tests de non-régression pour le correctif de concurrence P0-1
(``StockService.apply_movement`` — perte de mise à jour sous accès
concurrent, voir l'audit global de ce projet).

Chaque test de concurrence utilise deux threads réels, une base SQLite de
test sur fichier (jamais ``:memory:``, voir ``tests/conftest.py::test_settings``
et ses sous-fixtures), et une synchronisation explicite (``threading.Barrier``)
pour maximiser la fenêtre de recouvrement entre les deux opérations plutôt
que de dépendre du hasard de l'ordonnanceur — puis répète le scénario
plusieurs fois (articles distincts à chaque répétition) pour détecter une
perte de mise à jour qui ne se manifesterait pas à chaque tentative (le
défaut corrigé ici ne se reproduisait, avant correction, qu'environ une fois
sur quatre lors de l'audit)."""
from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest

from app.services.entries.entry_service import EntreeLigneInput
from app.services.exits.exit_service import SortieLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import AppError, ValidationError

CONCURRENCY_REPETITIONS = 20


def _make_sellable_article(stack, reference: str, stock_initial: Decimal) -> int:
    category = stack.categories.create_category(f"CAT-{reference}")
    article = stack.articles.create_article(
        reference, f"Article {reference}", category.id, "unité",
        Decimal("50"), Decimal("80"), Decimal("0"),
        stock_initial=stock_initial,
    )
    return article.id


def _concurrent_run(*targets) -> list[Exception]:
    """Lance chaque callable dans son propre thread, les démarre à l'unisson
    via une barrière, puis attend leur fin. Retourne les exceptions levées
    par chaque thread (dans l'ordre des ``targets``), ``None`` si aucune."""
    barrier = threading.Barrier(len(targets))
    results: list = [None] * len(targets)

    def _wrap(index: int, fn) -> None:
        try:
            barrier.wait(timeout=10)
        except threading.BrokenBarrierError:
            pass
        try:
            fn()
        except Exception as exc:  # pragma: no cover - diagnostic
            results[index] = exc

    threads = [threading.Thread(target=_wrap, args=(i, fn)) for i, fn in enumerate(targets)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    return results


# -- Test A : deux ventes concurrentes, stock suffisant ---------------------------------


def test_concurrent_sales_both_succeed_and_stock_matches_sum_of_movements(login_as) -> None:
    stack, _ = login_as("Administrateur")

    for i in range(CONCURRENCY_REPETITIONS):
        reference = f"ART-CONC-A-{i}"
        article_id = _make_sellable_article(stack, reference, Decimal("100"))
        sale1 = stack.sales.create_sale(date.today(), [VenteLigneInput(article_id, Decimal("30"), Decimal("80"))])
        sale2 = stack.sales.create_sale(date.today(), [VenteLigneInput(article_id, Decimal("20"), Decimal("80"))])

        errors = _concurrent_run(
            lambda sid=sale1.id: stack.sales.validate_sale(sid),
            lambda sid=sale2.id: stack.sales.validate_sale(sid),
        )

        assert errors == [None, None], f"itération {i} : {errors}"

        final_article = stack.articles.get_article(article_id)
        assert final_article.stock_actuel == Decimal("50"), f"itération {i}"

        movements = stack.movements.list_movements(article_id=article_id)
        vente_movements = [m for m in movements if m.type.value == "VENTE"]
        assert len(vente_movements) == 2, f"itération {i}"
        assert {m.quantite for m in vente_movements} == {Decimal("-30.000"), Decimal("-20.000")}, f"itération {i}"
        # Le stock final doit correspondre exactement à la somme des mouvements
        # réellement enregistrés (jamais une mise à jour perdue ni dupliquée).
        somme_mouvements = sum((m.quantite for m in vente_movements), Decimal("0"))
        assert Decimal("100") + somme_mouvements == final_article.stock_actuel, f"itération {i}"


# -- Test B : deux ventes concurrentes, stock insuffisant pour les deux -----------------


def test_concurrent_sales_exceeding_stock_only_one_succeeds_never_negative(login_as) -> None:
    stack, _ = login_as("Administrateur")

    for i in range(CONCURRENCY_REPETITIONS):
        reference = f"ART-CONC-B-{i}"
        article_id = _make_sellable_article(stack, reference, Decimal("40"))
        sale1 = stack.sales.create_sale(date.today(), [VenteLigneInput(article_id, Decimal("30"), Decimal("80"))])
        sale2 = stack.sales.create_sale(date.today(), [VenteLigneInput(article_id, Decimal("30"), Decimal("80"))])

        errors = _concurrent_run(
            lambda sid=sale1.id: stack.sales.validate_sale(sid),
            lambda sid=sale2.id: stack.sales.validate_sale(sid),
        )

        succeeded = [e for e in errors if e is None]
        failed = [e for e in errors if e is not None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"
        assert len(failed) == 1, f"itération {i} : {errors}"
        assert isinstance(failed[0], (ValidationError, AppError)), f"itération {i} : {failed[0]!r}"

        final_article = stack.articles.get_article(article_id)
        assert final_article.stock_actuel == Decimal("10"), f"itération {i}"
        assert final_article.stock_actuel >= 0, f"itération {i}"

        movements = stack.movements.list_movements(article_id=article_id)
        vente_movements = [m for m in movements if m.type.value == "VENTE"]
        assert len(vente_movements) == 1, f"itération {i} : la vente refusée ne doit laisser aucun mouvement"
        assert vente_movements[0].quantite == Decimal("-30.000")


# -- Test C : deux entrées concurrentes, CMUP ------------------------------------------


def test_concurrent_entries_cmup_matches_one_valid_sequential_order(login_as) -> None:
    """Deux entrées concurrentes, quantités et coûts différents : le stock
    final (addition exacte, jamais arrondie) doit toujours correspondre à la
    somme des deux quantités. Le CMUP final, lui, dépend de l'ordre réel
    d'application (l'arrondi intermédiaire après la première entrée n'est
    pas commutatif) — l'atomicité garantit seulement que le résultat
    correspond à l'UNE des deux exécutions séquentielles valides (double
    écrivain concurrent = exécution « comme si » l'une des deux venait
    avant l'autre, jamais un résultat hybride ou corrompu des deux)."""
    stack, _ = login_as("Administrateur")

    for i in range(CONCURRENCY_REPETITIONS):
        reference = f"ART-CONC-C-{i}"
        category = stack.categories.create_category(f"CAT-CONC-C-{i}")
        supplier = stack.suppliers.create_supplier(f"Fournisseur {i}")
        article = stack.articles.create_article(
            reference, f"Article {reference}", category.id, "unité",
            Decimal("50"), Decimal("80"), Decimal("0"),
            stock_initial=Decimal("100"),
        )
        # CMUP initial = prix d'achat par défaut appliqué au stock initial
        # (voir ArticleService.create_article) : calculons-le exactement
        # comme ArticleService le fait, sans dépendre de sa valeur interne.
        cmup_initial = stack.articles.get_article(article.id).cout_moyen_pondere

        entry1 = stack.entries.create_entry(
            supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("10"), Decimal("120"))]
        )
        entry2 = stack.entries.create_entry(
            supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("15"), Decimal("200"))]
        )

        errors = _concurrent_run(
            lambda eid=entry1.id: stack.entries.validate_entry(eid),
            lambda eid=entry2.id: stack.entries.validate_entry(eid),
        )
        assert errors == [None, None], f"itération {i} : {errors}"

        final_article = stack.articles.get_article(article.id)
        assert final_article.stock_actuel == Decimal("125"), f"itération {i}"

        # Référence séquentielle, dans les deux ordres possibles.
        from app.services.stock.stock_service import StockService

        cmup_order_1_then_2 = StockService.compute_new_cmup(Decimal("100"), cmup_initial, Decimal("10"), Decimal("120"))
        cmup_order_1_then_2 = StockService.compute_new_cmup(Decimal("110"), cmup_order_1_then_2, Decimal("15"), Decimal("200"))

        cmup_order_2_then_1 = StockService.compute_new_cmup(Decimal("100"), cmup_initial, Decimal("15"), Decimal("200"))
        cmup_order_2_then_1 = StockService.compute_new_cmup(Decimal("115"), cmup_order_2_then_1, Decimal("10"), Decimal("120"))

        assert final_article.cout_moyen_pondere in (cmup_order_1_then_2, cmup_order_2_then_1), (
            f"itération {i} : CMUP final {final_article.cout_moyen_pondere} ne correspond à "
            f"aucun ordre séquentiel valide ({cmup_order_1_then_2} ou {cmup_order_2_then_1})"
        )

        movements = stack.movements.list_movements(article_id=article.id)
        entree_movements = [m for m in movements if m.type.value == "ENTREE"]
        assert len(entree_movements) == 2, f"itération {i}"
        assert {m.quantite for m in entree_movements} == {Decimal("10.000"), Decimal("15.000")}


# -- Test D : atomicité multi-lignes (une ligne échoue -> tout est annulé) -------------


def test_two_line_sale_rolls_back_entirely_when_second_line_fails(login_as) -> None:
    stack, _ = login_as("Administrateur")
    article1_id = _make_sellable_article(stack, "ART-ATOM-D-1", Decimal("10"))
    article2_id = _make_sellable_article(stack, "ART-ATOM-D-2", Decimal("10"))

    sale = stack.sales.create_sale(
        date.today(),
        [
            VenteLigneInput(article1_id, Decimal("5"), Decimal("80")),  # réussirait seule : 10-5=5
            VenteLigneInput(article2_id, Decimal("15"), Decimal("80")),  # refusée seule : 10-15<0
        ],
    )

    with pytest.raises(ValidationError):
        stack.sales.validate_sale(sale.id)

    # Rien n'a été appliqué, y compris la ligne qui aurait réussi isolément
    # (seul l'AJUSTEMENT du stock initial, créé avant la vente, subsiste).
    assert stack.articles.get_article(article1_id).stock_actuel == Decimal("10")
    assert stack.articles.get_article(article2_id).stock_actuel == Decimal("10")
    vente_movements_1 = [m for m in stack.movements.list_movements(article_id=article1_id) if m.type.value == "VENTE"]
    vente_movements_2 = [m for m in stack.movements.list_movements(article_id=article2_id) if m.type.value == "VENTE"]
    assert vente_movements_1 == []
    assert vente_movements_2 == []

    sale_after = stack.sales.get_sale(sale.id)
    assert sale_after.statut.value == "BROUILLON"


# -- Test E : régression séquentielle (hors concurrence) ------------------------------


def test_sequential_regression_entry_exit_sale_location_return_and_negative_rejection(
    login_as,
) -> None:
    """Un enchaînement séquentiel ordinaire à travers les modules Entrées,
    Sorties, Ventes et Locations, plus le refus de stock négatif — exercé
    une seule fois, sans concurrence, pour confirmer que le correctif
    n'a rien changé au comportement du chemin normal (mono-thread)."""
    from app.services.rentals.location_service import LocationLigneInput
    from app.models.enums import ModeGestionArticle

    stack, _ = login_as("Administrateur")
    category = stack.categories.create_category("CAT-SEQ-E")
    supplier = stack.suppliers.create_supplier("Fournisseur Séquentiel")
    client = stack.clients.create_client("Client Séquentiel")
    article = stack.articles.create_article(
        "ART-SEQ-E", "Article séquentiel", category.id, "unité",
        Decimal("50"), Decimal("80"), Decimal("0"), stock_initial=Decimal("0"),
    )

    # Entrée : 0 -> 100, CMUP = 50.
    entry = stack.entries.create_entry(
        supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("100"), Decimal("50"))]
    )
    stack.entries.validate_entry(entry.id)
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("100")
    assert stack.articles.get_article(article.id).cout_moyen_pondere == Decimal("50.00")

    # Sortie : 100 -> 70.
    reason = stack.exit_reasons.create_exit_reason("Casse séquentielle")
    exit_doc = stack.exits.create_exit(
        reason.id, date.today(), [SortieLigneInput(article.id, Decimal("30"))]
    )
    stack.exits.validate_exit(exit_doc.id)
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("70")

    # Vente : 70 -> 50.
    sale = stack.sales.create_sale(date.today(), [VenteLigneInput(article.id, Decimal("20"), Decimal("80"))])
    stack.sales.validate_sale(sale.id)
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")

    # Refus de stock négatif (sortie de 51 sur un stock de 50).
    reason2 = stack.exit_reasons.create_exit_reason("Casse refusée")
    exit_refuse = stack.exits.create_exit(
        reason2.id, date.today(), [SortieLigneInput(article.id, Decimal("51"))]
    )
    with pytest.raises(ValidationError):
        stack.exits.validate_exit(exit_refuse.id)
    assert stack.articles.get_article(article.id).stock_actuel == Decimal("50")

    # Location : 50 -> 45 au départ, puis -> 50 au retour complet.
    rental_article_id = _make_sellable_article(stack, "ART-SEQ-E-LOC", Decimal("20"))
    stack.articles.switch_mode_gestion(rental_article_id, ModeGestionArticle.LOCATION)
    location = stack.rentals.create_location(
        date.today(), client.id, [LocationLigneInput(rental_article_id, Decimal("5"), tarif_jour=Decimal("100"))]
    )
    confirmed = stack.rentals.confirm_location(location.id)
    departed = stack.rentals.depart_location(confirmed.id, date.today())
    assert stack.articles.get_article(rental_article_id).stock_actuel == Decimal("15")

    returned = stack.rentals.return_location_line(
        departed.id, departed.lignes[0].id, date.today(), quantite_bon_etat=Decimal("5")
    )
    assert returned.statut.value == "RETOURNEE"
    assert stack.articles.get_article(rental_article_id).stock_actuel == Decimal("20")
