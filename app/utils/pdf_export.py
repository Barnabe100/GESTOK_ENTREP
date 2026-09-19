"""Export d'un document Qt (``QTextDocument``) en fichier PDF.

Utilise exclusivement ``PySide6.QtPrintSupport`` (``QPrinter`` en sortie
PDF) : aucune dépendance supplémentaire (reportlab, weasyprint, ...) n'est
nécessaire — PySide6 est déjà une dépendance de l'application, et ce module
Qt gère nativement les caractères accentués (police système, pas
d'enregistrement de police requis) ainsi que le bundling PyInstaller (hook
officiel ``hook-PySide6.QtPrintSupport.py``).

Même rôle que ``csv_export.py`` pour les rapports : fonction utilitaire
pure, sans vérification de permission (déjà effectuée par l'appelant au
moment d'obtenir les données du document) et sans connaissance métier.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from app.utils.exceptions import ValidationError


def build_page_layout(page_size: QPageSize, margin_mm: float) -> QPageLayout:
    """Construit la mise en page (marges égales de tous les côtés) partagée
    par l'export PDF et l'impression directe — évite de dupliquer cette
    construction dans la vue qui gère l'impression."""
    return QPageLayout(
        page_size,
        QPageLayout.Orientation.Portrait,
        QMarginsF(margin_mm, margin_mm, margin_mm, margin_mm),
        QPageLayout.Unit.Millimeter,
    )


def export_document_to_pdf(
    document: QTextDocument,
    file_path: Union[str, Path],
    page_size: QPageSize,
    margin_mm: float = 10.0,
) -> None:
    """Écrit ``document`` dans un fichier PDF à ``file_path``, à la taille
    de page ``page_size`` (fixe pour A4, calculée dynamiquement pour un
    ticket — voir ``receipt_document.py``). Lève :class:`ValidationError` si
    le fichier ne peut pas être écrit (dossier inaccessible, ...) ou si
    l'export n'a produit aucun fichier exploitable."""
    file_path = Path(file_path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValidationError(f"Impossible de créer le dossier de destination : {exc}") from exc

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(file_path))
    printer.setPageLayout(build_page_layout(page_size, margin_mm))

    document.print_(printer)

    if not file_path.exists() or file_path.stat().st_size == 0:
        raise ValidationError(f"L'export PDF a échoué : le fichier « {file_path} » n'a pas été créé.")
