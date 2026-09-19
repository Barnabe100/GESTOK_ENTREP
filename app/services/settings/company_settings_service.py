"""Paramètres généraux de l'entreprise cliente : profil (nom, coordonnées),
devise d'affichage, logo — persistés dans la table clé-valeur ``parametres``
existante (voir ``app.repositories.parameter_repository``), même mécanisme
que la configuration des sauvegardes (``BackupService``), réutilisé tel quel
plutôt que d'ajouter une nouvelle table.

Distinction essentielle avec l'identité du produit (§ branding de cette
phase) : le logo géré ici est celui de l'entreprise cliente, destiné aux
futurs reçus/documents PDF qui la concernent. Il ne remplace ni ne modifie
jamais le logo StockManager/SM (``app.resources.APP_ICON_PATH``, bundlé en
lecture seule par PyInstaller) — ce service n'écrit d'ailleurs jamais dans
``app/resources``, uniquement dans ``Settings.data_dir`` (dossier de données
applicatif, accessible en écriture, déjà utilisé pour la base et les
sauvegardes).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QImageReader

from app.config.settings import Settings, get_settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.repositories.parameter_repository import ParameterRepository
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.settings")

_KEY_NOM = "entreprise.nom"
_KEY_ADRESSE = "entreprise.adresse"
_KEY_TELEPHONE = "entreprise.telephone"
_KEY_EMAIL = "entreprise.email"
_KEY_DEVISE = "entreprise.devise"
_KEY_LOGO_PATH = "entreprise.logo_path"

_MAX_LENGTHS = {
    "nom": 150,
    "adresse": 255,
    "telephone": 30,
    "email": 150,
}

# Devises déjà prises en charge par le formatage monétaire (voir
# app.utils.money._CURRENCY_SYMBOLS) : restreint le choix à des devises dont
# l'affichage est réellement correct, plutôt que d'accepter un code arbitraire.
SUPPORTED_CURRENCIES = {"XOF", "XAF", "EUR", "USD"}
DEFAULT_CURRENCY = "XOF"

_ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_MAX_LOGO_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 Mo
_MAX_LOGO_DIMENSION_PX = 4000
_LOGO_FILENAME_STEM = "logo_entreprise"


def _clean_optional(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    max_length = _MAX_LENGTHS[field_name]
    if len(value) > max_length:
        raise ValidationError(f"Le champ « {field_name} » ne doit pas dépasser {max_length} caractères.")
    return value


def _validate_email(email: Optional[str]) -> Optional[str]:
    email = _clean_optional(email, "email")
    if email is not None and "@" not in email:
        raise ValidationError("L'adresse email de l'entreprise n'est pas valide.")
    return email


def _validate_nom(nom: Optional[str]) -> str:
    nom = (nom or "").strip()
    if not nom:
        raise ValidationError("Le nom de l'entreprise est obligatoire.")
    if len(nom) > _MAX_LENGTHS["nom"]:
        raise ValidationError(f"Le nom de l'entreprise ne doit pas dépasser {_MAX_LENGTHS['nom']} caractères.")
    return nom


def get_effective_currency(settings: Optional[Settings] = None) -> str:
    """Devise à utiliser pour l'affichage monétaire dans toute l'application :
    celle configurée dans Paramètres si elle a été enregistrée, sinon la
    devise par défaut de la configuration (``STOCKMANAGER_DEFAULT_CURRENCY``).
    Fonction autonome (pas de vérification de permission) : appelée par les
    pages de consultation, qui ne doivent pas avoir à passer par une
    vérification ``SETTINGS_VIEW`` uniquement pour formater un montant."""
    effective_settings = settings or get_settings()
    with session_scope(effective_settings) as session:
        devise = ParameterRepository(session).get_value(_KEY_DEVISE)
    return devise or effective_settings.default_currency


@dataclass(frozen=True)
class CompanySettingsConfig:
    """Paramètres de l'entreprise cliente, persistés dans ``parametres``."""

    nom: Optional[str]
    adresse: Optional[str]
    telephone: Optional[str]
    email: Optional[str]
    devise: str
    logo_path: Optional[Path]


class CompanySettingsService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _effective_settings(self) -> Settings:
        return self._settings or get_settings()

    def _audit(self, action: str, resultat: ResultatAudit, details: Optional[str] = None) -> None:
        with session_scope(self._settings) as session:
            session.add(
                AuditLog(
                    user_id=self._acting_user_id(), action=action, entite="parametres",
                    entite_id=None, resultat=resultat, details=details,
                )
            )

    # -- consultation / mise à jour du profil --------------------------------------

    def get_config(self) -> CompanySettingsConfig:
        self._permissions.require_permission("SETTINGS_VIEW")
        return self._read_config()

    def _read_config(self) -> CompanySettingsConfig:
        with session_scope(self._settings) as session:
            repo = ParameterRepository(session)
            nom = repo.get_value(_KEY_NOM)
            adresse = repo.get_value(_KEY_ADRESSE)
            telephone = repo.get_value(_KEY_TELEPHONE)
            email = repo.get_value(_KEY_EMAIL)
            devise = repo.get_value(_KEY_DEVISE)
            logo_raw = repo.get_value(_KEY_LOGO_PATH)
        return CompanySettingsConfig(
            nom=nom, adresse=adresse, telephone=telephone, email=email,
            devise=devise or self._effective_settings().default_currency,
            logo_path=Path(logo_raw) if logo_raw else None,
        )

    def update_config(
        self,
        *,
        nom: Optional[str],
        adresse: Optional[str],
        telephone: Optional[str],
        email: Optional[str],
        devise: str,
    ) -> CompanySettingsConfig:
        self._permissions.require_permission("SETTINGS_UPDATE")

        nom = _validate_nom(nom)
        adresse = _clean_optional(adresse, "adresse")
        telephone = _clean_optional(telephone, "telephone")
        email = _validate_email(email)

        devise = (devise or "").strip().upper()
        if devise not in SUPPORTED_CURRENCIES:
            raise ValidationError(
                f"Devise non prise en charge : « {devise} » "
                f"(valeurs autorisées : {', '.join(sorted(SUPPORTED_CURRENCIES))})."
            )

        with session_scope(self._settings) as session:
            repo = ParameterRepository(session)
            repo.set_value(_KEY_NOM, nom)
            repo.set_value(_KEY_ADRESSE, adresse)
            repo.set_value(_KEY_TELEPHONE, telephone)
            repo.set_value(_KEY_EMAIL, email)
            repo.set_value(_KEY_DEVISE, devise)

        self._audit("SETTINGS_UPDATE", ResultatAudit.SUCCES)
        logger.info("Paramètres de l'entreprise mis à jour.")
        return self._read_config()

    # -- logo de l'entreprise cliente -----------------------------------------------

    def _branding_dir(self) -> Path:
        return self._effective_settings().data_dir / "branding"

    def set_logo(self, file_path: str | Path) -> CompanySettingsConfig:
        """Valide puis copie l'image choisie dans le dossier de données
        applicatif (jamais ``app/resources``, réservé au logo du produit)."""
        self._permissions.require_permission("SETTINGS_UPDATE")

        source = Path(file_path)
        if not source.is_file():
            raise ValidationError(f"Le fichier « {source} » est introuvable.")

        extension = source.suffix.lower()
        if extension not in _ALLOWED_LOGO_EXTENSIONS:
            raise ValidationError(
                f"Format de logo non pris en charge ({extension or 'sans extension'}) — "
                f"formats acceptés : {', '.join(sorted(_ALLOWED_LOGO_EXTENSIONS))}."
            )

        size_bytes = source.stat().st_size
        if size_bytes > _MAX_LOGO_FILE_SIZE_BYTES:
            raise ValidationError(
                f"Le fichier de logo est trop volumineux ({size_bytes // 1024} Ko, "
                f"maximum {_MAX_LOGO_FILE_SIZE_BYTES // 1024} Ko)."
            )

        reader = QImageReader(str(source))
        if not reader.canRead():
            raise ValidationError("Le fichier sélectionné n'est pas une image valide.")
        image_size = reader.size()
        if image_size.width() > _MAX_LOGO_DIMENSION_PX or image_size.height() > _MAX_LOGO_DIMENSION_PX:
            raise ValidationError(
                f"Image trop grande ({image_size.width()}x{image_size.height()} px, "
                f"maximum {_MAX_LOGO_DIMENSION_PX}x{_MAX_LOGO_DIMENSION_PX} px)."
            )

        branding_dir = self._branding_dir()
        try:
            branding_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValidationError(f"Impossible de créer le dossier de branding : {exc}") from exc

        destination = branding_dir / f"{_LOGO_FILENAME_STEM}{extension}"
        try:
            shutil.copyfile(source, destination)
        except OSError as exc:
            raise ValidationError(f"Impossible d'enregistrer le logo : {exc}") from exc

        # Supprime un ancien logo d'extension différente (ex. remplacement
        # .png -> .jpg) pour n'en conserver qu'un seul sur disque.
        for other_extension in _ALLOWED_LOGO_EXTENSIONS - {extension}:
            stale = branding_dir / f"{_LOGO_FILENAME_STEM}{other_extension}"
            if stale.exists():
                stale.unlink()

        with session_scope(self._settings) as session:
            ParameterRepository(session).set_value(_KEY_LOGO_PATH, str(destination))

        self._audit("SETTINGS_LOGO_UPDATE", ResultatAudit.SUCCES, details=str(destination))
        logger.info("Logo de l'entreprise mis à jour : %s", destination)
        return self._read_config()

    def clear_logo(self) -> CompanySettingsConfig:
        self._permissions.require_permission("SETTINGS_UPDATE")

        config = self._read_config()
        if config.logo_path is not None and config.logo_path.exists():
            try:
                config.logo_path.unlink()
            except OSError as exc:
                logger.warning("Impossible de supprimer le fichier de logo %s : %s", config.logo_path, exc)

        with session_scope(self._settings) as session:
            ParameterRepository(session).set_value(_KEY_LOGO_PATH, None)

        self._audit("SETTINGS_LOGO_CLEAR", ResultatAudit.SUCCES)
        logger.info("Logo de l'entreprise supprimé.")
        return self._read_config()
