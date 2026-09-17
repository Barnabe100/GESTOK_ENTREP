#!/usr/bin/env python3
"""Génère ``packaging/app_icon.ico`` à partir de l'icône SVG existante
(``app/resources/icons/app_icon.svg``) — aucune nouvelle identité visuelle
créée pour cette phase (§18 du cahier des charges de la phase Packaging),
seulement une conversion de format nécessaire à l'exécutable Windows
(PyInstaller/Inno Setup exigent un ``.ico``, un SVG ne suffit pas pour
l'icône d'un ``.exe``).

Dépendances (dev uniquement, jamais dans requirements.txt du runtime) :
PySide6 (déjà présente) pour rasteriser le SVG, Pillow pour assembler le
``.ico`` multi-résolutions.

Usage :
    python packaging/generate_icon.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SVG = REPO_ROOT / "app" / "resources" / "icons" / "app_icon.svg"
OUTPUT_ICO = Path(__file__).resolve().parent / "app_icon.ico"

# Tailles standard d'une icône Windows (barre des tâches, Explorateur en
# grandes icônes, raccourcis) — inclut toutes les résolutions usuelles.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    if not SOURCE_SVG.exists():
        print(f"Icône source introuvable : {SOURCE_SVG}", file=sys.stderr)
        return 1

    app = QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(str(SOURCE_SVG))

    with tempfile.TemporaryDirectory() as tmp_dir:
        rendered = []
        for size in ICON_SIZES:
            image = QImage(size, size, QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            path = Path(tmp_dir) / f"{size}.png"
            image.save(str(path), "PNG")
            rendered.append(Image.open(path).convert("RGBA"))

        # Pillow déduit les tailles embarquées de chaque image fournie
        # lorsqu'aucun paramètre ``sizes`` n'est passé : la base doit être la
        # plus grande, les suivantes strictement décroissantes.
        rendered.sort(key=lambda im: im.width, reverse=True)
        rendered[0].save(str(OUTPUT_ICO), format="ICO", append_images=rendered[1:])

    print(f"Icône Windows écrite : {OUTPUT_ICO} ({len(ICON_SIZES)} résolutions).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
