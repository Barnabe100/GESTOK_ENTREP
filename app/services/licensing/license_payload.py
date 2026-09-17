"""Structure versionnée de la charge utile de licence, et sa sérialisation
canonique — la même représentation doit être signée par le générateur et
revérifiée par le client (§3-4 de la phase Licences) ; toute divergence de
sérialisation invaliderait silencieusement la protection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import FrozenSet, Optional

from app.models.enums import EditionLicence

PRODUCT_NAME = "StockManager Desktop"

# Version du format de charge utile — incrémentée si la structure évolue
# (§4 : le format doit être versionné pour permettre l'évolution future).
LICENSE_FORMAT_VERSION = 1
SUPPORTED_LICENSE_VERSIONS = frozenset({LICENSE_FORMAT_VERSION})

# Fonctionnalités réellement présentes dans l'application (§13 : ne jamais
# inventer de fonctionnalité pour remplir artificiellement une édition).
# Chaque code correspond à un module métier existant ; le mapping vers les
# permissions RBAC concernées vit dans permission_map.py.
FEATURE_ARTICLES = "ARTICLES"
FEATURE_CATEGORIES = "CATEGORIES"
FEATURE_SUPPLIERS = "SUPPLIERS"
FEATURE_STOCK_ENTRIES = "STOCK_ENTRIES"
FEATURE_STOCK_EXITS = "STOCK_EXITS"
FEATURE_STOCK_MOVEMENTS = "STOCK_MOVEMENTS"
FEATURE_SALES = "SALES"
FEATURE_INVENTORY = "INVENTORY"
FEATURE_REPORTS = "REPORTS"
FEATURE_REPORTS_EXPORT = "REPORTS_EXPORT"
FEATURE_BACKUPS = "BACKUPS"
FEATURE_AUDIT = "AUDIT"
FEATURE_MULTI_USER = "MULTI_USER"

KNOWN_FEATURES = frozenset({
    FEATURE_ARTICLES, FEATURE_CATEGORIES, FEATURE_SUPPLIERS,
    FEATURE_STOCK_ENTRIES, FEATURE_STOCK_EXITS, FEATURE_STOCK_MOVEMENTS,
    FEATURE_SALES, FEATURE_INVENTORY, FEATURE_REPORTS, FEATURE_REPORTS_EXPORT,
    FEATURE_BACKUPS, FEATURE_AUDIT, FEATURE_MULTI_USER,
})

# Jeux de fonctionnalités par défaut, PAR ÉDITION — utilisés uniquement par
# l'outil générateur (license_generator/) au moment d'émettre une licence.
# Le client ne les importe jamais pour décider d'un droit : une fois émise,
# seule la liste "features" réellement présente dans la charge utile signée
# fait foi (§4, §7, §13 : ne jamais coder en dur les droits d'une édition
# côté client).
DEFAULT_FEATURES_BY_EDITION: dict[EditionLicence, FrozenSet[str]] = {
    EditionLicence.DEMO: frozenset({
        FEATURE_ARTICLES, FEATURE_CATEGORIES, FEATURE_SUPPLIERS,
        FEATURE_STOCK_ENTRIES, FEATURE_STOCK_EXITS, FEATURE_STOCK_MOVEMENTS,
    }),
    EditionLicence.STANDARD: frozenset({
        FEATURE_ARTICLES, FEATURE_CATEGORIES, FEATURE_SUPPLIERS,
        FEATURE_STOCK_ENTRIES, FEATURE_STOCK_EXITS, FEATURE_STOCK_MOVEMENTS,
        FEATURE_SALES, FEATURE_INVENTORY, FEATURE_REPORTS,
    }),
    EditionLicence.PROFESSIONAL: frozenset({
        FEATURE_ARTICLES, FEATURE_CATEGORIES, FEATURE_SUPPLIERS,
        FEATURE_STOCK_ENTRIES, FEATURE_STOCK_EXITS, FEATURE_STOCK_MOVEMENTS,
        FEATURE_SALES, FEATURE_INVENTORY, FEATURE_REPORTS, FEATURE_REPORTS_EXPORT,
        FEATURE_BACKUPS, FEATURE_AUDIT,
    }),
    EditionLicence.ENTREPRISE: frozenset(KNOWN_FEATURES),
}


class LicensePayloadError(ValueError):
    """La structure de la charge utile ne respecte pas le format attendu
    (champ manquant, type invalide, édition/version inconnue...) — distincte
    d'une signature invalide, vérifiée séparément par license_crypto."""


@dataclass(frozen=True)
class LicensePayload:
    license_version: int
    license_id: str
    product: str
    client: str
    edition: EditionLicence
    issued_at: date
    expires_at: Optional[date]
    max_users: int
    max_devices: int
    features: FrozenSet[str]

    def to_dict(self) -> dict:
        return {
            "license_version": self.license_version,
            "license_id": self.license_id,
            "product": self.product,
            "client": self.client,
            "edition": self.edition.value,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "max_users": self.max_users,
            "max_devices": self.max_devices,
            "features": sorted(self.features),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LicensePayload":
        """Lève ``LicensePayloadError`` pour toute structure invalide —
        jamais une ``KeyError``/``TypeError`` généraliste qui échapperait à
        la gestion centralisée par ``LicenseService``."""
        if not isinstance(data, dict):
            raise LicensePayloadError("La charge utile doit être un objet JSON.")

        required = (
            "license_version", "license_id", "product", "client", "edition",
            "issued_at", "max_users", "max_devices", "features",
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise LicensePayloadError(f"Champ(s) manquant(s) : {', '.join(missing)}.")

        license_version = data["license_version"]
        if not isinstance(license_version, int) or isinstance(license_version, bool):
            raise LicensePayloadError("« license_version » doit être un entier.")

        edition_raw = data["edition"]
        try:
            edition = EditionLicence(edition_raw)
        except ValueError as exc:
            raise LicensePayloadError(f"Édition inconnue : {edition_raw!r}.") from exc

        issued_at = _parse_date(data["issued_at"], "issued_at")
        expires_at_raw = data.get("expires_at")
        expires_at = _parse_date(expires_at_raw, "expires_at") if expires_at_raw else None

        max_users = data["max_users"]
        max_devices = data["max_devices"]
        if not isinstance(max_users, int) or isinstance(max_users, bool) or max_users < 1:
            raise LicensePayloadError("« max_users » doit être un entier positif.")
        if not isinstance(max_devices, int) or isinstance(max_devices, bool) or max_devices < 1:
            raise LicensePayloadError("« max_devices » doit être un entier positif.")

        features_raw = data["features"]
        if not isinstance(features_raw, list) or not all(isinstance(f, str) for f in features_raw):
            raise LicensePayloadError("« features » doit être une liste de chaînes.")

        license_id = data["license_id"]
        client = data["client"]
        product = data["product"]
        if not isinstance(license_id, str) or not license_id.strip():
            raise LicensePayloadError("« license_id » est obligatoire.")
        if not isinstance(client, str) or not client.strip():
            raise LicensePayloadError("« client » est obligatoire.")
        if not isinstance(product, str) or not product.strip():
            raise LicensePayloadError("« product » est obligatoire.")

        return cls(
            license_version=license_version, license_id=license_id, product=product,
            client=client, edition=edition, issued_at=issued_at, expires_at=expires_at,
            max_users=max_users, max_devices=max_devices, features=frozenset(features_raw),
        )


def _parse_date(value: object, field_name: str) -> date:
    if not isinstance(value, str):
        raise LicensePayloadError(f"« {field_name} » doit être une date ISO (AAAA-MM-JJ).")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LicensePayloadError(f"« {field_name} » n'est pas une date ISO valide : {value!r}.") from exc


def canonical_json_bytes(payload_dict: dict) -> bytes:
    """Sérialisation canonique : c'est exactement cette suite d'octets qui
    est signée par le générateur et revérifiée par le client (§3) — jamais
    une représentation différente (clés triées, séparateurs compacts, sans
    dépendance à la locale)."""
    return json.dumps(payload_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
