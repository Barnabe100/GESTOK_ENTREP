from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QSizeF
from PySide6.QtGui import QImage
from PySide6.QtGui import QPageSize

from app.models.enums import StatutLocation, StatutPaiement
from app.services.documents.receipt_document import (
    ReceiptFormat,
    build_location_receipt_document,
    build_location_reservation_voucher_document,
    build_payment_receipt_document,
    build_receipt_document,
)
from app.services.documents.receipt_service import (
    LocationReceiptData,
    LocationReceiptLigne,
    LocationReceiptPaymentLine,
    LocationReceiptRetour,
    LocationReservationLigne,
    LocationReservationVoucherData,
    PaymentReceiptData,
    SaleReceiptData,
    SaleReceiptLine,
    SaleReceiptPaymentLine,
)


def _make_line(reference="ART-1", designation="Article", qty="1", prix="100", sous_total="100") -> SaleReceiptLine:
    return SaleReceiptLine(
        article_reference=reference, article_designation=designation,
        quantite=Decimal(qty), prix_unitaire=Decimal(prix), sous_total=Decimal(sous_total),
    )


def _make_data(**overrides) -> SaleReceiptData:
    defaults = dict(
        numero="VNT-000042", date=date(2026, 1, 15), heure=time(14, 32), username="vendeur1",
        lignes=[_make_line()], total=Decimal("100"), devise="XOF",
        entreprise_nom="Boutique Étoile SARL", entreprise_adresse="12 rue du Commerce, Abidjan",
        entreprise_telephone="+225 01 02 03 04", entreprise_email="contact@etoile.ci",
        entreprise_logo_path=None,
    )
    defaults.update(overrides)
    return SaleReceiptData(**defaults)


def _make_image_file(path: Path, width: int = 20, height: int = 20) -> None:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(path))


# -- taille de page -------------------------------------------------------------------


def test_a4_page_size_is_standard(qapp) -> None:
    rendered = build_receipt_document(_make_data(), ReceiptFormat.A4)

    size_mm = rendered.page_size.size(QPageSize.Unit.Millimeter)
    assert round(size_mm.width()) == 210
    assert round(size_mm.height()) == 297


def test_ticket_page_width_is_80mm(qapp) -> None:
    rendered = build_receipt_document(_make_data(), ReceiptFormat.TICKET_80MM)

    size_mm = rendered.page_size.size(QPageSize.Unit.Millimeter)
    assert round(size_mm.width()) == 80


def test_ticket_height_grows_with_more_lines(qapp) -> None:
    short_data = _make_data(lignes=[_make_line()])
    long_data = _make_data(lignes=[_make_line(reference=f"ART-{i}") for i in range(30)])

    short_rendered = build_receipt_document(short_data, ReceiptFormat.TICKET_80MM)
    long_rendered = build_receipt_document(long_data, ReceiptFormat.TICKET_80MM)

    short_height = short_rendered.page_size.size(QPageSize.Unit.Millimeter).height()
    long_height = long_rendered.page_size.size(QPageSize.Unit.Millimeter).height()
    assert long_height > short_height


def test_ticket_height_has_a_minimum_for_very_short_content(qapp) -> None:
    data = _make_data(lignes=[])
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    height_mm = rendered.page_size.size(QPageSize.Unit.Millimeter).height()
    assert height_mm >= 40.0


# -- Lot 23 (anomalie A) : pagination — une seule page pour un ticket -----------------


def _page_count_at_final_size(document, page_size) -> int:
    """Reconfigure ``document`` au mode paginé, à la taille de page
    finalement choisie (celle qui sera réellement transmise au
    ``QPrinter``), pour vérifier le nombre de pages tel que Qt le
    calculerait réellement — jamais une estimation indirecte. Remet le
    document en mode page infinie ensuite, pour ne pas perturber un test
    qui inspecterait encore ``toHtml()``/``toPlainText()`` après cet appel."""
    size_mm = page_size.size(QPageSize.Unit.Millimeter)
    width_pt = size_mm.width() * 72.0 / 25.4
    height_pt = size_mm.height() * 72.0 / 25.4
    document.setPageSize(QSizeF(width_pt, height_pt))
    count = document.pageCount()
    document.setPageSize(QSizeF(-1, -1))
    return count


def test_ticket_single_article_with_logo_and_footer_fits_one_page(qapp, tmp_path) -> None:
    """Scénario exact du constat (§A du mandat) : un seul article, un logo
    et un pied de page configuré ne doivent jamais produire une seconde
    page contenant uniquement le pied de page."""
    logo_path = tmp_path / "logo.png"
    _make_image_file(logo_path, width=200, height=80)
    data = _make_data(
        lignes=[_make_line()],
        entreprise_logo_path=logo_path,
        pied_de_page="Merci pour votre confiance et à bientôt !",
    )
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    assert _page_count_at_final_size(rendered.document, rendered.page_size) == 1


def test_ticket_single_article_without_logo_fits_one_page(qapp) -> None:
    data = _make_data(lignes=[_make_line()], entreprise_logo_path=None)
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    assert _page_count_at_final_size(rendered.document, rendered.page_size) == 1


def test_ticket_single_article_without_footer_fits_one_page(qapp) -> None:
    data = _make_data(lignes=[_make_line()], pied_de_page="")
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    assert _page_count_at_final_size(rendered.document, rendered.page_size) == 1


def test_ticket_multiple_articles_fits_one_page(qapp) -> None:
    lignes = [_make_line(reference=f"ART-{i}", designation=f"Article {i}") for i in range(15)]
    data = _make_data(lignes=lignes, pied_de_page="Merci pour votre confiance et à bientôt !")
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    assert _page_count_at_final_size(rendered.document, rendered.page_size) == 1


def test_ticket_multiple_payments_fits_one_page(qapp) -> None:
    paiements = tuple(
        SaleReceiptPaymentLine(
            date_heure=datetime(2026, 1, 1, 10, i % 60), montant=Decimal("10"),
            mode_paiement="Espèces", reference=None, commentaire=None, username="v1",
        )
        for i in range(10)
    )
    data = _make_data(
        lignes=[_make_line()], paiements=paiements,
        pied_de_page="Merci pour votre confiance et à bientôt !",
    )
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    assert _page_count_at_final_size(rendered.document, rendered.page_size) == 1


def test_ticket_long_receipt_still_fits_one_page(qapp) -> None:
    """Un ticket n'a pas de hauteur de page prédéfinie (rouleau continu) :
    même très long, le document reste sur une seule page custom, jamais
    scindé en plusieurs pages physiques (contrairement à l'A4, voir
    ``test_a4_long_receipt_spans_multiple_pages`` ci-dessous)."""
    lignes = [_make_line(reference=f"ART-{i}", designation=f"Article numéro {i}") for i in range(60)]
    paiements = tuple(
        SaleReceiptPaymentLine(
            date_heure=datetime(2026, 1, 1, 10, i % 60), montant=Decimal("10"),
            mode_paiement="Espèces", reference=None, commentaire=None, username="v1",
        )
        for i in range(20)
    )
    data = _make_data(
        lignes=lignes, paiements=paiements,
        pied_de_page="Merci pour votre confiance et à bientôt !",
    )
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    assert _page_count_at_final_size(rendered.document, rendered.page_size) == 1


def test_ticket_page_fit_never_loses_content(qapp) -> None:
    """Non-régression explicite : la correction de pagination ne doit
    jamais tronquer d'information — tous les articles restent présents
    dans le texte du document final."""
    lignes = [_make_line(reference=f"ART-{i}", designation=f"Article {i}") for i in range(25)]
    data = _make_data(lignes=lignes, pied_de_page="Merci pour votre confiance et à bientôt !")
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    text = rendered.document.toPlainText()
    for i in range(25):
        assert f"ART-{i}" in text
    assert "Merci pour votre confiance et à bientôt !" in text


def test_a4_long_receipt_spans_multiple_pages(qapp) -> None:
    """Non-régression : l'A4 garde sa pagination automatique multi-page
    pour un contenu réellement long — comportement volontaire, non
    modifié par la correction de l'anomalie A (spécifique au ticket)."""
    lignes = [_make_line(reference=f"ART-{i}", designation=f"Article numéro {i}") for i in range(80)]
    data = _make_data(lignes=lignes)
    rendered = build_receipt_document(data, ReceiptFormat.A4)

    assert _page_count_at_final_size(rendered.document, rendered.page_size) > 1


def test_a4_page_size_unaffected_by_number_of_lines(qapp) -> None:
    """A4 gère la pagination automatiquement (plusieurs pages) : la taille
    de la page elle-même ne varie jamais, contrairement au ticket."""
    short_rendered = build_receipt_document(_make_data(lignes=[_make_line()]), ReceiptFormat.A4)
    long_data = _make_data(lignes=[_make_line(reference=f"ART-{i}") for i in range(50)])
    long_rendered = build_receipt_document(long_data, ReceiptFormat.A4)

    assert short_rendered.page_size.size(QPageSize.Unit.Millimeter) == long_rendered.page_size.size(
        QPageSize.Unit.Millimeter
    )


# -- contenu ----------------------------------------------------------------------------


def test_a4_line_quantity_has_no_unnecessary_decimals(qapp) -> None:
    data = _make_data(lignes=[_make_line(qty="10.000", sous_total="1000")])
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "10" in text
    assert "10.000" not in text
    assert "10,5" not in text


def test_a4_line_quantity_preserves_real_decimal(qapp) -> None:
    data = _make_data(lignes=[_make_line(qty="2.500", sous_total="250")])
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "2,5" in text
    assert "2.500" not in text


def test_ticket_line_quantity_preserves_real_decimal(qapp) -> None:
    data = _make_data(lignes=[_make_line(qty="2.500", sous_total="250")])
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    text = rendered.document.toPlainText()

    assert "2,5" in text
    assert "2.500" not in text


def test_a4_contains_company_and_sale_info(qapp) -> None:
    rendered = build_receipt_document(_make_data(), ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "Boutique Étoile SARL" in text
    assert "VNT-000042" in text
    assert "vendeur1" in text


def test_ticket_contains_company_and_sale_info(qapp) -> None:
    rendered = build_receipt_document(_make_data(), ReceiptFormat.TICKET_80MM)
    text = rendered.document.toPlainText()

    assert "Boutique Étoile SARL" in text
    assert "VNT-000042" in text


def test_missing_company_profile_shows_placeholder_not_stockmanager_identity(qapp) -> None:
    data = _make_data(entreprise_nom=None, entreprise_adresse=None, entreprise_telephone=None, entreprise_email=None)
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "non configurée" in text
    # Lot 21 : la mention StockManager est entièrement supprimée du reçu
    # (jamais remplacée par une autre signature logicielle) — elle ne doit
    # donc plus jamais apparaître, y compris comme s'il s'agissait du nom de
    # l'entreprise cliente absente.
    assert "StockManager" not in text


def test_no_stockmanager_mention_on_sale_receipt(qapp) -> None:
    """Lot 21 : « Document généré par StockManager » (et toute variante
    équivalente) est supprimée du reçu de vente — jamais remplacée par une
    autre publicité logicielle. L'identité de l'entreprise cliente, elle,
    reste affichée normalement."""
    rendered = build_receipt_document(_make_data(), ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "StockManager" not in text
    assert "généré par" not in text.lower()
    assert "Boutique Étoile SARL" in text


def test_missing_logo_does_not_crash(qapp) -> None:
    data = _make_data(entreprise_logo_path=None)
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    assert rendered.document is not None


def test_invalid_logo_path_does_not_crash(qapp, tmp_path) -> None:
    data = _make_data(entreprise_logo_path=tmp_path / "does_not_exist.png")
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    assert rendered.document is not None


def test_valid_logo_is_embedded_as_resource(qapp, tmp_path) -> None:
    logo_path = tmp_path / "logo.png"
    _make_image_file(logo_path)
    data = _make_data(entreprise_logo_path=logo_path)

    rendered = build_receipt_document(data, ReceiptFormat.A4)

    assert "<img" in rendered.document.toHtml()


def test_accented_characters_are_preserved(qapp) -> None:
    data = _make_data(
        entreprise_nom="Épicerie Générale & Café",
        lignes=[_make_line(designation="Éclairs à la crème")],
    )
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    text = rendered.document.toPlainText()

    assert "Épicerie Générale & Café" in text
    assert "Éclairs à la crème" in text


def test_currency_xof_has_no_decimals(qapp) -> None:
    data = _make_data(devise="XOF", total=Decimal("15000"))
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "15 000" in text
    assert "15 000,00" not in text


def test_currency_eur_has_decimals(qapp) -> None:
    data = _make_data(devise="EUR", total=Decimal("150"))
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "150,00" in text or "150.00" in text


def test_same_data_produces_consistent_totals_across_formats(qapp) -> None:
    data = _make_data()
    a4_text = build_receipt_document(data, ReceiptFormat.A4).document.toPlainText()
    ticket_text = build_receipt_document(data, ReceiptFormat.TICKET_80MM).document.toPlainText()

    assert data.numero in a4_text
    assert data.numero in ticket_text
    # Le service ne dépend jamais du format : même total, dans les deux rendus.
    assert "100" in a4_text
    assert "100" in ticket_text


# -- client (lot Intégration du client dans les reçus et PDF) --------------------------


def _make_data_with_client(**overrides) -> SaleReceiptData:
    client_defaults = dict(
        client_nom="Jean Dupont", client_telephone="0102030405",
        client_adresse="5 avenue des Fleurs", client_email="jean@example.com",
    )
    client_defaults.update(overrides)
    return _make_data(**client_defaults)


def test_a4_shows_client_section_with_full_info(qapp) -> None:
    data = _make_data_with_client()
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "CLIENT" in text
    assert "Jean Dupont" in text
    assert "0102030405" in text
    assert "5 avenue des Fleurs" in text
    assert "jean@example.com" in text


def test_ticket_shows_client_block_with_full_info(qapp) -> None:
    data = _make_data_with_client()
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    text = rendered.document.toPlainText()

    assert "Jean Dupont" in text
    assert "0102030405" in text


def test_a4_without_client_has_no_client_section(qapp) -> None:
    """client_id = NULL -> aucune section Client, aucun espace inutile."""
    data = _make_data()  # aucun champ client_* renseigné
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "CLIENT" not in text


def test_ticket_without_client_has_no_client_block(qapp) -> None:
    data = _make_data()
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    text = rendered.document.toPlainText()

    assert "Client :" not in text


def test_a4_client_section_omits_missing_optional_fields(qapp) -> None:
    """Client renseigné mais sans téléphone/adresse/email : ces lignes ne
    doivent jamais apparaître (jamais None/N/A)."""
    data = _make_data_with_client(client_telephone=None, client_adresse=None, client_email=None)
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "CLIENT" in text
    assert "Jean Dupont" in text
    assert "None" not in text
    assert "N/A" not in text
    assert "Téléphone" not in text
    assert "Adresse" not in text
    assert "Email" not in text


def test_ticket_client_block_omits_missing_optional_fields(qapp) -> None:
    data = _make_data_with_client(client_telephone=None, client_adresse=None, client_email=None)
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    text = rendered.document.toPlainText()

    assert "Jean Dupont" in text
    assert "None" not in text
    assert "N/A" not in text


def test_a4_client_section_shows_only_telephone_when_only_field_set(qapp) -> None:
    data = _make_data_with_client(client_adresse=None, client_email=None)
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "0102030405" in text
    assert "Adresse" not in text
    assert "Email" not in text


def test_client_accented_name_and_address_preserved(qapp) -> None:
    data = _make_data_with_client(client_nom="Éric Ndiaye-Côté", client_adresse="Résidence Étoile")
    a4_text = build_receipt_document(data, ReceiptFormat.A4).document.toPlainText()
    ticket_text = build_receipt_document(data, ReceiptFormat.TICKET_80MM).document.toPlainText()

    assert "Éric Ndiaye-Côté" in a4_text
    assert "Résidence Étoile" in a4_text
    assert "Éric Ndiaye-Côté" in ticket_text


# -- hauteur dynamique du ticket avec/sans client ---------------------------------------


def test_ticket_with_client_is_taller_than_without_for_same_lines(qapp) -> None:
    data_without_client = _make_data()
    data_with_client = _make_data_with_client()

    height_without = build_receipt_document(data_without_client, ReceiptFormat.TICKET_80MM).page_size.size(
        QPageSize.Unit.Millimeter
    ).height()
    height_with = build_receipt_document(data_with_client, ReceiptFormat.TICKET_80MM).page_size.size(
        QPageSize.Unit.Millimeter
    ).height()

    assert height_with > height_without


def test_ticket_height_still_grows_with_more_lines_when_client_present(qapp) -> None:
    short_data = _make_data_with_client(lignes=[_make_line()])
    long_data = _make_data_with_client(lignes=[_make_line(reference=f"ART-{i}") for i in range(30)])

    short_height = build_receipt_document(short_data, ReceiptFormat.TICKET_80MM).page_size.size(
        QPageSize.Unit.Millimeter
    ).height()
    long_height = build_receipt_document(long_data, ReceiptFormat.TICKET_80MM).page_size.size(
        QPageSize.Unit.Millimeter
    ).height()

    assert long_height > short_height


def test_a4_page_size_unaffected_by_client_presence(qapp) -> None:
    """A4 gère la pagination automatiquement — la taille de page ne varie
    jamais, avec ou sans client (comme avec ou sans lignes, déjà vérifié)."""
    without_client = build_receipt_document(_make_data(), ReceiptFormat.A4)
    with_client = build_receipt_document(_make_data_with_client(), ReceiptFormat.A4)

    assert without_client.page_size.size(QPageSize.Unit.Millimeter) == with_client.page_size.size(
        QPageSize.Unit.Millimeter
    )


# -- ventes à crédit / paiements partiels (§5.8) --------------------------------------


def test_a4_shows_paid_and_remaining_for_partial_payment(qapp) -> None:
    data = _make_data(
        total=Decimal("300"), montant_paye=Decimal("100"), statut_paiement=StatutPaiement.PARTIELLEMENT_PAYEE
    )
    rendered = build_receipt_document(data, ReceiptFormat.A4)

    text = rendered.document.toPlainText()
    assert "200" in text  # reste à payer
    assert "Partiellement payée" in text


def test_ticket_shows_paid_and_remaining_for_partial_payment(qapp) -> None:
    data = _make_data(
        total=Decimal("300"), montant_paye=Decimal("100"), statut_paiement=StatutPaiement.PARTIELLEMENT_PAYEE
    )
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)

    text = rendered.document.toPlainText()
    assert "200" in text
    assert "Partiellement payée" in text


def test_a4_shows_zero_remaining_for_fully_paid_sale(qapp) -> None:
    data = _make_data(total=Decimal("100"), montant_paye=Decimal("100"), statut_paiement=StatutPaiement.PAYEE)
    rendered = build_receipt_document(data, ReceiptFormat.A4)

    text = rendered.document.toPlainText()
    assert "Payée" in text


def _make_payment_receipt_data(**overrides) -> PaymentReceiptData:
    defaults = dict(
        vente_numero="VNT-000042", client_nom="Client Crédit", montant=Decimal("100"),
        total_vente=Decimal("300"), total_paye_apres=Decimal("100"),
        date_heure=datetime(2026, 1, 20, 10, 30), username="vendeur1", devise="XOF",
        entreprise_nom="Boutique Étoile SARL", entreprise_adresse="12 rue du Commerce, Abidjan",
        entreprise_telephone="+225 01 02 03 04", entreprise_email="contact@etoile.ci",
    )
    defaults.update(overrides)
    return PaymentReceiptData(**defaults)


def test_payment_receipt_shows_amount_and_remaining(qapp) -> None:
    rendered = build_payment_receipt_document(_make_payment_receipt_data())

    text = rendered.document.toPlainText()
    assert "VNT-000042" in text
    assert "Client Crédit" in text
    assert "vendeur1" in text
    assert "200" in text  # reste à payer (300 - 100)


def test_payment_receipt_page_size_is_a4(qapp) -> None:
    rendered = build_payment_receipt_document(_make_payment_receipt_data())

    size_mm = rendered.page_size.size(QPageSize.Unit.Millimeter)
    assert round(size_mm.width()) == 210
    assert round(size_mm.height()) == 297


def test_payment_receipt_without_client_has_no_client_line(qapp) -> None:
    rendered = build_payment_receipt_document(_make_payment_receipt_data(client_nom=None))

    text = rendered.document.toPlainText()
    assert "Client Crédit" not in text


# -- mode de paiement / référence (lot Harmonisation des reçus) -----------------------


def test_payment_receipt_shows_mode_and_reference_when_set(qapp) -> None:
    rendered = build_payment_receipt_document(
        _make_payment_receipt_data(mode_paiement="Mobile Money", reference="MM-REF-42")
    )

    text = rendered.document.toPlainText()
    assert "Mobile Money" in text
    assert "MM-REF-42" in text


def test_payment_receipt_omits_mode_and_reference_lines_when_absent(qapp) -> None:
    rendered = build_payment_receipt_document(_make_payment_receipt_data(mode_paiement=None, reference=None))

    text = rendered.document.toPlainText()
    assert "Mode de paiement" not in text
    assert "Référence" not in text


def test_payment_receipt_has_no_stockmanager_mention(qapp) -> None:
    """Lot 21 : la mention logicielle est également supprimée du reçu de
    paiement individuel, jamais remplacée."""
    rendered = build_payment_receipt_document(_make_payment_receipt_data())

    text = rendered.document.toPlainText()
    assert "StockManager" not in text
    assert "généré par" not in text.lower()


# -- Lot 21/23 : logo redimensionné (boîte maximale propre à chaque format) -----------

_A4_LOGO_BOX = (40.0, 20.0)
_TICKET_LOGO_BOX = (30.0, 15.0)


def test_logo_box_fit_wide_image_is_width_constrained_a4(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    # ratio 4:1, plus large que la boîte A4 (40/20 = 2.0) — image haute
    # résolution (400x100 px), bien au-delà de sa taille naturelle à 150 DPI :
    # toujours réduite pour tenir dans la boîte.
    width_mm, height_mm = _fit_logo_box(4000, 1000, *_A4_LOGO_BOX)

    assert width_mm == 40.0
    assert round(height_mm, 3) == round(40.0 / 4.0, 3)


def test_logo_box_fit_tall_image_is_height_constrained_a4(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(1000, 2000, *_A4_LOGO_BOX)  # ratio 0.5

    assert height_mm == 20.0
    assert round(width_mm, 3) == round(20.0 * 0.5, 3)


def test_logo_box_fit_wide_image_is_width_constrained_ticket(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(4000, 1000, *_TICKET_LOGO_BOX)  # ratio 4:1

    assert width_mm == 30.0
    assert round(height_mm, 3) == round(30.0 / 4.0, 3)


def test_logo_box_fit_tall_image_is_height_constrained_ticket(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(1000, 2000, *_TICKET_LOGO_BOX)  # ratio 0.5

    assert height_mm == 15.0
    assert round(width_mm, 3) == round(15.0 * 0.5, 3)


def test_logo_box_fit_never_exceeds_max_dimensions(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    for max_box in (_A4_LOGO_BOX, _TICKET_LOGO_BOX):
        for width_px, height_px in [(4000, 1000), (1000, 2000), (3000, 3000), (1, 1), (4000, 1)]:
            width_mm, height_mm = _fit_logo_box(width_px, height_px, *max_box)
            assert width_mm <= max_box[0] + 1e-6
            assert height_mm <= max_box[1] + 1e-6


def test_logo_box_fit_preserves_aspect_ratio(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(2000, 500, *_A4_LOGO_BOX)  # ratio 4:1
    assert round(width_mm / height_mm, 3) == round(2000 / 500, 3)


def test_logo_box_fit_never_returns_negative_or_zero_for_valid_image(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(100, 100, *_TICKET_LOGO_BOX)
    assert width_mm > 0
    assert height_mm > 0


def test_logo_sized_image_is_embedded_with_explicit_dimensions(qapp, tmp_path) -> None:
    """Le logo valide doit porter des attributs width/height explicites
    (jamais une taille fixe arbitraire) — c'est ce qui garantit le respect
    de la boîte propre au format, quelle que soit la forme de l'image
    source."""
    logo_path = tmp_path / "logo_wide.png"
    _make_image_file(logo_path, width=4000, height=1000)
    data = _make_data(entreprise_logo_path=logo_path)

    rendered = build_receipt_document(data, ReceiptFormat.A4)
    html = rendered.document.toHtml()

    assert "<img" in html
    assert 'width="' in html
    assert 'height="' in html


def test_ticket_logo_does_not_overflow_80mm_width(qapp, tmp_path) -> None:
    """Le logo (30 mm maximum sur ticket) doit toujours tenir dans la
    largeur de contenu du ticket (80 - 2x4 mm de marge = 72 mm) — aucun
    débordement horizontal possible par construction."""
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, _height_mm = _fit_logo_box(10000, 1000, *_TICKET_LOGO_BOX)  # image très large
    assert width_mm <= 30.0
    assert width_mm < 72.0  # largeur de contenu du ticket 80 mm


# -- Lot 23 (§C) : seuil de 150 DPI, jamais d'agrandissement d'un logo basse résolution -


def test_logo_low_resolution_is_not_upscaled_beyond_natural_size_a4(qapp) -> None:
    """Un petit logo (ex. 100x50 px) tient déjà dans sa taille naturelle à
    150 DPI (100/150*25.4 ~= 16.9 mm) sous la boîte A4 (40x20 mm) : il ne
    doit jamais être agrandi pour la remplir."""
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(100, 50, *_A4_LOGO_BOX)

    natural_width_mm = (100 / 150.0) * 25.4
    natural_height_mm = (50 / 150.0) * 25.4
    assert round(width_mm, 3) == round(natural_width_mm, 3)
    assert round(height_mm, 3) == round(natural_height_mm, 3)
    assert width_mm < _A4_LOGO_BOX[0]
    assert height_mm < _A4_LOGO_BOX[1]


def test_logo_low_resolution_is_not_upscaled_beyond_natural_size_ticket(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(80, 40, *_TICKET_LOGO_BOX)

    natural_width_mm = (80 / 150.0) * 25.4
    natural_height_mm = (40 / 150.0) * 25.4
    assert round(width_mm, 3) == round(natural_width_mm, 3)
    assert round(height_mm, 3) == round(natural_height_mm, 3)
    assert width_mm < _TICKET_LOGO_BOX[0]
    assert height_mm < _TICKET_LOGO_BOX[1]


def test_logo_high_resolution_is_still_shrunk_to_fit_box(qapp) -> None:
    """Non-régression : une image dont la taille naturelle à 150 DPI
    dépasse la boîte reste réduite pour y tenir, exactement comme avant
    l'introduction du seuil de qualité."""
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(4000, 1000, *_A4_LOGO_BOX)

    assert width_mm == 40.0
    assert height_mm <= 20.0


def test_logo_natural_size_exactly_matching_box_is_not_altered(qapp) -> None:
    """Cas limite : une image dont la taille naturelle à 150 DPI correspond
    exactement à la boîte n'est ni agrandie ni réduite."""
    from app.services.documents.receipt_document import _fit_logo_box

    width_px = round(_A4_LOGO_BOX[0] / 25.4 * 150.0)
    height_px = round(_A4_LOGO_BOX[1] / 25.4 * 150.0)
    width_mm, height_mm = _fit_logo_box(width_px, height_px, *_A4_LOGO_BOX)

    assert round(width_mm, 1) == _A4_LOGO_BOX[0]
    assert round(height_mm, 1) == _A4_LOGO_BOX[1]


# -- Lot 21 : historique des paiements sur le reçu unifié ------------------------------


def _make_payment_line(
    montant="100", mode_paiement="Espèces", reference=None, commentaire=None, username="vendeur1",
) -> SaleReceiptPaymentLine:
    return SaleReceiptPaymentLine(
        date_heure=datetime(2026, 1, 20, 10, 30),
        montant=Decimal(montant),
        mode_paiement=mode_paiement,
        reference=reference,
        commentaire=commentaire,
        username=username,
    )


def test_a4_shows_no_payment_history_section_when_no_payments(qapp) -> None:
    rendered = build_receipt_document(_make_data(paiements=()), ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "HISTORIQUE DES PAIEMENTS" not in text


def test_a4_shows_each_payment_in_history(qapp) -> None:
    data = _make_data(
        paiements=(
            _make_payment_line(montant="100", reference="REF-1"),
            _make_payment_line(montant="50", mode_paiement="Mobile Money", reference="REF-2"),
        )
    )
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "HISTORIQUE DES PAIEMENTS" in text
    assert "REF-1" in text
    assert "REF-2" in text
    assert "Mobile Money" in text
    assert "vendeur1" in text


def test_a4_payment_history_shows_commentaire_when_set(qapp) -> None:
    data = _make_data(paiements=(_make_payment_line(commentaire="Acompte à la commande"),))
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "Acompte à la commande" in text


def test_a4_payment_history_never_shows_dash_for_commentaire_when_absent(qapp) -> None:
    """Aucune donnée inventée : un commentaire non renseigné ne doit laisser
    aucune trace (ni ligne vide, ni "—"), contrairement à mode/référence qui
    affichent un tiret explicite lorsqu'absents."""
    data = _make_data(paiements=(_make_payment_line(mode_paiement=None, reference=None, commentaire=None),))
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    html = rendered.document.toHtml()

    assert html.count("font-style:italic") == 0


def test_ticket_shows_each_payment_in_history(qapp) -> None:
    data = _make_data(
        paiements=(
            _make_payment_line(montant="100", reference="REF-1"),
            _make_payment_line(montant="50", mode_paiement="Mobile Money", reference="REF-2"),
        )
    )
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    text = rendered.document.toPlainText()

    assert "Historique des paiements" in text
    assert "REF-1" in text
    assert "REF-2" in text


def test_ticket_payment_history_increases_height(qapp) -> None:
    """La hauteur du ticket doit rester dynamique : davantage de paiements
    produit un ticket plus haut, sans aucune troncature (réutilise le même
    mécanisme de mesure que pour les lignes d'articles)."""
    base = build_receipt_document(_make_data(paiements=()), ReceiptFormat.TICKET_80MM)
    many_payments = tuple(_make_payment_line(montant="10", reference=f"REF-{i}") for i in range(15))
    taller = build_receipt_document(_make_data(paiements=many_payments), ReceiptFormat.TICKET_80MM)

    base_height = base.page_size.size(QPageSize.Unit.Millimeter).height()
    taller_height = taller.page_size.size(QPageSize.Unit.Millimeter).height()
    assert taller_height > base_height


def test_payment_history_total_never_confused_with_sale_total(qapp) -> None:
    """Un paiement partiel ne doit jamais apparaître comme si la vente était
    intégralement réglée : le total de la vente et chaque paiement restent
    des montants distincts et tous deux visibles."""
    data = _make_data(
        total=Decimal("300"), montant_paye=Decimal("100"),
        paiements=(_make_payment_line(montant="100"),),
    )
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "Total : " in text
    assert "200" in text  # reste à payer, jamais confondu avec le paiement de 100


# -- Lot 21 : phrase de pied de reçu configurable --------------------------------------


def test_a4_shows_configured_footer_phrase(qapp) -> None:
    rendered = build_receipt_document(_make_data(pied_de_page="Merci pour votre confiance et à bientôt !"), ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "Merci pour votre confiance et à bientôt !" in text


def test_ticket_shows_configured_footer_phrase(qapp) -> None:
    rendered = build_receipt_document(
        _make_data(pied_de_page="Merci pour votre confiance et à bientôt !"), ReceiptFormat.TICKET_80MM
    )
    text = rendered.document.toPlainText()

    assert "Merci pour votre confiance et à bientôt !" in text


def test_a4_shows_no_footer_phrase_when_empty(qapp) -> None:
    rendered = build_receipt_document(_make_data(pied_de_page=""), ReceiptFormat.A4)
    text_with_default = build_receipt_document(
        _make_data(pied_de_page="Phrase personnalisée"), ReceiptFormat.A4
    ).document.toPlainText()

    assert "Phrase personnalisée" in text_with_default
    # Avec une phrase vide, aucun texte de pied de reçu ne doit apparaître.
    html = rendered.document.toHtml()
    assert "margin-top:20px" not in html


def test_ticket_shows_no_footer_phrase_when_empty(qapp) -> None:
    rendered = build_receipt_document(_make_data(pied_de_page=""), ReceiptFormat.TICKET_80MM)
    html = rendered.document.toHtml()

    assert "margin-top:20px" not in html


# -- Lot 23 (§B) : ordre canonique, logo avant toute information d'entreprise --------


def test_ticket_logo_appears_before_company_name(qapp, tmp_path) -> None:
    logo_path = tmp_path / "logo.png"
    _make_image_file(logo_path, width=100, height=100)
    data = _make_data(entreprise_logo_path=logo_path, entreprise_nom="Boutique Étoile SARL")
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    html = rendered.document.toHtml()

    logo_index = html.find("stockmanager-receipt://logo-entreprise")
    nom_index = html.find("Boutique")
    assert logo_index != -1
    assert nom_index != -1
    assert logo_index < nom_index


def test_ticket_without_logo_starts_directly_with_company_name(qapp) -> None:
    data = _make_data(entreprise_logo_path=None, entreprise_nom="Boutique Étoile SARL")
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    html = rendered.document.toHtml()

    assert "stockmanager-receipt://logo-entreprise" not in html
    text = rendered.document.toPlainText().strip()
    assert text.startswith("Boutique Étoile SARL")


def test_ticket_footer_preceded_by_separator_when_present(qapp) -> None:
    rendered = build_receipt_document(
        _make_data(pied_de_page="Merci pour votre confiance et à bientôt !"), ReceiptFormat.TICKET_80MM
    )
    html = rendered.document.toHtml()

    separator_count = html.count("------------------------------")
    # Trois séparateurs « structurels » (après coordonnées, après client/
    # infos reçu, après articles) toujours présents, plus celui ajouté
    # juste avant le pied de page (Lot 23, §B).
    assert separator_count == 4


def test_ticket_no_dangling_separator_when_no_footer(qapp) -> None:
    rendered_with = build_receipt_document(
        _make_data(pied_de_page="Phrase"), ReceiptFormat.TICKET_80MM
    )
    rendered_without = build_receipt_document(
        _make_data(pied_de_page=""), ReceiptFormat.TICKET_80MM
    )

    count_with = rendered_with.document.toHtml().count("------------------------------")
    count_without = rendered_without.document.toHtml().count("------------------------------")
    assert count_without == count_with - 1


def test_a4_logo_is_centered(qapp, tmp_path) -> None:
    logo_path = tmp_path / "logo.png"
    _make_image_file(logo_path, width=100, height=100)
    data = _make_data(entreprise_logo_path=logo_path)
    rendered = build_receipt_document(data, ReceiptFormat.A4)
    html = rendered.document.toHtml()

    img_index = html.find("<img")
    preceding = html[:img_index]
    last_p_open = preceding.rfind("<p")
    assert last_p_open != -1
    assert "center" in preceding[last_p_open:img_index].lower()


def test_location_voucher_logo_is_centered(qapp, tmp_path) -> None:
    logo_path = tmp_path / "logo.png"
    _make_image_file(logo_path, width=100, height=100)
    data = _make_voucher_data(entreprise_logo_path=logo_path)
    rendered = build_location_reservation_voucher_document(data)
    html = rendered.document.toHtml()

    img_index = html.find("<img")
    preceding = html[:img_index]
    last_p_open = preceding.rfind("<p")
    assert last_p_open != -1
    assert "center" in preceding[last_p_open:img_index].lower()


def test_location_receipt_logo_is_centered(qapp, tmp_path) -> None:
    logo_path = tmp_path / "logo.png"
    _make_image_file(logo_path, width=100, height=100)
    data = _make_location_receipt_data(entreprise_logo_path=logo_path)
    rendered = build_location_receipt_document(data)
    html = rendered.document.toHtml()

    img_index = html.find("<img")
    preceding = html[:img_index]
    last_p_open = preceding.rfind("<p")
    assert last_p_open != -1
    assert "center" in preceding[last_p_open:img_index].lower()


def test_location_voucher_uses_ticket_or_a4_box(qapp, tmp_path) -> None:
    """Les documents de location restent en A4 uniquement (décision Lot 22,
    confirmée) : ils utilisent donc la boîte A4 (40x20 mm), jamais la boîte
    ticket (30x15 mm)."""
    logo_path = tmp_path / "logo.png"
    _make_image_file(logo_path, width=4000, height=1000)  # large, haute résolution
    data = _make_voucher_data(entreprise_logo_path=logo_path)
    rendered = build_location_reservation_voucher_document(data)
    html = rendered.document.toHtml()

    assert 'width="113.4"' in html  # 40 mm en points (40 * 72 / 25.4)


# -- Lot 22 (anomalie D) : tailles de police explicites sur le ticket 80 mm -----------


def test_ticket_html_contains_every_explicit_font_size_in_the_scale(qapp) -> None:
    """Vérifie que les tailles réellement appliquées (et non seulement
    présentes dans un conteneur englobant) couvrent chaque type de
    contenu : en-tête, corps, lignes d'articles, total et pied de reçu.
    ``QTextDocument.toHtml()`` ne réémet jamais le ``font-size`` posé sur
    un ``<table>``/<div> tel quel, mais le propage toujours vers les
    ``<span>`` qui portent le texte réellement affiché — c'est cette
    propagation, vérifiée empiriquement, qui est testée ici, pas la seule
    présence d'une règle dans un conteneur (voir le constat de l'anomalie
    D : un ``font-size`` sur le seul conteneur ne suffit pas)."""
    data = _make_data(
        paiements=(
            SaleReceiptPaymentLine(
                date_heure=datetime(2026, 1, 20, 10, 30), montant=Decimal("50"),
                mode_paiement="Espèces", reference=None, commentaire=None, username="vendeur1",
            ),
        ),
    )
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    html = rendered.document.toHtml()

    assert "9pt" in html  # en-tête (nom de l'entreprise)
    assert "8pt" in html  # corps / pied de reçu
    assert "7.5pt" in html  # ligne d'article (désignation + table qté/prix/montant)
    assert "10pt" in html  # total, volontairement plus grand
    assert "7pt" in html  # historique des paiements


def test_ticket_article_line_uses_article_font_size_not_only_container(qapp) -> None:
    """Isole la désignation d'un article réellement distinctif pour
    vérifier qu'elle est bien enveloppée dans un ``<span>`` à la taille
    ``_TICKET_FONT_ARTICLE_PT`` — pas seulement que cette taille existe
    quelque part dans le document."""
    data = _make_data(lignes=[_make_line(designation="Tequila grosse bouteille")])
    rendered = build_receipt_document(data, ReceiptFormat.TICKET_80MM)
    html = rendered.document.toHtml()

    designation_index = html.index("Tequila grosse bouteille")
    preceding = html[:designation_index]
    last_span_open = preceding.rfind("<span")
    assert last_span_open != -1
    assert "7.5pt" in preceding[last_span_open:designation_index]


def test_ticket_total_amount_uses_larger_font_than_article_lines(qapp) -> None:
    rendered = build_receipt_document(_make_data(total=Decimal("12345")), ReceiptFormat.TICKET_80MM)
    html = rendered.document.toHtml()

    total_index = html.index("TOTAL")
    preceding = html[:total_index]
    last_span_open = preceding.rfind("<span")
    assert last_span_open != -1
    assert "10pt" in preceding[last_span_open:total_index]


def test_ticket_many_articles_and_payments_keeps_explicit_sizes_and_no_overflow(qapp) -> None:
    """Scénario avec de nombreux articles et paiements (§11 du mandat) :
    la hauteur reste dynamique, la largeur reste 80 mm, et les tailles
    explicites restent appliquées sur chaque ligne."""
    lignes = [_make_line(reference=f"ART-{i}", designation=f"Article {i}") for i in range(20)]
    paiements = tuple(
        SaleReceiptPaymentLine(
            date_heure=datetime(2026, 1, 1, 10, i % 60), montant=Decimal("10"),
            mode_paiement=None, reference=None, commentaire=None, username="v1",
        )
        for i in range(15)
    )
    rendered = build_receipt_document(_make_data(lignes=lignes, paiements=paiements), ReceiptFormat.TICKET_80MM)

    size_mm = rendered.page_size.size(QPageSize.Unit.Millimeter)
    assert round(size_mm.width()) == 80
    assert size_mm.height() > 40.0  # hauteur minimale par défaut (ticket vide)
    html = rendered.document.toHtml()
    assert "7.5pt" in html
    assert "7pt" in html


def test_ticket_footer_phrase_is_single_and_not_duplicated_with_fixed_message(qapp) -> None:
    """Non-régression explicite (§3 de l'autorisation) : un seul message
    de remerciement, jamais un second message fixe « Merci de votre
    visite »."""
    rendered = build_receipt_document(_make_data(pied_de_page="Merci pour votre confiance et à bientôt !"), ReceiptFormat.TICKET_80MM)
    text = rendered.document.toPlainText()

    assert text.count("Merci pour votre confiance et à bientôt !") == 1
    assert "Merci de votre visite" not in text


# -- Lot 22 (§F) : documents de location ------------------------------------------------


def _make_reservation_ligne(reference="ART-LOC", designation="Article de location", qty="2", tarif="500"):
    return LocationReservationLigne(
        article_reference=reference, article_designation=designation,
        quantite_reservee=Decimal(qty), tarif_jour=Decimal(tarif),
    )


def _make_voucher_data(**overrides) -> LocationReservationVoucherData:
    defaults = dict(
        numero="LOC-000007", date=date(2026, 1, 10), username="vendeur1",
        lignes=[_make_reservation_ligne()], caution_montant=Decimal("0"), devise="XOF",
        entreprise_nom="Boutique Étoile SARL", entreprise_adresse="12 rue du Commerce, Abidjan",
        entreprise_telephone="+225 01 02 03 04", entreprise_email="contact@etoile.ci",
        entreprise_logo_path=None,
    )
    defaults.update(overrides)
    return LocationReservationVoucherData(**defaults)


def _make_location_retour(date_retour=date(2026, 1, 13), qty="2", jours=3, montant="3000"):
    return LocationReceiptRetour(
        date_retour=date_retour, quantite=Decimal(qty), jours=jours, montant_facture=Decimal(montant),
    )


def _make_location_ligne(reference="ART-LOC", designation="Article de location", tarif="500", retours=None):
    return LocationReceiptLigne(
        article_reference=reference, article_designation=designation,
        tarif_jour=Decimal(tarif), retours=tuple(retours) if retours is not None else (),
    )


def _make_location_receipt_data(**overrides) -> LocationReceiptData:
    defaults = dict(
        numero="LOC-000007", date=date(2026, 1, 10), date_depart=date(2026, 1, 10), username="vendeur1",
        statut=StatutLocation.RETOURNEE,
        lignes=[_make_location_ligne(retours=[_make_location_retour()])],
        total_facture=Decimal("3000"), montant_paye=Decimal("0"), paiements=(),
        caution_montant=Decimal("0"), caution_rendue=Decimal("0"), devise="XOF",
        entreprise_nom="Boutique Étoile SARL", entreprise_adresse="12 rue du Commerce, Abidjan",
        entreprise_telephone="+225 01 02 03 04", entreprise_email="contact@etoile.ci",
        entreprise_logo_path=None,
    )
    defaults.update(overrides)
    return LocationReceiptData(**defaults)


def test_reservation_voucher_is_a4(qapp) -> None:
    rendered = build_location_reservation_voucher_document(_make_voucher_data())

    size_mm = rendered.page_size.size(QPageSize.Unit.Millimeter)
    assert round(size_mm.width()) == 210
    assert round(size_mm.height()) == 297


def test_reservation_voucher_never_shows_a_total_amount(qapp) -> None:
    """§F : jamais de montant total engagé affiché comme un chiffre — la
    phrase explicative peut mentionner le mot « total » (c'est précisément
    ce qu'elle explique ne pas être calculable), mais aucune ligne de type
    « Total : X » comme sur le reçu de vente (``_build_a4_html``)."""
    rendered = build_location_reservation_voucher_document(_make_voucher_data())
    text = rendered.document.toPlainText()

    assert "Total :" not in text
    assert "TOTAL" not in text


def test_reservation_voucher_explicitly_states_not_a_payment_receipt(qapp) -> None:
    rendered = build_location_reservation_voucher_document(_make_voucher_data())
    text = rendered.document.toPlainText()

    assert "réservation" in text.lower()
    assert "ne constitue pas un reçu de paiement" in text.lower()


def test_reservation_voucher_shows_article_lines_with_rate(qapp) -> None:
    rendered = build_location_reservation_voucher_document(
        _make_voucher_data(lignes=[_make_reservation_ligne(reference="ART-42", qty="3", tarif="700")])
    )
    html = rendered.document.toHtml()

    assert "ART-42" in html
    assert "3" in html
    assert "700" in html


def test_reservation_voucher_shows_planned_caution_when_defined(qapp) -> None:
    rendered = build_location_reservation_voucher_document(
        _make_voucher_data(caution_montant=Decimal("10000"))
    )
    text = rendered.document.toPlainText()

    assert "Caution prévue" in text
    assert "10 000 FCFA" in text


def test_reservation_voucher_omits_caution_block_when_not_defined(qapp) -> None:
    rendered = build_location_reservation_voucher_document(
        _make_voucher_data(caution_montant=Decimal("0"))
    )
    text = rendered.document.toPlainText()

    assert "Caution prévue" not in text


def test_reservation_voucher_logo_respects_max_box(qapp, tmp_path) -> None:
    logo_path = tmp_path / "logo.png"
    _make_image_file(logo_path, width=400, height=100)
    rendered = build_location_reservation_voucher_document(
        _make_voucher_data(entreprise_logo_path=logo_path)
    )
    html = rendered.document.toHtml()

    assert "stockmanager-receipt://logo-entreprise" in html


def test_location_receipt_is_a4(qapp) -> None:
    rendered = build_location_receipt_document(_make_location_receipt_data())

    size_mm = rendered.page_size.size(QPageSize.Unit.Millimeter)
    assert round(size_mm.width()) == 210
    assert round(size_mm.height()) == 297


def test_location_receipt_shows_real_billed_total(qapp) -> None:
    rendered = build_location_receipt_document(
        _make_location_receipt_data(total_facture=Decimal("3000"))
    )
    text = rendered.document.toPlainText()

    assert "3 000 FCFA" in text
    assert "Total facturé" in text


def test_location_receipt_shows_balance_due(qapp) -> None:
    rendered = build_location_receipt_document(
        _make_location_receipt_data(
            total_facture=Decimal("3000"), montant_paye=Decimal("1000"),
        )
    )
    text = rendered.document.toPlainText()

    assert "Payé" in text
    assert "Reste à payer" in text


def test_location_receipt_shows_payment_history(qapp) -> None:
    paiements = (
        LocationReceiptPaymentLine(
            date_heure=datetime(2026, 1, 11, 9, 0), montant=Decimal("1000"),
            mode_paiement="Espèces", reference=None, commentaire=None, username="vendeur1",
        ),
    )
    rendered = build_location_receipt_document(
        _make_location_receipt_data(montant_paye=Decimal("1000"), paiements=paiements)
    )
    text = rendered.document.toPlainText()

    assert "HISTORIQUE DES PAIEMENTS" in text
    assert "Espèces" in text


def test_location_receipt_shows_caution_separately_never_added_to_total(qapp) -> None:
    rendered = build_location_receipt_document(
        _make_location_receipt_data(
            total_facture=Decimal("3000"), caution_montant=Decimal("20000"), caution_rendue=Decimal("0"),
        )
    )
    text = rendered.document.toPlainText()

    assert "Caution versée" in text
    assert "Caution restituée" in text


def test_location_receipt_omits_caution_block_when_not_defined(qapp) -> None:
    rendered = build_location_receipt_document(
        _make_location_receipt_data(caution_montant=Decimal("0"))
    )
    text = rendered.document.toPlainText()

    assert "Caution versée" not in text


def test_location_receipt_shows_not_yet_returned_line(qapp) -> None:
    rendered = build_location_receipt_document(
        _make_location_receipt_data(
            lignes=[_make_location_ligne(reference="ART-99", retours=[])],
            total_facture=Decimal("0"),
        )
    )
    text = rendered.document.toPlainText()

    assert "Non encore retourné" in text


def test_location_receipt_single_footer_phrase(qapp) -> None:
    rendered = build_location_receipt_document(
        _make_location_receipt_data(pied_de_page="Merci pour votre confiance et à bientôt !")
    )
    text = rendered.document.toPlainText()

    assert text.count("Merci pour votre confiance et à bientôt !") == 1
    assert "Document généré par StockManager" not in text


def test_location_receipt_shows_client_section_when_present(qapp) -> None:
    rendered = build_location_receipt_document(
        _make_location_receipt_data(client_nom="Jean Dupont")
    )
    text = rendered.document.toPlainText()

    assert "CLIENT" in text
    assert "Jean Dupont" in text


def test_location_receipt_omits_client_section_when_absent(qapp) -> None:
    rendered = build_location_receipt_document(_make_location_receipt_data(client_nom=None))
    text = rendered.document.toPlainText()

    assert "CLIENT" not in text
