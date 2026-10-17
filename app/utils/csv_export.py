"""Export CSV générique, réutilisable par tous les rapports.

Utilise uniquement le module standard ``csv``. L'export Excel (voir
``app.utils.xlsx_export.export_rows_to_xlsx``) suit la même convention
qu'``export_document_to_pdf`` (``pdf_export.py``) : un module dédié par
format de sortie, plutôt qu'un seul fichier regroupant tous les formats.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence, Union


def export_rows_to_csv(
    file_path: Union[str, Path], headers: Sequence[str], rows: Sequence[Sequence[str]]
) -> None:
    """Écrit ``headers``/``rows`` (déjà formatées en texte par l'appelant) dans
    un fichier CSV. Délimiteur « ; » et BOM UTF-8 : convention Excel FR."""
    with open(file_path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(headers)
        writer.writerows(rows)
