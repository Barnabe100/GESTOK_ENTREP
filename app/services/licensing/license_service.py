"""``LicenseService`` : point d'entrée unique pour tout ce qui concerne la
licence — validation complète (§5), état exploitable (§6), activation
offline (§9), stockage local sans jamais la clé privée (§10), identité
d'appareil V1 (§11), limite d'utilisateurs (§12).

Ni ``FeatureGate`` ni aucune autre couche ne doit relire ``Licence`` ou
vérifier une signature par elle-même : tout passe par cette classe.
"""
from __future__ import annotations

import base64
import enum
import json
from dataclasses import dataclass
from datetime import date
from typing import FrozenSet, Optional

from uuid import uuid4

from app.config.settings import Settings, get_settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import EditionLicence, ResultatAudit, StatutLicence
from app.models.license import Licence
from app.models.user import User
from app.repositories.licence_repository import LicenceRepository
from app.repositories.parameter_repository import ParameterRepository
from app.services.auth.permission_service import PermissionService
from app.services.licensing import license_crypto
from app.services.licensing.license_payload import (
    KNOWN_FEATURES,
    PRODUCT_NAME,
    SUPPORTED_LICENSE_VERSIONS,
    LicensePayload,
    LicensePayloadError,
    canonical_json_bytes,
)
from app.services.licensing.public_key import PRODUCTION_PUBLIC_KEY_BYTES
from app.utils.exceptions import ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.licensing")

_KEY_DEVICE_ID = "license.device_id"


class LicenseState(str, enum.Enum):
    """État exploitable de la licence courante (§6) — distinct de
    ``StatutLicence`` (instantané persisté en base au moment de
    l'activation) : cet état est toujours recalculé par vérification
    cryptographique complète, jamais lu tel quel depuis la base (§10 : ne
    jamais faire confiance à une information stockée localement sans
    revalider la signature)."""

    VALID = "VALID"
    EXPIRED = "EXPIRED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    CORRUPTED = "CORRUPTED"


@dataclass(frozen=True)
class LicenseInfo:
    """Vue exploitable de la licence courante, exposée à l'UI et à
    ``FeatureGate``."""

    state: LicenseState
    client: Optional[str] = None
    produit: Optional[str] = None
    edition: Optional[EditionLicence] = None
    license_id: Optional[str] = None
    issued_at: Optional[date] = None
    expires_at: Optional[date] = None
    max_users: Optional[int] = None
    max_devices: Optional[int] = None
    features: FrozenSet[str] = frozenset()
    device_id: Optional[str] = None
    message: str = ""


class LicenseService:
    def __init__(
        self,
        permission_service: PermissionService,
        settings: Optional[Settings] = None,
        public_key_bytes: bytes = PRODUCTION_PUBLIC_KEY_BYTES,
    ) -> None:
        self._permissions = permission_service
        self._settings = settings
        self._public_key_bytes = public_key_bytes

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, action: str, resultat: ResultatAudit, details: Optional[str] = None) -> None:
        with session_scope(self._settings) as session:
            session.add(
                AuditLog(
                    user_id=self._acting_user_id(), action=action, entite="licences",
                    entite_id=None, resultat=resultat, details=details,
                )
            )

    # -- évaluation interne (aucune vérification de permission : utilisée par
    #    FeatureGate à chaque contrôle de fonctionnalité) --------------------

    def evaluate(self) -> LicenseInfo:
        """Revalide systématiquement la signature de la licence stockée —
        jamais de confiance dans le seul contenu de la base (§10)."""
        with session_scope(self._settings) as session:
            return self._evaluate_with_session(session)

    def _evaluate_with_session(self, session) -> LicenseInfo:
        """Cœur de l'évaluation, paramétré par une session déjà ouverte —
        utilisé aussi bien par ``evaluate()`` (session dédiée) que par
        ``check_can_activate_user`` (réutilise la session appelante, pour
        rester dans la même transaction plutôt que d'ouvrir une seconde
        connexion SQLite concurrente pendant qu'une écriture est en cours)."""
        device_id = self._ensure_device_id(session)
        licence_row = LicenceRepository(session).get_current()

        if licence_row is None:
            return LicenseInfo(state=LicenseState.MISSING, device_id=device_id, message="Aucune licence activée.")

        try:
            payload_dict = json.loads(licence_row.payload_json)
        except (TypeError, ValueError):
            return LicenseInfo(
                state=LicenseState.CORRUPTED, device_id=device_id,
                message="Licence stockée illisible (JSON corrompu).",
            )

        if not isinstance(payload_dict, dict):
            return LicenseInfo(
                state=LicenseState.CORRUPTED, device_id=device_id,
                message="Structure de licence stockée invalide.",
            )

        try:
            signature_bytes = _decode_signature(licence_row.signature)
        except (TypeError, ValueError):
            return LicenseInfo(
                state=LicenseState.CORRUPTED, device_id=device_id,
                message="Signature stockée illisible.",
            )

        message_bytes = canonical_json_bytes(payload_dict)
        if not license_crypto.verify(self._public_key_bytes, message_bytes, signature_bytes):
            return LicenseInfo(state=LicenseState.INVALID, device_id=device_id, message="Signature de licence invalide.")

        error = _validate_payload_structure(payload_dict)
        if error is not None:
            return LicenseInfo(state=LicenseState.INVALID, device_id=device_id, message=error)

        payload = LicensePayload.from_dict(payload_dict)

        state = LicenseState.VALID
        message = "Licence valide."
        if payload.expires_at is not None and payload.expires_at < date.today():
            state = LicenseState.EXPIRED
            message = f"Licence expirée depuis le {payload.expires_at.isoformat()}."

        return LicenseInfo(
            state=state, client=payload.client, produit=payload.product, edition=payload.edition,
            license_id=payload.license_id, issued_at=payload.issued_at, expires_at=payload.expires_at,
            max_users=payload.max_users, max_devices=payload.max_devices, features=payload.features,
            device_id=device_id, message=message,
        )

    def get_state(self) -> LicenseState:
        return self.evaluate().state

    def _ensure_device_id(self, session) -> str:
        """Identifiant d'appareil local (§11) : un simple UUID persisté une
        fois, stable entre redémarrages. Volontairement PAS une empreinte
        matérielle (fragile : change au moindre remplacement de disque ou
        de carte réseau). Limite documentée assumée pour cette version :
        ``max_devices`` n'est affiché qu'à titre informatif — son
        application fiable entre plusieurs postes nécessiterait un serveur
        central, explicitement hors périmètre V1 (cahier des charges §11).
        Une réinstallation régénère un nouvel identifiant."""
        repo = ParameterRepository(session)
        device_id = repo.get_value(_KEY_DEVICE_ID)
        if device_id is None:
            device_id = str(uuid4())
            repo.set_value(_KEY_DEVICE_ID, device_id)
        return device_id

    # -- consultation (UI) ------------------------------------------------------

    def get_info(self) -> LicenseInfo:
        self._permissions.require_permission("LICENSE_VIEW")
        return self.evaluate()

    # -- activation (§9) ---------------------------------------------------------

    def activate_license(self, file_content: str) -> LicenseInfo:
        """Vérifie intégralement une licence (structure, signature, version,
        produit, dates, fonctionnalités) avant toute persistance — une
        licence falsifiée ou modifiée sans re-signature est refusée sans
        jamais être enregistrée (§5, §16)."""
        self._permissions.require_permission("LICENSE_ACTIVATE")
        payload_dict, signature_raw, payload = self._validate_and_parse(file_content)

        statut = (
            StatutLicence.EXPIREE if (payload.expires_at and payload.expires_at < date.today())
            else StatutLicence.ACTIVE
        )

        with session_scope(self._settings) as session:
            LicenceRepository(session).add(
                Licence(
                    client=payload.client, produit=payload.product, edition=payload.edition,
                    date_emission=payload.issued_at, date_expiration=payload.expires_at,
                    max_users=payload.max_users, max_postes=payload.max_devices, statut=statut,
                    payload_json=json.dumps(payload_dict), signature=signature_raw,
                )
            )

        self._audit(
            "LICENSE_ACTIVATE_SUCCESS", ResultatAudit.SUCCES,
            details=f"license_id={payload.license_id} client={payload.client} edition={payload.edition.value}",
        )
        logger.info(
            "Licence activée : %s (client=%s, édition=%s).", payload.license_id, payload.client, payload.edition.value
        )
        return self.evaluate()

    def validate_license_content(self, file_content: str) -> LicensePayload:
        """Valide intégralement un contenu de licence (structure d'enveloppe,
        signature Ed25519, cohérence du payload) SANS l'enregistrer.

        Utilisé par ``ActivationService`` en mode SERVER : la validation
        locale doit être complète avant toute sollicitation d'un futur
        serveur TechNova, mais rien ne doit être persisté avant son
        autorisation (le serveur pourra encore refuser, ex. quota
        ``max_devices``) — voir l'architecture LOCAL/SERVER. Mêmes règles,
        mêmes messages d'erreur, même journalisation d'audit que
        ``activate_license`` : les deux méthodes partagent le même cœur de
        validation (``_validate_and_parse``), jamais dupliqué."""
        self._permissions.require_permission("LICENSE_ACTIVATE")
        _, _, payload = self._validate_and_parse(file_content)
        return payload

    def get_device_id(self) -> str:
        """Identifiant local de cet appareil (§11), sans vérification de
        permission dédiée : ce n'est pas une donnée de licence sensible,
        seulement un identifiant technique local — réutilisé par
        ``ActivationService`` pour le futur flux SERVER. Pour l'affichage
        UI, voir ``LicenseInfo.device_id`` via ``get_info()`` (protégé par
        ``LICENSE_VIEW``)."""
        with session_scope(self._settings) as session:
            return self._ensure_device_id(session)

    def _validate_and_parse(self, file_content: str) -> tuple[dict, str, LicensePayload]:
        """Cœur de validation partagé par ``activate_license`` et
        ``validate_license_content`` — jamais dupliqué. Comportement et
        messages d'erreur strictement identiques à avant l'extraction de
        cette méthode."""
        try:
            envelope = json.loads(file_content)
        except (TypeError, ValueError) as exc:
            self._audit("LICENSE_ACTIVATE_FAILURE", ResultatAudit.ECHEC, details=f"JSON invalide : {exc}")
            raise ValidationError("Le fichier de licence n'est pas un JSON valide.") from exc

        if not isinstance(envelope, dict) or "payload" not in envelope or "signature" not in envelope:
            self._audit("LICENSE_ACTIVATE_FAILURE", ResultatAudit.ECHEC, details="Structure d'enveloppe invalide.")
            raise ValidationError("Structure de licence invalide (« payload »/« signature » attendus).")

        payload_dict = envelope["payload"]
        if not isinstance(payload_dict, dict):
            self._audit("LICENSE_ACTIVATE_FAILURE", ResultatAudit.ECHEC, details="« payload » n'est pas un objet.")
            raise ValidationError("Structure de licence invalide : « payload » doit être un objet JSON.")

        signature_raw = envelope["signature"]
        try:
            signature_bytes = _decode_signature(signature_raw)
        except (TypeError, ValueError) as exc:
            self._audit("LICENSE_ACTIVATE_FAILURE", ResultatAudit.ECHEC, details=f"Signature illisible : {exc}")
            raise ValidationError("Signature de licence illisible (encodage invalide).") from exc

        message_bytes = canonical_json_bytes(payload_dict)
        if not license_crypto.verify(self._public_key_bytes, message_bytes, signature_bytes):
            self._audit("LICENSE_ACTIVATE_FAILURE", ResultatAudit.ECHEC, details="Signature invalide.")
            raise ValidationError(
                "Signature de licence invalide : fichier falsifié, modifié, ou signé avec une autre clé."
            )

        error = _validate_payload_structure(payload_dict)
        if error is not None:
            self._audit("LICENSE_ACTIVATE_FAILURE", ResultatAudit.ECHEC, details=error)
            raise ValidationError(error)

        try:
            payload = LicensePayload.from_dict(payload_dict)
        except LicensePayloadError as exc:
            self._audit("LICENSE_ACTIVATE_FAILURE", ResultatAudit.ECHEC, details=str(exc))
            raise ValidationError(f"Licence invalide : {exc}") from exc

        return payload_dict, signature_raw, payload

    # -- limite d'utilisateurs (§12) ----------------------------------------------

    def count_active_users(self, session) -> int:
        """Compte les comptes actifs (``User.actif is True``) — un compte
        désactivé ne consomme pas de place dans ``max_users`` (règle
        métier retenue pour cette phase)."""
        return session.query(User).filter(User.actif.is_(True)).count()

    def check_can_activate_user(self, session) -> None:
        """Lève ``ValidationError`` si activer un utilisateur de plus
        dépasserait ``max_users`` de la licence courante. Aucune limite
        n'est appliquée hors licence valide : c'est déjà ``FeatureGate`` qui
        bloque les fonctionnalités hors licence valide, cette méthode ne
        vérifie que la limite numérique d'une licence par ailleurs valide.

        Reçoit la session déjà ouverte par l'appelant (ex.
        ``UserService.set_active``) plutôt que d'en ouvrir une nouvelle : la
        vérification doit voir l'état de cette même transaction, non
        commitée, et éviter toute connexion SQLite concurrente pendant une
        écriture en cours (voir ``_evaluate_with_session``)."""
        info = self._evaluate_with_session(session)
        if info.state != LicenseState.VALID or info.max_users is None:
            return
        if self.count_active_users(session) >= info.max_users:
            raise ValidationError(
                f"Limite d'utilisateurs actifs atteinte ({info.max_users} autorisé(s) par la licence active)."
            )


def _validate_payload_structure(payload_dict: dict) -> Optional[str]:
    """Contrôles de structure/cohérence (§5, points 3/5/6/7/12) qui ne
    dépendent pas de ``LicensePayload.from_dict`` (lequel lève déjà pour les
    champs manquants/mal typés) : version supportée, produit, édition
    connue, date d'émission cohérente, fonctionnalités connues. Retourne un
    message d'erreur, ou ``None`` si tout est cohérent."""
    license_version = payload_dict.get("license_version")
    if license_version not in SUPPORTED_LICENSE_VERSIONS:
        return f"Version de licence non prise en charge : {license_version!r}."

    product = payload_dict.get("product")
    if product != PRODUCT_NAME:
        return f"Cette licence concerne un autre produit : {product!r}."

    edition_raw = payload_dict.get("edition")
    if edition_raw not in {edition.value for edition in EditionLicence}:
        return f"Édition inconnue : {edition_raw!r}."

    issued_at_raw = payload_dict.get("issued_at")
    if isinstance(issued_at_raw, str):
        try:
            issued_at = date.fromisoformat(issued_at_raw)
        except ValueError:
            return f"Date d'émission invalide : {issued_at_raw!r}."
        if issued_at > date.today():
            return f"Date d'émission incohérente (dans le futur) : {issued_at_raw!r}."

    features_raw = payload_dict.get("features")
    if isinstance(features_raw, list):
        unknown_features = set(features_raw) - KNOWN_FEATURES
        if unknown_features:
            return f"Fonctionnalité(s) inconnue(s) : {', '.join(sorted(unknown_features))}."

    return None


def _decode_signature(signature_raw: object) -> bytes:
    if not isinstance(signature_raw, str):
        raise TypeError("La signature doit être une chaîne encodée en base64.")
    return base64.b64decode(signature_raw, validate=True)
