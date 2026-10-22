"""Lot C (audit de concurrence PostgreSQL) : non-régression pour le défaut
de double application d'une même validation sous accès concurrent.

Découverte pendant cet audit (voir le rapport de ce lot) : chaque
transition de cycle de vie des documents métier (``validate_exit``,
``validate_entry``, ``validate_sale``, ``validate_inventory``,
``depart_location``, ``return_location_line``) protégeait historiquement
son unicité par une simple lecture ORM suivie d'un test Python
(``if doc.statut != X: raise ConflictError``) — sous deux sessions
réellement concurrentes, rien n'empêchait les deux appels de lire le même
statut avant que l'un des deux n'écrive, appliquant deux fois le même
mouvement de stock. Confirmé empiriquement, symétriquement sur SQLite et
PostgreSQL 16.15 (14/15 et 12/15 répétitions sur un script jetable, avant
correctif).

Corrigé par ``app.utils.atomic_transition.apply_atomic_status_transition``
— une mise à jour SQL conditionnelle sur le statut du document, jamais une
lecture-puis-écriture Python — appliquée dans chacun des services
concernés, selon le même principe que ``StockService.apply_movement``
pour ``Article.stock_actuel`` (voir le rapport de ce lot pour le détail).

Complète ``tests/test_stock_service_concurrency.py`` (qui teste deux
documents DIFFÉRENTS sur le même article, scénario déjà protégé avant ce
lot) en testant ici la validation concurrente d'un MÊME document — le
scénario qui révélait le défaut. Voir
``tests/test_document_validation_concurrency_postgresql.py`` pour les
mêmes scénarios contre un serveur PostgreSQL 16.15 réel."""
from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

from app.models.enums import ModeGestionArticle
from app.services.entries.entry_service import EntreeLigneInput
from app.services.exits.exit_service import SortieLigneInput
from app.services.inventory.inventory_service import InventaireLigneInput
from app.services.rentals.location_service import LocationLigneInput
from app.services.sales.sale_service import VenteLigneInput
from app.utils.exceptions import AppError

CONCURRENCY_REPETITIONS = 8


def _concurrent_run(*targets) -> list:
    """Voir tests/test_stock_service_concurrency.py::_concurrent_run — même
    principe (barrière explicite, jamais une attente temporelle)."""
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


def _make_sellable_article(stack, reference: str, stock_initial: Decimal):
    category = stack.categories.create_category(f"CAT-{reference}")
    return stack.articles.create_article(
        reference, f"Article {reference}", category.id, "unité",
        Decimal("50"), Decimal("80"), Decimal("0"), stock_initial=stock_initial,
    )


# -- Sorties --------------------------------------------------------------------------


def test_concurrent_double_validation_of_same_exit_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_sellable_article(stack, f"ART-DVC-EXIT-{i}", Decimal("100"))
        reason = stack.exit_reasons.create_exit_reason(f"Motif DVC {i}")
        exit_doc = stack.exits.create_exit(reason.id, date.today(), [SortieLigneInput(article.id, Decimal("10"))])

        errors = _concurrent_run(
            lambda eid=exit_doc.id: stack.exits.validate_exit(eid),
            lambda eid=exit_doc.id: stack.exits.validate_exit(eid),
        )
        succeeded = [e for e in errors if e is None]
        failed = [e for e in errors if e is not None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"
        assert len(failed) == 1 and isinstance(failed[0], AppError), f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        sortie_movements = [m for m in movements if m.type.value == "SORTIE"]
        assert len(sortie_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("90"), f"itération {i}"


# -- Entrées --------------------------------------------------------------------------


def test_concurrent_double_validation_of_same_entry_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    for i in range(CONCURRENCY_REPETITIONS):
        category = stack.categories.create_category(f"CAT-DVC-ENTRY-{i}")
        supplier = stack.suppliers.create_supplier(f"Fournisseur DVC {i}")
        article = stack.articles.create_article(
            f"ART-DVC-ENTRY-{i}", f"Article {i}", category.id, "unité",
            Decimal("50"), Decimal("80"), Decimal("0"), stock_initial=Decimal("0"),
        )
        entry = stack.entries.create_entry(
            supplier.id, date.today(), [EntreeLigneInput(article.id, Decimal("10"), Decimal("50"))]
        )

        errors = _concurrent_run(
            lambda eid=entry.id: stack.entries.validate_entry(eid),
            lambda eid=entry.id: stack.entries.validate_entry(eid),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        entree_movements = [m for m in movements if m.type.value == "ENTREE"]
        assert len(entree_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("10"), f"itération {i}"


# -- Ventes ---------------------------------------------------------------------------


def test_concurrent_double_validation_of_same_sale_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_sellable_article(stack, f"ART-DVC-SALE-{i}", Decimal("100"))
        sale = stack.sales.create_sale(date.today(), [VenteLigneInput(article.id, Decimal("10"), Decimal("80"))])

        errors = _concurrent_run(
            lambda sid=sale.id: stack.sales.validate_sale(sid),
            lambda sid=sale.id: stack.sales.validate_sale(sid),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        vente_movements = [m for m in movements if m.type.value == "VENTE"]
        assert len(vente_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("90"), f"itération {i}"


# -- Inventaires ------------------------------------------------------------------------


def test_concurrent_double_validation_of_same_inventory_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_sellable_article(stack, f"ART-DVC-INV-{i}", Decimal("100"))
        # Écart non nul (stock_physique != stock_theorique capturé à la
        # création) : sans écart, aucun mouvement n'est généré (voir
        # InventoryService.validate_inventory), ce qui ne testerait rien.
        inventory = stack.inventory.create_inventory(
            date.today(), [InventaireLigneInput(article.id, Decimal("120"))]
        )

        errors = _concurrent_run(
            lambda iid=inventory.id: stack.inventory.validate_inventory(iid),
            lambda iid=inventory.id: stack.inventory.validate_inventory(iid),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        # Exclut l'AJUSTEMENT initial généré par create_article(stock_initial=...)
        # (sans rapport avec cet inventaire) : seul le mouvement rattaché à
        # ce numéro d'inventaire est significatif ici.
        movements = stack.movements.list_movements(article_id=article.id)
        ajustement_movements = [
            m for m in movements if m.type.value == "AJUSTEMENT" and m.reference_operation == inventory.numero
        ]
        assert len(ajustement_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("120"), f"itération {i}"


# -- Locations : départ -----------------------------------------------------------------


def _make_rental_article(stack, reference: str, stock_initial: Decimal):
    article = _make_sellable_article(stack, reference, stock_initial)
    stack.articles.switch_mode_gestion(article.id, ModeGestionArticle.LOCATION)
    return article


def test_concurrent_double_departure_of_same_location_is_rejected(login_as) -> None:
    stack, _ = login_as("Administrateur")
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_rental_article(stack, f"ART-DVC-DEP-{i}", Decimal("20"))
        client = stack.clients.create_client(f"Client DVC {i}")
        location = stack.rentals.create_location(
            date.today(), client.id, [LocationLigneInput(article.id, Decimal("5"), tarif_jour=Decimal("100"))]
        )
        confirmed = stack.rentals.confirm_location(location.id)

        errors = _concurrent_run(
            lambda lid=confirmed.id: stack.rentals.depart_location(lid, date.today()),
            lambda lid=confirmed.id: stack.rentals.depart_location(lid, date.today()),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        depart_movements = [m for m in movements if m.type.value == "LOCATION_SORTIE"]
        assert len(depart_movements) == 1, f"itération {i}"
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("15"), f"itération {i}"


# -- Locations : retour (même ligne, double retour concurrent) -------------------------


def test_concurrent_double_return_of_same_location_line_never_goes_negative(login_as) -> None:
    """Défaut distinct, découvert pendant la même analyse (voir le rapport
    de ce lot) : la mise à jour atomique préexistante de
    ``LocationLigne.qte_en_location`` protégeait contre la perte de mise à
    jour mais pas contre un double retour concurrent de la MÊME ligne —
    ``qte_en_location`` pouvait passer en négatif. Corrigé par l'ajout
    d'une clause ``WHERE qte_en_location >= total_retour`` (même principe
    que l'epsilon de ``StockService.apply_movement`` pour
    ``Article.stock_actuel``)."""
    stack, _ = login_as("Administrateur")
    for i in range(CONCURRENCY_REPETITIONS):
        article = _make_rental_article(stack, f"ART-DVC-RET-{i}", Decimal("20"))
        client = stack.clients.create_client(f"Client DVC RET {i}")
        location = stack.rentals.create_location(
            date.today(), client.id, [LocationLigneInput(article.id, Decimal("10"), tarif_jour=Decimal("100"))]
        )
        confirmed = stack.rentals.confirm_location(location.id)
        departed = stack.rentals.depart_location(confirmed.id, date.today())
        ligne_id = departed.lignes[0].id

        # Deux retours concurrents de 10 chacun sur une ligne qui n'a que
        # 10 en location : un seul doit réussir, jamais qte_en_location < 0.
        errors = _concurrent_run(
            lambda lid=departed.id: stack.rentals.return_location_line(
                lid, ligne_id, date.today(), quantite_bon_etat=Decimal("10")
            ),
            lambda lid=departed.id: stack.rentals.return_location_line(
                lid, ligne_id, date.today(), quantite_bon_etat=Decimal("10")
            ),
        )
        succeeded = [e for e in errors if e is None]
        assert len(succeeded) == 1, f"itération {i} : {errors}"

        movements = stack.movements.list_movements(article_id=article.id)
        retour_movements = [m for m in movements if m.type.value == "LOCATION_RETOUR"]
        assert len(retour_movements) == 1, f"itération {i}"
        # Stock : 20 initial -> 10 après départ -> 20 après le seul retour accepté.
        assert stack.articles.get_article(article.id).stock_actuel == Decimal("20"), f"itération {i}"

        final_location = stack.rentals.get_location(departed.id)
        final_ligne = next(l for l in final_location.lignes if l.id == ligne_id)
        assert final_ligne.qte_en_location == Decimal("0"), f"itération {i}"
        assert final_ligne.qte_en_location >= 0, f"itération {i}"
