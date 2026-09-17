#!/usr/bin/env python3
"""Génère la paire de clés Ed25519 de production de StockManager.

À exécuter UNE SEULE FOIS par l'éditeur, sur un poste hors du dépôt public
(ou en tout cas jamais suivi par git — voir ``keys/`` dans ``.gitignore``).
Le fichier de clé privée produit ne doit JAMAIS être commité, copié dans le
projet client ``app/``, ni distribué avec l'exécutable. Seule la clé
publique (fichier ``.hex``) doit être copiée dans
``app/services/licensing/public_key.py``.

Usage :
    python generate_keypair.py [--out-dir keys]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

DEFAULT_OUT_DIR = Path(__file__).parent / "keys"
PRIVATE_KEY_FILENAME = "private_key.pem"
PUBLIC_KEY_FILENAME = "public_key.hex"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    private_key_path = args.out_dir / PRIVATE_KEY_FILENAME
    public_key_path = args.out_dir / PUBLIC_KEY_FILENAME

    if private_key_path.exists():
        print(f"Refus d'écraser une clé privée existante : {private_key_path}", file=sys.stderr)
        return 1

    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    private_key_path.write_bytes(private_bytes)
    try:
        private_key_path.chmod(0o600)
    except OSError:
        pass
    public_key_path.write_text(public_bytes.hex())

    print(f"Clé privée écrite dans {private_key_path} (à conserver hors de tout dépôt).")
    print(f"Clé publique (hex) écrite dans {public_key_path} :")
    print(public_bytes.hex())
    print("Copiez cette valeur dans PRODUCTION_PUBLIC_KEY_HEX (app/services/licensing/public_key.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
