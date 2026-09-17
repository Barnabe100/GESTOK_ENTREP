"""Export CSV générique, réutilisable par tous les rapports.

Utilise uniquement le module standard ``csv`` : aucune dépendance lourde
(openpyxl, reportlab, ...) n'est ajoutée pour cette phase (§8 du cahier des
charges de la phase Rapports). Les exports Excel/PDF pourront être ajoutés
ultérieurement en suivant la même interface (en-têtes + lignes déjà
formatées en texte), sans modifier les rapports eux-mêmes — seule une
nouvelle fonction ``export_rows_to_xlsx``/``export_rows_to_pdf`` serait à
ajouter dans ce module.
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
