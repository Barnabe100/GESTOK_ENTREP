#!/usr/bin/env python3
"""Émet une licence StockManager signée (Ed25519) à partir de la clé privée
locale produite par ``generate_keypair.py``.

Cet outil ne fait jamais partie de l'application cliente (voir README.md) :
il importe la structure de charge utile depuis ``app.services.licensing``
en lecture seule (aucune clé, aucun secret dans ce module partagé), mais
n'est lui-même exécuté que par l'éditeur, jamais embarqué ni distribué.

Usage :
    python generate_license.py --client "Ma Société" --edition PROFESSIONAL \\
        --max-users 5 --max-devices 2 --expires 2027-01-01 \\
        --out licence_ma_societe.lic
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from base64 import b64encode
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.models.enums import EditionLicence
from app.services.licensing.license_payload import (
    DEFAULT_FEATURES_BY_EDITION,
    LICENSE_FORMAT_VERSION,
    PRODUCT_NAME,
    canonical_json_bytes,
)

DEFAULT_KEY_PATH = Path(__file__).parent / "keys" / "private_key.pem"


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit(f"{path} ne contient pas une clé Ed25519.")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--client", required=True)
    parser.add_argument("--edition", required=True, choices=[e.value for e in EditionLicence])
    parser.add_argument("--max-users", type=int, required=True)
    parser.add_argument("--max-devices", type=int, required=True)
    parser.add_argument("--expires", help="AAAA-MM-JJ ; omis = sans expiration")
    parser.add_argument("--license-id", help="Par défaut, généré aléatoirement")
    parser.add_argument(
        "--features",
        help="Liste de fonctionnalités séparées par des virgules ; par défaut celles de l'édition",
    )
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY_PATH)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if not args.key.exists():
        print(f"Clé privée introuvable : {args.key} (lancez d'abord generate_keypair.py).", file=sys.stderr)
        return 1

    private_key = _load_private_key(args.key)
    edition = EditionLicence(args.edition)
    features = (
        sorted(f.strip() for f in args.features.split(",") if f.strip())
        if args.features else sorted(DEFAULT_FEATURES_BY_EDITION[edition])
    )

    payload_dict = {
        "license_version": LICENSE_FORMAT_VERSION,
        "license_id": args.license_id or f"STK-{uuid.uuid4().hex[:12].upper()}",
        "product": PRODUCT_NAME,
        "client": args.client,
        "edition": edition.value,
        "issued_at": date.today().isoformat(),
        "expires_at": args.expires,
        "max_users": args.max_users,
        "max_devices": args.max_devices,
        "features": features,
    }

    message = canonical_json_bytes(payload_dict)
    signature = private_key.sign(message)

    envelope = {"payload": payload_dict, "signature": b64encode(signature).decode("ascii")}
    args.out.write_text(json.dumps(envelope, indent=2, ensure_ascii=False))
    print(f"Licence écrite dans {args.out} (id={payload_dict['license_id']}, édition={edition.value}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
