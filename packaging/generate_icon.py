#!/usr/bin/env python3
"""Génère ``packaging/app_icon.ico`` à partir du symbole officiel SM +
carton (``app/resources/branding/stockmanager_mark.png``) — isolé du logo
officiel StockManager/TechNova fourni par le client par un simple recadrage
technique (sans texte ni slogan, jamais redessiné), voir
``app/resources/branding/README.md``.

Dépendance (dev uniquement, jamais dans requirements.txt du runtime) :
Pillow, pour rééchantillonner le PNG source vers chaque résolution et
assembler le ``.ico`` multi-résolutions.

Usage :
    python packaging/generate_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_MARK = REPO_ROOT / "app" / "resources" / "branding" / "stockmanager_mark.png"
OUTPUT_ICO = Path(__file__).resolve().parent / "app_icon.ico"

# Tailles standard d'une icône Windows (barre des tâches, Explorateur en
# grandes icônes, raccourcis) — inclut toutes les résolutions usuelles.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    if not SOURCE_MARK.exists():
        print(f"Symbole source introuvable : {SOURCE_MARK}", file=sys.stderr)
        return 1

    source = Image.open(SOURCE_MARK).convert("RGBA")

    # Pillow déduit les tailles embarquées de chaque image fournie lorsqu'aucun
    # paramètre ``sizes`` n'est passé : la base doit être la plus grande, les
    # suivantes strictement décroissantes — rééchantillonnage de haute qualité
    # (LANCZOS), jamais un simple redimensionnement au plus proche voisin.
    rendered = [
        source.resize((size, size), Image.Resampling.LANCZOS)
        for size in sorted(ICON_SIZES, reverse=True)
    ]
    rendered[0].save(str(OUTPUT_ICO), format="ICO", append_images=rendered[1:])

    print(f"Icône Windows écrite : {OUTPUT_ICO} ({len(ICON_SIZES)} résolutions).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
