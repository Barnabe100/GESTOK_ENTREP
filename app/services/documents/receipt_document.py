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

from typing import Optional, Union

from PySide6.QtCore import QSizeF, QUrl
from PySide6.QtGui import QImage, QPageSize, QTextDocument

from app.models.enums import StatutLocation, StatutPaiement
from app.services.documents.receipt_service import (
    LocationReceiptData,
    LocationReservationVoucherData,
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

# Même duplication déjà acceptée que ``_STATUT_PAIEMENT_LABELS`` ci-dessus
# par rapport à ``sale_detail_dialog.py`` : ce module ne doit jamais
# dépendre d'un module de vue (architecture View -> Service), donc jamais
# d'import de ``locations_page.py``/``location_detail_dialog.py`` ici,
# quitte à reprendre le même libellé.
_STATUT_LOCATION_LABELS = {
    StatutLocation.BROUILLON: "Brouillon",
    StatutLocation.CONFIRMEE: "Confirmée",
    StatutLocation.EN_COURS: "En cours",
    StatutLocation.RETOURNEE: "Retournée",
    StatutLocation.ANNULEE: "Annulée",
}

# Lot 22 (§F) : ``_add_logo_resource``/``_footer_phrase_html``/``_header_lines``/
# ``_client_fields``/``_client_section_html_a4`` ci-dessous ne lisent que des
# champs volontairement nommés à l'identique sur les trois DTO (voir
# ``receipt_service.py``) : réutilisés tels quels pour les deux documents de
# location, jamais dupliqués.
_ReceiptLike = Union[SaleReceiptData, LocationReservationVoucherData, LocationReceiptData]

# 1 mm en points (unité interne de QTextDocument) : 72 pt/pouce, 25.4 mm/pouce.
_MM_TO_POINTS = 72.0 / 25.4

_A4_WIDTH_MM = 210.0
_A4_MARGIN_MM = 15.0

_TICKET_WIDTH_MM = 80.0
_TICKET_MARGIN_MM = 4.0
_TICKET_MIN_HEIGHT_MM = 40.0
# Marge de sécurité ajoutée à la hauteur mesurée (arrondi de mise en page,
# évite qu'une dernière ligne ne soit coupée sur l'imprimante physique) —
# ajoutée APRÈS vérification par ``document.pageCount()`` (voir
# ``_measure_ticket_height_mm``), jamais à sa place : elle ne couvre plus
# qu'un résidu (métriques de police légèrement différentes entre la mesure
# et l'impression réelle), plus la cause structurelle du double-page
# (Lot 23, anomalie A).
_TICKET_HEIGHT_BUFFER_MM = 8.0
# Lot 23 (anomalie A) : nombre maximal de tentatives et incrément utilisés
# pour faire converger la hauteur candidate vers une page unique selon
# ``document.pageCount()`` — jamais une boucle non bornée. 20 tentatives à
# 5 mm couvrent une marge de 100 mm au-delà de l'estimation initiale,
# largement suffisant en pratique (l'estimation initiale, basée sur la
# mesure réelle du contenu, n'est habituellement déjà qu'à quelques
# millimètres de la valeur correcte) ; au-delà, le contenu est considéré
# comme nécessitant légitimement plusieurs pages (jamais forcé sur une
# seule à n'importe quel prix).
_TICKET_PAGE_FIT_MAX_ATTEMPTS = 20
_TICKET_PAGE_FIT_INCREMENT_MM = 5.0

_LOGO_RESOURCE_URL = QUrl("stockmanager-receipt://logo-entreprise")

# Lot 23 (§C) : boîte maximale distincte par format — un ticket 80 mm ne
# doit pas accepter un logo aussi grand qu'un document A4, même si 40 mm
# de large tiendrait techniquement dans les 72 mm de contenu disponibles
# (80 - 2x4 mm de marge). Proportions toujours conservées — jamais déformé,
# jamais agrandi au-delà de la boîte (voir ``_fit_logo_box``).
_LOGO_MAX_WIDTH_TICKET_MM = 30.0
_LOGO_MAX_HEIGHT_TICKET_MM = 15.0
_LOGO_MAX_WIDTH_A4_MM = 40.0
_LOGO_MAX_HEIGHT_A4_MM = 20.0

# Lot 23 (§C) : seuil de qualité d'impression retenu pour ne jamais agrandir
# un logo de faible résolution au-delà de sa taille « naturelle » à cette
# définition — un logo dont la taille naturelle à 150 DPI est déjà plus
# petite que la boîte maximale n'est jamais étiré pour la remplir (ce qui
# dégraderait sa netteté) ; seul un logo dont la taille naturelle dépasse la
# boîte est réduit, comme avant. 150 DPI est un seuil de qualité d'impression
# courant (documenté dans le rapport d'analyse de ce lot), jamais une limite
# de résolution en pixels imposée à l'import (voir ``company_settings_service``).
_LOGO_MIN_RENDER_DPI = 150.0
_MM_PER_INCH = 25.4

# Lot 22 (anomalie D) : échelle typographique explicite du ticket 80 mm,
# posée directement sur chaque élément — y compris les tables — plutôt que
# sur le seul <div> englobant. Un <table>/<td>/<th> HTML n'hérite pas
# fiablement du ``font-size`` d'un ancêtre dans le sous-ensemble de rendu
# riche de ``QTextDocument` : c'est précisément ce qui expliquait que la
# réduction de 9 pt à 8 pt du Lot 21 restait invisible sur les lignes
# d'articles et les montants, qui vivent tous dans des tables. Une seule
# échelle, documentée ici et réutilisée pour chaque type de contenu
# (y compris, Lot 22 §8.3, le futur reçu de location) plutôt que des
# corrections ponctuelles :
#   - HEADER  : nom de l'entreprise (identité, légèrement mis en avant) ;
#   - BODY    : texte courant (coordonnées, numéro, date, vendeur, client) ;
#   - ARTICLE : lignes d'articles (désignation/quantité/prix/montant) —
#               la majorité du contenu, doit rester la plus compacte ;
#   - TOTAL   : montant total du document — seul élément volontairement
#               plus grand que le texte courant, pour rester immédiatement
#               visible malgré la réduction générale ;
#   - SUMMARY : bloc Payé/Reste à payer/Statut ;
#   - HISTORY : historique des paiements (information secondaire, la plus
#               petite taille du ticket) ;
#   - FOOTER  : pied de reçu configurable.
_TICKET_FONT_HEADER_PT = 9
_TICKET_FONT_BODY_PT = 8
_TICKET_FONT_ARTICLE_PT = 7.5
_TICKET_FONT_TOTAL_PT = 10
_TICKET_FONT_SUMMARY_PT = 7.5
_TICKET_FONT_HISTORY_PT = 7
_TICKET_FONT_FOOTER_PT = 8


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


def _fit_logo_box(
    image_width_px: int, image_height_px: int, max_width_mm: float, max_height_mm: float
) -> tuple[float, float]:
    """Calcule la largeur/hauteur (mm) du logo pour qu'il s'inscrive dans la
    boîte ``max_width_mm`` x ``max_height_mm`` (propre à chaque format, voir
    ``_LOGO_MAX_*_MM``) en conservant ses proportions réelles — jamais de
    déformation, jamais de dépassement d'une des deux dimensions.

    Lot 23 (§C) : si la taille « naturelle » de l'image à
    ``_LOGO_MIN_RENDER_DPI`` est déjà plus petite que la boîte dans les deux
    dimensions, cette taille naturelle est conservée telle quelle plutôt que
    d'agrandir l'image pour remplir la boîte — un logo de faible résolution
    n'est jamais étiré au-delà de sa définition réelle, ce qui dégraderait
    sa netteté. Seul un logo dont la taille naturelle dépasse la boîte est
    réduit pour y tenir, comme avant. Fonction pure, indépendante de Qt,
    pour rester testable sans document ni image réelle."""
    if image_width_px <= 0 or image_height_px <= 0:
        return (0.0, 0.0)

    aspect = image_width_px / image_height_px
    box_aspect = max_width_mm / max_height_mm
    if aspect >= box_aspect:
        fitted_width_mm = max_width_mm
        fitted_height_mm = max_width_mm / aspect
    else:
        fitted_height_mm = max_height_mm
        fitted_width_mm = max_height_mm * aspect

    natural_width_mm = (image_width_px / _LOGO_MIN_RENDER_DPI) * _MM_PER_INCH
    natural_height_mm = (image_height_px / _LOGO_MIN_RENDER_DPI) * _MM_PER_INCH
    if natural_width_mm <= max_width_mm and natural_height_mm <= max_height_mm:
        return (natural_width_mm, natural_height_mm)
    return (fitted_width_mm, fitted_height_mm)


def _add_logo_resource(
    document: QTextDocument, data: _ReceiptLike, max_width_mm: float, max_height_mm: float
) -> Optional[tuple[float, float]]:
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
    pour respecter la boîte ``max_width_mm`` x ``max_height_mm`` (propre au
    format appelant, voir ``_fit_logo_box``) en conservant les proportions."""
    if data.entreprise_logo_path is None or not data.entreprise_logo_path.exists():
        return None
    image = QImage(str(data.entreprise_logo_path))
    if image.isNull():
        return None
    document.addResource(QTextDocument.ResourceType.ImageResource, _LOGO_RESOURCE_URL, image)
    width_mm, height_mm = _fit_logo_box(image.width(), image.height(), max_width_mm, max_height_mm)
    return (width_mm * _MM_TO_POINTS, height_mm * _MM_TO_POINTS)


def _logo_html(logo_size: Optional[tuple[float, float]]) -> str:
    """Construit la balise ``<img>`` du logo, toujours centrée horizontalement
    (Lot 23, §C) — point de construction unique réutilisé par les quatre
    gabarits (reçu de vente A4/ticket, justificatif de réservation, reçu de
    location), jamais dupliqué. Chaîne vide si aucun logo (voir
    ``_add_logo_resource``) : jamais d'espace réservé vide."""
    if logo_size is None:
        return ""
    width_pt, height_pt = logo_size
    return (
        '<p align="center" style="margin:2px 0;">'
        f'<img src="{_LOGO_RESOURCE_URL.toString()}" width="{width_pt:.1f}" height="{height_pt:.1f}">'
        "</p>"
    )


def _header_lines(data: _ReceiptLike) -> list[str]:
    lines = []
    if data.entreprise_adresse:
        lines.append(_esc(data.entreprise_adresse))
    if data.entreprise_telephone:
        lines.append(f"Tél. {_esc(data.entreprise_telephone)}")
    if data.entreprise_email:
        lines.append(_esc(data.entreprise_email))
    return lines


def _client_fields(data: _ReceiptLike) -> list[tuple[str, str]]:
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
    """Bloc Payé/Reste/Statut puis, séparément, le total — toujours mis en
    évidence à une taille supérieure (``_TICKET_FONT_TOTAL_PT``) juste
    avant ce bloc (voir ``_build_ticket_html``), jamais confondu avec un
    paiement individuel ci-dessous."""
    statut_label = _STATUT_PAIEMENT_LABELS.get(data.statut_paiement, str(data.statut_paiement))
    return f"""
    <table width="100%" cellspacing="0" cellpadding="0" style="font-size:{_TICKET_FONT_SUMMARY_PT}pt;">
      <tr><td>Payé</td><td align="right">{_fmt_money(data.montant_paye, data.devise)}</td></tr>
      <tr><td>Reste à payer</td><td align="right">{_fmt_money(data.reste_a_payer, data.devise)}</td></tr>
      <tr><td><b>Statut</b></td><td align="right"><b>{_esc(statut_label)}</b></td></tr>
    </table>
    """


def _footer_phrase_html(data: _ReceiptLike, font_size_pt: int) -> str:
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
        f"<table width='100%' cellspacing='0' cellpadding='0' style='font-size:{_TICKET_FONT_HISTORY_PT}pt;'><tr>"
        f"<td>{_esc(p.date_heure.strftime('%Y-%m-%d %H:%M'))}</td>"
        f"<td align='right'>{_fmt_money(p.montant, devise)}</td>"
        "</tr></table>"
    ]
    extra = [value for value in (_esc(p.mode_paiement), _esc(p.reference)) if value]
    if extra:
        parts.append(
            f"<p style='margin:0 0 2px 0; font-size:{_TICKET_FONT_HISTORY_PT}pt;'>{' · '.join(extra)}</p>"
        )
    if p.commentaire:
        parts.append(
            f"<p style='margin:0 0 4px 0; font-size:{_TICKET_FONT_HISTORY_PT}pt; font-style:italic;'>"
            f"{_esc(p.commentaire)}</p>"
        )
    return "".join(parts)


def _payment_history_section_ticket(data: SaleReceiptData) -> str:
    if not data.paiements:
        return ""
    rows = "".join(_payment_history_row_ticket(p, data.devise) for p in data.paiements)
    return f"""
    <p align="center">------------------------------</p>
    <p style="margin:2px 0; font-weight:600; font-size:{_TICKET_FONT_BODY_PT}pt;">Historique des paiements</p>
    {rows}
    """


def _client_section_html_a4(data: _ReceiptLike) -> str:
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
    logo_html = _logo_html(logo_size)
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
    return (
        f"<p style='margin:2px 0; font-size:{_TICKET_FONT_BODY_PT}pt;'>{'<br/>'.join(parts)}</p>"
    )


def _build_ticket_html(data: SaleReceiptData, logo_size: Optional[tuple[float, float]]) -> str:
    logo_html = _logo_html(logo_size)
    entreprise_nom = _esc(data.entreprise_nom) or "(Entreprise non configurée)"
    header_lines = "<br/>".join(_header_lines(data))
    client_block = _client_block_ticket(data)
    # Lot 23 (§F — reprise de l'ordre canonique) : un séparateur précède
    # toujours le pied de page configurable, mais uniquement s'il y a
    # réellement un pied de page à afficher — jamais un séparateur isolé
    # sans contenu après (même convention que les autres sections
    # optionnelles de ce document).
    footer_html = _footer_phrase_html(data, font_size_pt=_TICKET_FONT_FOOTER_PT)
    footer_separator = '<p align="center">------------------------------</p>' if footer_html else ""

    # Lignes d'articles (Lot 22, anomalie D) : taille explicite sur le
    # paragraphe de désignation ET sur la table quantité/prix/montant —
    # c'est précisément cette table qui ne réduisait pas visuellement
    # malgré le <div> englobant à 8 pt.
    lines_html = "".join(
        f"<p style='margin:2px 0; font-size:{_TICKET_FONT_ARTICLE_PT}pt;'>"
        f"{_esc(l.article_reference)} — {_esc(l.article_designation)}</p>"
        f"<table width='100%' cellspacing='0' cellpadding='0' style='font-size:{_TICKET_FONT_ARTICLE_PT}pt;'><tr>"
        f"<td>{_esc(format_quantity(l.quantite))} x {_fmt_money(l.prix_unitaire, data.devise)}</td>"
        f"<td align='right'>{_fmt_money(l.sous_total, data.devise)}</td>"
        f"</tr></table>"
        for l in data.lignes
    )

    return f"""
    <div style="font-family:monospace; font-size:{_TICKET_FONT_BODY_PT}pt;">
      {logo_html}
      <p align="center" style="margin:2px 0; font-size:{_TICKET_FONT_HEADER_PT}pt;"><b>{entreprise_nom}</b></p>
      <p align="center" style="margin:2px 0; font-size:{_TICKET_FONT_BODY_PT}pt;">{header_lines}</p>
      <p align="center">------------------------------</p>
      <p style="margin:2px 0; font-size:{_TICKET_FONT_BODY_PT}pt;">
        Reçu N° {_esc(data.numero)}<br/>
        {_esc(_date_heure_text(data))}<br/>
        Vendeur : {_esc(data.username)}
      </p>
      {client_block}
      <p align="center">------------------------------</p>
      {lines_html}
      <p align="center">------------------------------</p>
      <table width="100%" cellspacing="0" cellpadding="0" style="font-size:{_TICKET_FONT_TOTAL_PT}pt;"><tr>
        <td><b>TOTAL</b></td>
        <td align="right"><b>{_fmt_money(data.total, data.devise)}</b></td>
      </tr></table>
      {_payment_rows_ticket(data)}
      {_payment_history_section_ticket(data)}
      {footer_separator}
      {footer_html}
    </div>
    """


def _measure_ticket_height_mm(document: QTextDocument, content_width_mm: float) -> float:
    """Mesure la hauteur réellement nécessaire pour afficher tout le contenu
    du ticket sur une seule page à largeur fixe (80 mm moins marges) : un
    ticket thermique n'a pas de hauteur de page prédéfinie (rouleau
    continu), contrairement à A4 — Qt exige pourtant toujours une taille de
    page définie pour imprimer/exporter. La hauteur suit donc automatiquement
    le nombre de lignes de la vente.

    Lot 23 (anomalie A) : une simple mesure en mode page infinie
    (``setTextWidth`` seul, sans ``setPageSize``) ne garantit pas d'obtenir
    la même hauteur que celle que Qt calculera réellement à l'impression —
    ``document.print_(printer)`` utilise toujours le mode paginé, qui peut
    repousser un bloc entier (typiquement le pied de page, isolé par une
    marge avant lui) sur une seconde page même pour un écart minime, par
    exemple entre les métriques de police de l'environnement de mesure et
    celles réellement utilisées au moment d'imprimer. C'est précisément ce
    qui provoquait un reçu court sur deux pages sous Windows alors que la
    mesure semblait correcte.

    La correction utilise donc le même mode paginé que l'impression réelle
    comme référence : on configure ``document.setPageSize(...)`` à une
    hauteur candidate puis on vérifie ``document.pageCount()`` — jamais une
    estimation indirecte seule. Si plus d'une page est nécessaire, la
    hauteur candidate est augmentée et revérifiée, dans la limite de
    ``_TICKET_PAGE_FIT_MAX_ATTEMPTS`` tentatives (jamais de boucle non
    bornée : au-delà, le contenu est légitimement trop long pour une seule
    page et la dernière hauteur testée est conservée telle quelle, sans
    jamais tronquer ni masquer d'information)."""
    content_width_pt = content_width_mm * _MM_TO_POINTS

    # Estimation initiale : mesure en mode page infinie, point de départ
    # déjà proche de la valeur correcte dans l'immense majorité des cas.
    document.setTextWidth(content_width_pt)
    candidate_height_pt = max(document.size().height(), _TICKET_MIN_HEIGHT_MM * _MM_TO_POINTS)

    increment_pt = _TICKET_PAGE_FIT_INCREMENT_MM * _MM_TO_POINTS
    for _ in range(_TICKET_PAGE_FIT_MAX_ATTEMPTS):
        document.setPageSize(QSizeF(content_width_pt, candidate_height_pt))
        if document.pageCount() <= 1:
            break
        candidate_height_pt += increment_pt

    # Remet le document en mode page infinie : seul ce calcul a besoin du
    # mode paginé, ni l'impression/export réelle (qui gèrent leur propre
    # pagination via QPrinter), ni les usages ultérieurs de ce même
    # document (ex. inspection du HTML/texte dans les tests).
    document.setPageSize(QSizeF(-1, -1))

    height_mm = candidate_height_pt / _MM_TO_POINTS
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

    if receipt_format is ReceiptFormat.A4:
        logo_size = _add_logo_resource(document, data, _LOGO_MAX_WIDTH_A4_MM, _LOGO_MAX_HEIGHT_A4_MM)
        document.setHtml(_build_a4_html(data, logo_size))
        page_size = QPageSize(QPageSize.PageSizeId.A4)
        return RenderedReceipt(document=document, page_size=page_size, margin_mm=_A4_MARGIN_MM)

    if receipt_format is ReceiptFormat.TICKET_80MM:
        logo_size = _add_logo_resource(document, data, _LOGO_MAX_WIDTH_TICKET_MM, _LOGO_MAX_HEIGHT_TICKET_MM)
        document.setHtml(_build_ticket_html(data, logo_size))
        content_width_mm = _TICKET_WIDTH_MM - 2 * _TICKET_MARGIN_MM
        height_mm = _measure_ticket_height_mm(document, content_width_mm)
        page_size = QPageSize(QSizeF(_TICKET_WIDTH_MM, height_mm), QPageSize.Unit.Millimeter)
        return RenderedReceipt(document=document, page_size=page_size, margin_mm=_TICKET_MARGIN_MM)

    raise ValueError(f"Format de reçu non pris en charge : {receipt_format!r}")


# -- documents de location (Lot 22, §F) ------------------------------------------------
#
# Choix délibéré, à documenter dans le compte rendu (jamais demandé
# explicitement par le mandat, qui ne fixe un format que pour les reçus de
# vente) : format A4 uniquement pour les deux documents de location,
# jamais de variante ticket 80 mm — une location ne se traite pas à la
# caisse et aucun des deux visuels fournis en exemple n'était un ticket.
# Même principe déjà retenu pour ``build_payment_receipt_document``
# ci-dessus (A4 uniquement) : réutilisé ici pour la même raison.


def _build_reservation_voucher_html(
    data: LocationReservationVoucherData, logo_size: Optional[tuple[float, float]]
) -> str:
    logo_html = _logo_html(logo_size)
    entreprise_nom = _esc(data.entreprise_nom) or "(Entreprise non configurée — voir Paramètres)"
    header_lines = "<br/>".join(_header_lines(data)) or "&nbsp;"
    client_section = _client_section_html_a4(data)

    rows = "".join(
        f"<tr>"
        f"<td>{_esc(l.article_reference)} — {_esc(l.article_designation)}</td>"
        f"<td align='center'>{_esc(format_quantity(l.quantite_reservee))}</td>"
        f"<td align='right'>{_fmt_money(l.tarif_jour, data.devise)}</td>"
        f"</tr>"
        for l in data.lignes
    )

    # Caution éventuelle (§G) : jamais affirmée comme déjà perçue — montant
    # prévu tel que défini sur la location, sans invention d'un statut de
    # paiement qu'aucune donnée ne permet de déterminer ici.
    caution_block = ""
    if data.caution_montant > 0:
        caution_block = (
            f'<p style="margin:12px 0 0 0;">Caution prévue : '
            f"{_fmt_money(data.caution_montant, data.devise)}</p>"
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
          <h1 style="margin:0;">JUSTIFICATIF DE RÉSERVATION</h1>
          <p style="margin:4px 0;">
            N° {_esc(data.numero)}<br/>
            Date : {_esc(data.date)}<br/>
            Enregistré par : {_esc(data.username)}
          </p>
        </td>
      </tr>
    </table>
    <hr/>
    {client_section}
    <p style="margin:12px 0; font-style:italic; color:#444444;">
      Ce document atteste la réservation des articles ci-dessous. Il ne
      constitue pas un reçu de paiement : la location est facturée à la
      journée, le montant total ne peut donc être déterminé qu'au retour
      des articles.
    </p>
    <table width="100%" border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;">
      <tr style="background-color:#eeeeee;">
        <th align="left">Article</th>
        <th align="center">Qté réservée</th>
        <th align="right">Tarif / jour</th>
      </tr>
      {rows}
    </table>
    {caution_block}
    {_footer_phrase_html(data, font_size_pt=9)}
    </div>
    """


def build_location_reservation_voucher_document(data: LocationReservationVoucherData) -> RenderedReceipt:
    """Construit le justificatif de réservation (format A4 uniquement, voir
    note ci-dessus). Pure fonction de rendu, comme ``build_receipt_document``."""
    document = QTextDocument()
    logo_size = _add_logo_resource(document, data, _LOGO_MAX_WIDTH_A4_MM, _LOGO_MAX_HEIGHT_A4_MM)
    document.setHtml(_build_reservation_voucher_html(data, logo_size))
    page_size = QPageSize(QPageSize.PageSizeId.A4)
    return RenderedReceipt(document=document, page_size=page_size, margin_mm=_A4_MARGIN_MM)


def _location_receipt_lines_rows(data: LocationReceiptData) -> str:
    rows = []
    for ligne in data.lignes:
        if not ligne.retours:
            rows.append(
                f"<tr>"
                f"<td>{_esc(ligne.article_reference)} — {_esc(ligne.article_designation)}</td>"
                f"<td align='right'>{_fmt_money(ligne.tarif_jour, data.devise)}</td>"
                f"<td colspan='3' style='font-style:italic; color:#777777;'>Non encore retourné</td>"
                f"</tr>"
            )
            continue
        for retour in ligne.retours:
            rows.append(
                f"<tr>"
                f"<td>{_esc(ligne.article_reference)} — {_esc(ligne.article_designation)}</td>"
                f"<td align='right'>{_fmt_money(ligne.tarif_jour, data.devise)}</td>"
                f"<td>{_esc(retour.date_retour)}</td>"
                f"<td align='center'>{_esc(format_quantity(retour.quantite))} x {retour.jours} j</td>"
                f"<td align='right'>{_fmt_money(retour.montant_facture, data.devise)}</td>"
                f"</tr>"
            )
    return "".join(rows)


def _location_payment_rows_a4(data: LocationReceiptData) -> str:
    return f"""
    <p align="right" style="margin:2px 0;">Payé : {_fmt_money(data.montant_paye, data.devise)}</p>
    <p align="right" style="margin:2px 0; font-weight:600;">Reste à payer : {_fmt_money(data.reste_a_payer, data.devise)}</p>
    """


def _location_payment_history_row_a4(p, devise: str) -> str:
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


def _location_payment_history_section_a4(data: LocationReceiptData) -> str:
    if not data.paiements:
        return ""
    rows = "".join(_location_payment_history_row_a4(p, data.devise) for p in data.paiements)
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


def _build_location_receipt_html(
    data: LocationReceiptData, logo_size: Optional[tuple[float, float]]
) -> str:
    logo_html = _logo_html(logo_size)
    entreprise_nom = _esc(data.entreprise_nom) or "(Entreprise non configurée — voir Paramètres)"
    header_lines = "<br/>".join(_header_lines(data)) or "&nbsp;"
    client_section = _client_section_html_a4(data)
    statut_label = _STATUT_LOCATION_LABELS.get(data.statut, str(data.statut))
    date_depart_text = _esc(data.date_depart) if data.date_depart else "—"

    rows = _location_receipt_lines_rows(data)

    # Caution (§G) : toujours affichée séparément, jamais ajoutée au total
    # facturé ci-dessous — elle ne concerne pas la location des articles
    # eux-mêmes (voir docstring de module).
    caution_block = ""
    if data.caution_montant > 0:
        caution_block = f"""
        <hr/>
        <p style="margin:4px 0;">Caution versée : {_fmt_money(data.caution_montant, data.devise)}</p>
        <p style="margin:4px 0;">Caution restituée/retenue : {_fmt_money(data.caution_rendue, data.devise)}</p>
        """

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
          <h1 style="margin:0;">REÇU DE LOCATION</h1>
          <p style="margin:4px 0;">
            N° {_esc(data.numero)}<br/>
            Date de réservation : {_esc(data.date)}<br/>
            Date de départ : {date_depart_text}<br/>
            Enregistré par : {_esc(data.username)}<br/>
            Statut : {_esc(statut_label)}
          </p>
        </td>
      </tr>
    </table>
    <hr/>
    {client_section}
    <table width="100%" border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;">
      <tr style="background-color:#eeeeee;">
        <th align="left">Article</th>
        <th align="right">Tarif / jour</th>
        <th align="left">Retour</th>
        <th align="center">Qté x jours</th>
        <th align="right">Montant facturé</th>
      </tr>
      {rows}
    </table>
    <h2 align="right" style="margin-top:16px;">Total facturé : {_fmt_money(data.total_facture, data.devise)}</h2>
    {_location_payment_rows_a4(data)}
    {_location_payment_history_section_a4(data)}
    {caution_block}
    {_footer_phrase_html(data, font_size_pt=9)}
    </div>
    """


def build_location_receipt_document(data: LocationReceiptData) -> RenderedReceipt:
    """Construit le reçu de location (format A4 uniquement, voir note
    ci-dessus). Pure fonction de rendu, comme ``build_receipt_document``."""
    document = QTextDocument()
    logo_size = _add_logo_resource(document, data, _LOGO_MAX_WIDTH_A4_MM, _LOGO_MAX_HEIGHT_A4_MM)
    document.setHtml(_build_location_receipt_html(data, logo_size))
    page_size = QPageSize(QPageSize.PageSizeId.A4)
    return RenderedReceipt(document=document, page_size=page_size, margin_mm=_A4_MARGIN_MM)
