"""Réinitialisation des données métier (« repartir sur une base propre »
après une période de test client, sans désinstaller StockManager).

Strictement réservé à l'Administrateur (``SYSTEM_RESET_BUSINESS_DATA``,
voir ``app/db/seed.py``) — protection appliquée ici, côté service, jamais
seulement par le masquage d'un bouton côté interface.

Principe de sécurité non négociable (§3 du lot) : une sauvegarde de
sécurité est créée et **vérifiée** via :class:`BackupService` avant toute
suppression ; si elle échoue, rien n'est réinitialisé. La réinitialisation
elle-même est une unique transaction (``session_scope``) : soit toutes les
suppressions réussissent, soit aucune (rollback automatique).

Ordre de suppression déterminé par le graphe de dépendances de clés
étrangères réelles du schéma (enfants avant parents) — jamais un ordre
arbitraire :
    mouvements_stock, paiements
    -> vente_lignes, sortie_lignes, entree_lignes, inventaire_lignes
    -> ventes, sorties, entrees, inventaires
    -> articles
    -> clients, fournisseurs, motifs_sortie, categories

Ne touche jamais : utilisateurs, rôles, permissions, compte administrateur,
paramètres de l'entreprise (dont logo/devise), licence, journal d'audit.

Comme pour ``BackupService.restore_backup``, l'événement d'audit
(succès/échec) est écrit **après coup**, dans une transaction séparée de
l'opération elle-même : un échec qui déclenche un rollback de la
réinitialisation ne doit jamais effacer la trace de la tentative.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.audit import AuditLog
from app.models.catalog import Article, Category, ExitReason, Supplier
from app.models.client import Client
from app.models.documents import Entree, EntreeLigne, Sortie, SortieLigne, Vente, VenteLigne
from app.models.enums import ResultatAudit
from app.models.inventory import Inventaire, InventaireLigne
from app.models.license import Licence
from app.models.movement import MouvementStock
from app.models.parameter import Parametre
from app.models.payment import Paiement
from app.models.rbac import Permission, Role
from app.models.user import User
from app.services.auth.permission_service import PermissionService
from app.services.backups.backup_service import BackupService
from app.utils.exceptions import ValidationError
from app.utils.logging_config import get_logger

logger = get_logger("services.system.data_reset")

# Ordre de suppression strict (enfants avant parents) — voir docstring de module.
_DELETE_ORDER: list[tuple[str, type]] = [
    ("mouvements_stock", MouvementStock),
    ("paiements", Paiement),
    ("vente_lignes", VenteLigne),
    ("sortie_lignes", SortieLigne),
    ("entree_lignes", EntreeLigne),
    ("inventaire_lignes", InventaireLigne),
    ("ventes", Vente),
    ("sorties", Sortie),
    ("entrees", Entree),
    ("inventaires", Inventaire),
    ("articles", Article),
    ("clients", Client),
    ("fournisseurs", Supplier),
    ("motifs_sortie", ExitReason),
    ("categories", Category),
]

# Tables jamais touchées — vérifiées inchangées après coup (§ intégrité).
_PRESERVED_MODELS: list[type] = [User, Role, Permission, Parametre, Licence]


@dataclass(frozen=True)
class DataResetResult:
    success: bool
    message: str
    backup_path: Optional[Path] = None
    deleted_counts: dict[str, int] = field(default_factory=dict)


class DataResetService:
    def __init__(
        self,
        permission_service: PermissionService,
        backup_service: BackupService,
        settings: Optional[Settings] = None,
    ) -> None:
        self._permissions = permission_service
        self._backups = backup_service
        self._settings = settings

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _audit(self, action: str, resultat: ResultatAudit, details: Optional[str] = None) -> None:
        """Écrit toujours dans sa propre transaction, jamais dans celle de
        l'opération auditée (voir docstring de module)."""
        with session_scope(self._settings) as session:
            session.add(
                AuditLog(
                    user_id=self._acting_user_id(), action=action, entite="systeme",
                    entite_id=None, resultat=resultat, details=details,
                )
            )

    def reset_business_data(self) -> DataResetResult:
        """Sauvegarde de sécurité vérifiée -> suppression transactionnelle
        des données métier, dans cet ordre strict. N'importe quelle étape en
        échec annule tout (rollback), et un échec de sauvegarde préalable
        bloque totalement l'opération : la base n'est jamais touchée."""
        self._permissions.require_permission("SYSTEM_RESET_BUSINESS_DATA")

        backup_result = self._backups.create_manual_backup()
        if not backup_result.success:
            message = f"Sauvegarde de sécurité préalable échouée : réinitialisation annulée. {backup_result.message}"
            logger.error(message)
            self._audit("BUSINESS_DATA_RESET_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message)

        logger.info("Sauvegarde de sécurité préalable créée et vérifiée : %s", backup_result.file_path)

        deleted_counts: dict[str, int] = {}
        try:
            with session_scope(self._settings) as session:
                for label, model in _DELETE_ORDER:
                    deleted_counts[label] = session.query(model).delete(synchronize_session=False)

                # Jamais commis si la base est corrompue par l'opération elle-même.
                integrity = session.execute(text("PRAGMA integrity_check")).scalar()
                if integrity != "ok":
                    raise ValidationError(
                        f"Vérification d'intégrité SQLite échouée après réinitialisation : {integrity!r}."
                    )
        except Exception as exc:
            # Rien n'a été commis (rollback automatique de session_scope) :
            # sûr d'affirmer qu'aucune donnée n'a été modifiée.
            message = f"Échec de la réinitialisation, aucune donnée n'a été modifiée (transaction annulée) : {exc}"
            logger.error(message)
            self._audit(
                "BUSINESS_DATA_RESET_FAILURE", ResultatAudit.ECHEC,
                details=f"{message} Sauvegarde de sécurité disponible : {backup_result.file_path}.",
            )
            raise ValidationError(message) from exc

        # À partir d'ici, la suppression a déjà été commise avec succès : une
        # anomalie détectée par cette vérification ne peut plus être annulée
        # (elle est donc auditée distinctement — jamais silencieuse), mais la
        # sauvegarde de sécurité créée plus haut reste disponible pour une
        # restauration manuelle si nécessaire.
        try:
            self._verify_preserved_data_intact()
        except ValidationError as exc:
            message = (
                f"Réinitialisation effectuée mais anomalie détectée à la vérification post-opération : {exc} "
                f"Sauvegarde de sécurité disponible pour restauration : {backup_result.file_path}."
            )
            logger.error(message)
            self._audit("BUSINESS_DATA_RESET_FAILURE", ResultatAudit.ECHEC, details=message)
            raise ValidationError(message) from exc

        summary = "; ".join(f"{label}={count}" for label, count in deleted_counts.items())
        self._audit(
            "BUSINESS_DATA_RESET_SUCCESS", ResultatAudit.SUCCES,
            details=f"Sauvegarde de sécurité : {backup_result.file_path}. Éléments supprimés : {summary}.",
        )
        logger.info("Réinitialisation des données métier réussie : %s", summary)

        return DataResetResult(
            success=True,
            message="Les données métier ont été réinitialisées avec succès. Une base propre est prête pour l'exploitation réelle.",
            backup_path=backup_result.file_path,
            deleted_counts=deleted_counts,
        )

    def _verify_preserved_data_intact(self) -> None:
        """Vérification défensive après coup (§ intégrité) : les données à
        conserver n'ont pas varié en nombre. Ne devrait jamais échouer étant
        donné l'ordre de suppression ci-dessus — une alerte forte (exception)
        si c'était le cas, plutôt qu'un succès silencieusement faux."""
        with session_scope(self._settings) as session:
            for model in _PRESERVED_MODELS:
                if session.query(model).count() == 0 and model is not Licence:
                    # Licence peut légitimement être absente (aucune licence
                    # activée) ; les autres (users/roles/permissions/parametres)
                    # ne devraient jamais l'être après un premier démarrage.
                    raise ValidationError(
                        f"Anomalie critique : la table {model.__tablename__!r} est vide après "
                        "réinitialisation alors qu'elle doit être préservée."
                    )
            for label, model in _DELETE_ORDER:
                remaining = session.query(model).count()
                if remaining != 0:
                    raise ValidationError(
                        f"Anomalie critique : {remaining} ligne(s) restante(s) dans {label!r} "
                        "après réinitialisation."
                    )
