"""Construction du document Qt (``QTextDocument``) d'un reçu de vente, dans
l'un des deux gabarits pris en charge : A4 ou ticket thermique 80 mm.

Indépendant de :class:`ReceiptService` (qui ne connaît aucun format) : ce
module ne fait que transformer un :class:`SaleReceiptData` déjà assemblé en
document imprimable/exportable — aucun accès base de données, aucune
vérification de permission (la donnée fournie a déjà été autorisée par
``ReceiptService.build_sale_receipt``, gardé par ``SALE_VIEW``).

Le logo de l'entreprise cliente est intégré comme ressource du document
(``QTextDocument.addResource``) directement depuis le fichier pointé par
``SaleReceiptData.entreprise_logo_path`` — jamais de fichier temporaire,
et jamais le logo StockManager/SM (``app.resources``), qui n'apparaît nulle
part ici. Redimensionné pour s'inscrire dans une boîte de 40 x 18 mm
maximum en conservant ses proportions (voir ``_fit_logo_box``), toujours
chargé en mémoire (``QImage``, synchrone) avant toute construction du HTML
qui y fait référence — voir ``_add_logo_resource``.

Lot 21 (reçu unifié) : aucune mention publicitaire pour StockManager n'est
plus imprimée sur le reçu (l'ancienne mention « Document généré par
StockManager » a été supprimée, jamais remplacée) — seule une phrase de
pied de reçu configurable par l'entreprise cliente (voir
``SaleReceiptData.pied_de_page``/``_footer_phrase_html``) peut apparaître
en bas du document, et rien du tout si elle est explicitement vidée dans
les paramètres.
"""
from __future__ import annotations

import enum
import html
from dataclasses import dataclass
from decimal import Decimal

from typing import Optional

from PySide6.QtCore import QSizeF, QUrl
from PySide6.QtGui import QImage, QPageSize, QTextDocument

from app.models.enums import StatutPaiement
from app.services.documents.receipt_service import (
    PaymentReceiptData,
    SaleReceiptData,
    SaleReceiptPaymentLine,
)
from app.utils.money import format_money
from app.utils.quantity import format_quantity

_STATUT_PAIEMENT_LABELS = {
    StatutPaiement.NON_PAYEE: "Non payée",
    StatutPaiement.PARTIELLEMENT_PAYEE: "Partiellement payée",
    StatutPaiement.PAYEE: "Payée",
}

# 1 mm en points (unité interne de QTextDocument) : 72 pt/pouce, 25.4 mm/pouce.
_MM_TO_POINTS = 72.0 / 25.4

_A4_WIDTH_MM = 210.0
_A4_MARGIN_MM = 15.0

_TICKET_WIDTH_MM = 80.0
_TICKET_MARGIN_MM = 4.0
_TICKET_MIN_HEIGHT_MM = 40.0
# Marge de sécurité ajoutée à la hauteur mesurée (arrondi de mise en page,
# évite qu'une dernière ligne ne soit coupée sur l'imprimante physique).
_TICKET_HEIGHT_BUFFER_MM = 8.0

_LOGO_RESOURCE_URL = QUrl("stockmanager-receipt://logo-entreprise")

# Taille d'impression maximale du logo (décision déjà actée, Lot 21) :
# 40 x 18 mm, proportions toujours conservées — jamais déformé, jamais agrandi
# au-delà de cette boîte. 40 mm reste largement inférieur à la largeur de
# contenu d'un ticket 80 mm (80 - 2x4 mm de marge = 72 mm) : aucun débordement
# horizontal possible sur ce format.
_LOGO_MAX_WIDTH_MM = 40.0
_LOGO_MAX_HEIGHT_MM = 18.0


class ReceiptFormat(enum.Enum):
    A4 = "A4"
    TICKET_80MM = "TICKET_80MM"


@dataclass
class RenderedReceipt:
    """Document prêt à imprimer/exporter, avec la taille de page adaptée au
    format choisi (fixe pour A4, calculée dynamiquement pour le ticket)."""

    document: QTextDocument
    page_size: QPageSize
    margin_mm: float


def _fmt_money(amount: Decimal, devise: str) -> str:
    return html.escape(format_money(amount, devise))


def _esc(value) -> str:
    return html.escape(str(value)) if value else ""


def _fit_logo_box(image_width_px: int, image_height_px: int) -> tuple[float, float]:
    """Calcule la largeur/hauteur (mm) du logo pour qu'il s'inscrive dans la
    boîte ``_LOGO_MAX_WIDTH_MM`` x ``_LOGO_MAX_HEIGHT_MM`` en conservant ses
    proportions réelles — jamais de déformation, jamais de dépassement d'une
    des deux dimensions. Fonction pure, indépendante de Qt, pour rester
    testable sans document ni image réelle."""
    if image_width_px <= 0 or image_height_px <= 0:
        return (0.0, 0.0)
    aspect = image_width_px / image_height_px
    box_aspect = _LOGO_MAX_WIDTH_MM / _LOGO_MAX_HEIGHT_MM
    if aspect >= box_aspect:
        width_mm = _LOGO_MAX_WIDTH_MM
        height_mm = _LOGO_MAX_WIDTH_MM / aspect
    else:
        height_mm = _LOGO_MAX_HEIGHT_MM
        width_mm = _LOGO_MAX_HEIGHT_MM * aspect
    return (width_mm, height_mm)


def _add_logo_resource(document: QTextDocument, data: SaleReceiptData) -> Optional[tuple[float, float]]:
    """Charge le logo client (s'il existe) comme ressource du document
    **avant** toute construction du HTML (voir ``build_receipt_document`` :
    l'ordre d'appel garantit que l'image est entièrement chargée — ``QImage``
    décode le fichier de façon synchrone, aucun chargement différé — avant
    que ``QTextDocument.setHtml`` ne résolve la balise ``<img>`` qui y fait
    référence ; c'est cet ordre, pas un mécanisme supplémentaire, qui évite
    qu'un logo chargé trop tard disparaisse à l'impression.

    Retourne ``None`` silencieusement si le fichier est absent/illisible —
    un logo manquant ou invalide ne doit jamais empêcher la génération du
    reçu (§6 du cahier des charges de ce lot) — sinon la taille (largeur,
    hauteur) en points à appliquer explicitement sur la balise ``<img>``
    pour respecter la boîte 40 x 18 mm en conservant les proportions
    (Lot 21, voir ``_fit_logo_box``)."""
    if data.entreprise_logo_path is None or not data.entreprise_logo_path.exists():
        return None
    image = QImage(str(data.entreprise_logo_path))
    if image.isNull():
        return None
    document.addResource(QTextDocument.ResourceType.ImageResource, _LOGO_RESOURCE_URL, image)
    width_mm, height_mm = _fit_logo_box(image.width(), image.height())
    return (width_mm * _MM_TO_POINTS, height_mm * _MM_TO_POINTS)


def _header_lines(data: SaleReceiptData) -> list[str]:
    lines = []
    if data.entreprise_adresse:
        lines.append(_esc(data.entreprise_adresse))
    if data.entreprise_telephone:
        lines.append(f"Tél. {_esc(data.entreprise_telephone)}")
    if data.entreprise_email:
        lines.append(_esc(data.entreprise_email))
    return lines


def _client_fields(data: SaleReceiptData) -> list[tuple[str, str]]:
    """Paires (étiquette, valeur) des champs client optionnels réellement
    renseignés — un client peut exister sans qu'aucun de ces champs ne soit
    rempli. Même principe que ``_header_lines`` pour le profil entreprise."""
    fields = []
    if data.client_telephone:
        fields.append(("Téléphone", _esc(data.client_telephone)))
    if data.client_adresse:
        fields.append(("Adresse", _esc(data.client_adresse)))
    if data.client_email:
        fields.append(("Email", _esc(data.client_email)))
    return fields


def _date_heure_text(data: SaleReceiptData) -> str:
    text = str(data.date)
    if data.heure is not None:
        text += f" à {data.heure.strftime('%H:%M')}"
    return text


def _payment_rows_a4(data: SaleReceiptData) -> str:
    """Bloc Payé/Reste/Statut (§5.8), toujours affiché — une vente comptant
    affiche « Reste : 0 » au même titre qu'une vente partiellement payée,
    sans distinction de traitement."""
    statut_label = _STATUT_PAIEMENT_LABELS.get(data.statut_paiement, str(data.statut_paiement))
    return f"""
    <p align="right" style="margin:2px 0;">Payé : {_fmt_money(data.montant_paye, data.devise)}</p>
    <p align="right" style="margin:2px 0;">Reste à payer : {_fmt_money(data.reste_a_payer, data.devise)}</p>
    <p align="right" style="margin:2px 0; font-weight:600;">Statut : {_esc(statut_label)}</p>
    """


def _payment_rows_ticket(data: SaleReceiptData) -> str:
    statut_label = _STATUT_PAIEMENT_LABELS.get(data.statut_paiement, str(data.statut_paiement))
    return f"""
    <table width="100%" cellspacing="0" cellpadding="0">
      <tr><td>Payé</td><td align="right">{_fmt_money(data.montant_paye, data.devise)}</td></tr>
      <tr><td>Reste à payer</td><td align="right">{_fmt_money(data.reste_a_payer, data.devise)}</td></tr>
      <tr><td><b>Statut</b></td><td align="right"><b>{_esc(statut_label)}</b></td></tr>
    </table>
    """


def _footer_phrase_html(data: SaleReceiptData, font_size_pt: int) -> str:
    """Phrase de pied de reçu configurable (Lot 21) — jamais de texte publi-
    citaire pour le logiciel (la mention « Document généré par StockManager »
    est supprimée, pas remplacée) : seule une phrase destinée au client,
    configurable dans Paramètres, et rien du tout si elle a été explicitement
    vidée (voir ``CompanySettingsConfig.recu_pied_de_page``)."""
    if not data.pied_de_page:
        return ""
    return (
        f'<p align="center" style="margin-top:20px; font-size:{font_size_pt}pt;">'
        f"{_esc(data.pied_de_page)}</p>"
    )


def _payment_history_row_a4(p: SaleReceiptPaymentLine, devise: str) -> str:
    row = (
        f"<tr>"
        f"<td>{_esc(p.date_heure.strftime('%Y-%m-%d %H:%M'))}</td>"
        f"<td align='right'>{_fmt_money(p.montant, devise)}</td>"
        f"<td>{_esc(p.mode_paiement) or '—'}</td>"
        f"<td>{_esc(p.reference) or '—'}</td>"
        f"<td>{_esc(p.username)}</td>"
        f"</tr>"
    )
    if p.commentaire:
        row += (
            f"<tr><td colspan='5' style='font-style:italic; color:#555555;'>"
            f"{_esc(p.commentaire)}</td></tr>"
        )
    return row


def _payment_history_section_a4(data: SaleReceiptData) -> str:
    """Historique complet des paiements (Lot 21), distinct du bloc
    Payé/Reste/Statut ci-dessus — jamais affiché si la vente n'a reçu aucun
    paiement (aucun titre, aucune table vide réservée, même convention que
    ``_client_section_html_a4``)."""
    if not data.paiements:
        return ""
    rows = "".join(_payment_history_row_a4(p, data.devise) for p in data.paiements)
    return f"""
    <p style="margin:16px 0 4px 0; font-weight:600;">HISTORIQUE DES PAIEMENTS</p>
    <table width="100%" border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse; font-size:8pt;">
      <tr style="background-color:#eeeeee;">
        <th align="left">Date</th>
        <th align="right">Montant</th>
        <th align="left">Mode</th>
        <th align="left">Référence</th>
        <th align="left">Enregistré par</th>
      </tr>
      {rows}
    </table>
    """


def _payment_history_row_ticket(p: SaleReceiptPaymentLine, devise: str) -> str:
    parts = [
        "<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td>{_esc(p.date_heure.strftime('%Y-%m-%d %H:%M'))}</td>"
        f"<td align='right'>{_fmt_money(p.montant, devise)}</td>"
        "</tr></table>"
    ]
    extra = [value for value in (_esc(p.mode_paiement), _esc(p.reference)) if value]
    if extra:
        parts.append(f"<p style='margin:0 0 2px 0; font-size:7pt;'>{' · '.join(extra)}</p>")
    if p.commentaire:
        parts.append(
            f"<p style='margin:0 0 4px 0; font-size:7pt; font-style:italic;'>{_esc(p.commentaire)}</p>"
        )
    return "".join(parts)


def _payment_history_section_ticket(data: SaleReceiptData) -> str:
    if not data.paiements:
        return ""
    rows = "".join(_payment_history_row_ticket(p, data.devise) for p in data.paiements)
    return f"""
    <p align="center">------------------------------</p>
    <p style="margin:2px 0; font-weight:600;">Historique des paiements</p>
    {rows}
    """


def _client_section_html_a4(data: SaleReceiptData) -> str:
    """Bloc CLIENT distinct (§4 de ce lot) — chaîne vide si aucun client
    n'est associé à la vente : aucun titre, aucun espace réservé."""
    if not data.client_nom:
        return ""
    extra_rows = "".join(
        f"<p style='margin:0;'>{label} : {value}</p>" for label, value in _client_fields(data)
    )
    return f"""
    <p style="margin:16px 0 4px 0; font-weight:600;">CLIENT</p>
    <p style="margin:0;">Nom : {_esc(data.client_nom)}</p>
    {extra_rows}
    """


def _build_a4_html(data: SaleReceiptData, logo_size: Optional[tuple[float, float]]) -> str:
    logo_html = ""
    if logo_size is not None:
        width_pt, height_pt = logo_size
        logo_html = (
            f'<img src="{_LOGO_RESOURCE_URL.toString()}" '
            f'width="{width_pt:.1f}" height="{height_pt:.1f}">'
        )
    entreprise_nom = _esc(data.entreprise_nom) or "(Entreprise non configurée — voir Paramètres)"
    header_lines = "<br/>".join(_header_lines(data)) or "&nbsp;"
    client_section = _client_section_html_a4(data)

    rows = "".join(
        f"<tr>"
        f"<td>{_esc(l.article_reference)} — {_esc(l.article_designation)}</td>"
        f"<td align='center'>{_esc(format_quantity(l.quantite))}</td>"
        f"<td align='right'>{_fmt_money(l.prix_unitaire, data.devise)}</td>"
        f"<td align='right'>{_fmt_money(l.sous_total, data.devise)}</td>"
        f"</tr>"
        for l in data.lignes
    )

    return f"""
    <div style="font-size:10pt;">
    <table width="100%" cellspacing="0" cellpadding="0">
      <tr>
        <td width="55%" valign="top">
          {logo_html}
          <h2 style="margin:4px 0;">{entreprise_nom}</h2>
          <p style="margin:0;">{header_lines}</p>
        </td>
        <td width="45%" valign="top" align="right">
          <h1 style="margin:0;">REÇU</h1>
          <p style="margin:4px 0;">
            N° {_esc(data.numero)}<br/>
            Date : {_esc(_date_heure_text(data))}<br/>
            Vendeur : {_esc(data.username)}
          </p>
        </td>
      </tr>
    </table>
    <hr/>
    {client_section}
    <table width="100%" border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;">
      <tr style="background-color:#eeeeee;">
        <th align="left">Article</th>
        <th align="center">Qté</th>
        <th align="right">Prix unitaire</th>
        <th align="right">Montant</th>
      </tr>
      {rows}
    </table>
    <h2 align="right" style="margin-top:16px;">Total : {_fmt_money(data.total, data.devise)}</h2>
    {_payment_rows_a4(data)}
    {_payment_history_section_a4(data)}
    {_footer_phrase_html(data, font_size_pt=9)}
    </div>
    """


def _client_block_ticket(data: SaleReceiptData) -> str:
    """Bloc client compact (§5 de ce lot) — chaîne vide si aucun client
    n'est associé : le ticket reste plus court, sans ligne réservée."""
    if not data.client_nom:
        return ""
    parts = [f"Client : {_esc(data.client_nom)}"]
    for label, value in _client_fields(data):
        parts.append(f"{label} : {value}")
    return f"<p style='margin:2px 0;'>{'<br/>'.join(parts)}</p>"


def _build_ticket_html(data: SaleReceiptData, logo_size: Optional[tuple[float, float]]) -> str:
    logo_html = ""
    if logo_size is not None:
        width_pt, height_pt = logo_size
        logo_html = (
            '<p align="center">'
            f'<img src="{_LOGO_RESOURCE_URL.toString()}" width="{width_pt:.1f}" height="{height_pt:.1f}">'
            "</p>"
        )
    entreprise_nom = _esc(data.entreprise_nom) or "(Entreprise non configurée)"
    header_lines = "<br/>".join(_header_lines(data))
    client_block = _client_block_ticket(data)

    lines_html = "".join(
        f"<p style='margin:2px 0;'>{_esc(l.article_reference)} — {_esc(l.article_designation)}</p>"
        f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td>{_esc(format_quantity(l.quantite))} x {_fmt_money(l.prix_unitaire, data.devise)}</td>"
        f"<td align='right'>{_fmt_money(l.sous_total, data.devise)}</td>"
        f"</tr></table>"
        for l in data.lignes
    )

    return f"""
    <div style="font-family:monospace; font-size:8pt;">
      <p align="center" style="margin:2px 0;"><b>{entreprise_nom}</b></p>
      <p align="center" style="margin:2px 0;">{header_lines}</p>
      {logo_html}
      <p align="center">------------------------------</p>
      <p style="margin:2px 0;">
        Reçu N° {_esc(data.numero)}<br/>
        {_esc(_date_heure_text(data))}<br/>
        Vendeur : {_esc(data.username)}
      </p>
      {client_block}
      <p align="center">------------------------------</p>
      {lines_html}
      <p align="center">------------------------------</p>
      <table width="100%" cellspacing="0" cellpadding="0"><tr>
        <td><b>TOTAL</b></td>
        <td align="right"><b>{_fmt_money(data.total, data.devise)}</b></td>
      </tr></table>
      {_payment_rows_ticket(data)}
      {_payment_history_section_ticket(data)}
      {_footer_phrase_html(data, font_size_pt=8)}
    </div>
    """


def _measure_ticket_height_mm(document: QTextDocument, content_width_mm: float) -> float:
    """Mesure en deux passes la hauteur réellement nécessaire pour afficher
    tout le contenu du ticket à largeur fixe (80 mm moins marges) : un
    ticket thermique n'a pas de hauteur de page prédéfinie (rouleau
    continu), contrairement à A4 — Qt exige pourtant toujours une taille de
    page définie pour imprimer/exporter. La hauteur suit donc automatiquement
    le nombre de lignes de la vente."""
    document.setTextWidth(content_width_mm * _MM_TO_POINTS)
    height_points = document.size().height()
    height_mm = height_points / _MM_TO_POINTS
    return max(height_mm + _TICKET_HEIGHT_BUFFER_MM, _TICKET_MIN_HEIGHT_MM)


def _build_payment_receipt_html(data: PaymentReceiptData) -> str:
    """Reçu d'un paiement ultérieur (§5.8) — document A4 volontairement
    compact : pas de lignes d'articles, seulement la trace du règlement."""
    entreprise_nom = _esc(data.entreprise_nom) or "(Entreprise non configurée — voir Paramètres)"
    header_lines = "<br/>".join(
        line for line in (
            _esc(data.entreprise_adresse), f"Tél. {_esc(data.entreprise_telephone)}" if data.entreprise_telephone else "",
            _esc(data.entreprise_email),
        ) if line
    ) or "&nbsp;"
    client_line = f"<p style='margin:4px 0;'>Client : {_esc(data.client_nom)}</p>" if data.client_nom else ""
    # Mêmes informations déjà visibles dans l'historique à l'écran
    # (SaleDetailDialog.payments_table) — n'apparaissent ici que si
    # renseignées, jamais une ligne vide/« — » (même convention que
    # _header_lines/_client_fields pour le reçu de vente).
    mode_paiement_line = (
        f"<p style='margin:4px 0;'>Mode de paiement : {_esc(data.mode_paiement)}</p>" if data.mode_paiement else ""
    )
    reference_line = (
        f"<p style='margin:4px 0;'>Référence : {_esc(data.reference)}</p>" if data.reference else ""
    )

    return f"""
    <h2 style="margin:4px 0;">{entreprise_nom}</h2>
    <p style="margin:0;">{header_lines}</p>
    <hr/>
    <h1 style="margin:16px 0;">REÇU DE PAIEMENT</h1>
    <p style="margin:4px 0;">
      Vente concernée : {_esc(data.vente_numero)}<br/>
      Date du paiement : {_esc(data.date_heure.strftime('%Y-%m-%d à %H:%M'))}<br/>
      Enregistré par : {_esc(data.username)}
    </p>
    {client_line}
    <hr/>
    <p style="margin:4px 0; font-size:14pt; font-weight:600;">
      Montant payé : {_fmt_money(data.montant, data.devise)}
    </p>
    {mode_paiement_line}
    {reference_line}
    <p style="margin:4px 0;">Total de la vente : {_fmt_money(data.total_vente, data.devise)}</p>
    <p style="margin:4px 0;">Total payé après ce paiement : {_fmt_money(data.total_paye_apres, data.devise)}</p>
    <p style="margin:4px 0; font-weight:600;">Reste à payer : {_fmt_money(data.reste_a_payer, data.devise)}</p>
    """


def build_payment_receipt_document(data: PaymentReceiptData) -> RenderedReceipt:
    """Construit le document (format A4 uniquement — §5.8 ne demande pas de
    variante ticket thermique pour un reçu de paiement) du reçu d'un
    paiement ultérieur. Pure fonction de rendu, comme
    ``build_receipt_document``."""
    document = QTextDocument()
    document.setHtml(_build_payment_receipt_html(data))
    page_size = QPageSize(QPageSize.PageSizeId.A4)
    return RenderedReceipt(document=document, page_size=page_size, margin_mm=_A4_MARGIN_MM)


def build_receipt_document(data: SaleReceiptData, receipt_format: ReceiptFormat) -> RenderedReceipt:
    """Construit le ``QTextDocument`` et la taille de page correspondant au
    format demandé. Ne modifie jamais ``data`` ni quoi que ce soit en base :
    pure fonction de rendu."""
    document = QTextDocument()
    logo_size = _add_logo_resource(document, data)

    if receipt_format is ReceiptFormat.A4:
        document.setHtml(_build_a4_html(data, logo_size))
        page_size = QPageSize(QPageSize.PageSizeId.A4)
        return RenderedReceipt(document=document, page_size=page_size, margin_mm=_A4_MARGIN_MM)

    if receipt_format is ReceiptFormat.TICKET_80MM:
        document.setHtml(_build_ticket_html(data, logo_size))
        content_width_mm = _TICKET_WIDTH_MM - 2 * _TICKET_MARGIN_MM
        height_mm = _measure_ticket_height_mm(document, content_width_mm)
        page_size = QPageSize(QSizeF(_TICKET_WIDTH_MM, height_mm), QPageSize.Unit.Millimeter)
        return RenderedReceipt(document=document, page_size=page_size, margin_mm=_TICKET_MARGIN_MM)

    raise ValueError(f"Format de reçu non pris en charge : {receipt_format!r}")
