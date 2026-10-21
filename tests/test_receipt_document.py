from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtGui import QPageSize

from app.models.enums import StatutPaiement
from app.services.documents.receipt_document import (
    ReceiptFormat,
    build_payment_receipt_document,
    build_receipt_document,
)
from app.services.documents.receipt_service import (
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


# -- Lot 21 : logo redimensionné (40 x 18 mm maximum) ----------------------------------


def test_logo_box_fit_wide_image_is_width_constrained(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(400, 100)  # ratio 4:1, plus large que la boîte (40/18 ~= 2.22)

    assert width_mm == 40.0
    assert round(height_mm, 3) == round(40.0 / 4.0, 3)


def test_logo_box_fit_tall_image_is_height_constrained(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(100, 200)  # ratio 0.5, plus étroit que la boîte

    assert height_mm == 18.0
    assert round(width_mm, 3) == round(18.0 * 0.5, 3)


def test_logo_box_fit_never_exceeds_max_dimensions(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    for width_px, height_px in [(400, 100), (100, 200), (300, 300), (1, 1), (4000, 1)]:
        width_mm, height_mm = _fit_logo_box(width_px, height_px)
        assert width_mm <= 40.0 + 1e-6
        assert height_mm <= 18.0 + 1e-6


def test_logo_box_fit_preserves_aspect_ratio(qapp) -> None:
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, height_mm = _fit_logo_box(200, 50)  # ratio 4:1
    assert round(width_mm / height_mm, 3) == round(200 / 50, 3)


def test_logo_sized_image_is_embedded_with_explicit_dimensions(qapp, tmp_path) -> None:
    """Le logo valide doit porter des attributs width/height explicites
    (jamais une taille fixe arbitraire) — c'est ce qui garantit le respect
    de la boîte 40 x 18 mm quelle que soit la forme de l'image source."""
    logo_path = tmp_path / "logo_wide.png"
    _make_image_file(logo_path, width=400, height=100)
    data = _make_data(entreprise_logo_path=logo_path)

    rendered = build_receipt_document(data, ReceiptFormat.A4)
    html = rendered.document.toHtml()

    assert "<img" in html
    assert 'width="' in html
    assert 'height="' in html


def test_ticket_logo_does_not_overflow_80mm_width(qapp, tmp_path) -> None:
    """Le logo (40 mm maximum) doit toujours tenir dans la largeur de
    contenu du ticket (80 - 2x4 mm de marge = 72 mm) — aucun débordement
    horizontal possible par construction."""
    from app.services.documents.receipt_document import _fit_logo_box

    width_mm, _height_mm = _fit_logo_box(1000, 100)  # image très large
    assert width_mm <= 40.0
    assert width_mm < 72.0  # largeur de contenu du ticket 80 mm


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
