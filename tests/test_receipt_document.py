from datetime import date, time
from decimal import Decimal
from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtGui import QPageSize

from app.services.documents.receipt_document import ReceiptFormat, build_receipt_document
from app.services.documents.receipt_service import SaleReceiptData, SaleReceiptLine


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
    # La mention StockManager reste uniquement le petit texte de pied de page,
    # jamais affichée comme s'il s'agissait du nom de l'entreprise cliente.
    assert text.count("StockManager") == 1


def test_footer_mentions_stockmanager_distinctly_from_company_identity(qapp) -> None:
    rendered = build_receipt_document(_make_data(), ReceiptFormat.A4)
    text = rendered.document.toPlainText()

    assert "Document généré par StockManager" in text
    assert "Boutique Étoile SARL" in text
    assert text.index("Boutique Étoile SARL") < text.index("Document généré par StockManager")


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
