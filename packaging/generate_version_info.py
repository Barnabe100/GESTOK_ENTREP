#!/usr/bin/env python3
"""Génère ``packaging/file_version_info.txt`` (métadonnées de version de
l'exécutable Windows, format attendu par PyInstaller's ``version=`` dans le
``.spec``) à partir de ``app/version.py`` — source unique de la version
(§17 du cahier des charges de la phase Packaging) : ne jamais éditer
``file_version_info.txt`` à la main, toujours régénérer depuis ce script
après avoir changé ``app/version.py``.

Usage :
    python packaging/generate_version_info.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.version import APP_NAME, __version__  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "file_version_info.txt"

_TEMPLATE = """\
# Généré automatiquement par packaging/generate_version_info.py — ne pas éditer à la main.
# Source : app/version.py (version={version!r})
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({tuple_version}, 0),
    prodvers=({tuple_version}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040c04b0',
          [StringStruct(u'CompanyName', u'{app_name}'),
          StringStruct(u'FileDescription', u'{app_name}'),
          StringStruct(u'FileVersion', u'{version}'),
          StringStruct(u'InternalName', u'stockmanager'),
          StringStruct(u'OriginalFilename', u'StockManager.exe'),
          StringStruct(u'ProductName', u'{app_name}'),
          StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1036, 1200])])
  ]
)
"""


def main() -> int:
    parts = __version__.split(".")
    parts += ["0"] * (3 - len(parts))
    tuple_version = ", ".join(parts[:3])

    content = _TEMPLATE.format(version=__version__, tuple_version=tuple_version, app_name=APP_NAME)
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Métadonnées de version écrites : {OUTPUT_PATH} (version={__version__}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
