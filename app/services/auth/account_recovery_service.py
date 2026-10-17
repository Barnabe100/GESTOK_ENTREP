"""Récupération du compte administrateur par code à usage unique.

Deux flux distincts, volontairement séparés :

- :meth:`AccountRecoveryService.generate_code` — appelé par un
  Administrateur **déjà authentifié**, pour générer ou régénérer son propre
  code (jamais celui d'un autre compte). Gardé par la permission RBAC
  ``ADMIN_RECOVERY_MANAGE`` comme toute action de ce service (voir
  ``app.services.auth.permission_service``).
- :meth:`AccountRecoveryService.reset_password_with_code` — appelé depuis
  l'écran de connexion, **avant toute authentification** : aucune
  permission RBAC n'a de sens ici (pas de session), l'éligibilité (rôle
  Administrateur, compte actif) est vérifiée directement sur l'utilisateur
  ciblé, comme ``AuthService.login``.

Anti-énumération stricte (§ lot) : ``reset_password_with_code`` lève
exactement la même exception, avec le même message, que l'identifiant soit
inconnu, le compte inactif, le compte sans rôle Administrateur, le compte
sans code généré, le code déjà consommé, le code faux, ou le compte
actuellement verrouillé — aucune de ces causes n'est jamais distinguée côté
appelant, seul le journal d'audit (jamais exposé à l'écran de connexion)
porte le détail réel. Une vérification Argon2 factice (temps constant) est
exécutée même quand aucun compte/code éligible n'existe, pour que la durée
de réponse ne varie pas selon que le compte existe ou non.

Compteur de tentatives et verrouillage : lus et modifiés dans la même
transaction (``session_scope``) que leur propre vérification, jamais une
lecture puis une écriture séparées — SQLite sérialise les transactions
d'écriture (un seul writer à la fois), ce qui rend ce motif sûr vis-à-vis
d'appels concurrents sans verrou applicatif supplémentaire (même principe
déjà utilisé partout ailleurs dans ce projet, ex. ``Article.qte_reservee``).
"""
from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy import case, update

from app.config.settings import Settings
from app.db.session import session_scope
from app.models.account_recovery import AdminRecoveryCode
from app.models.audit import AuditLog
from app.models.enums import ResultatAudit
from app.models.user import User
from app.security.password_hashing import hash_password, verify_password
from app.services.auth.permission_service import PermissionService
from app.utils.exceptions import InvalidCredentialsError, PermissionDeniedError, ValidationError
from app.utils.logging_config import get_logger
from app.models.mixins import utcnow

MIN_PASSWORD_LENGTH = 8
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)

# Message générique unique pour tout échec de ``reset_password_with_code`` —
# jamais un message distinct par cause (anti-énumération, voir docstring de
# module). Même principe que ``InvalidCredentialsError`` dans
# ``AuthService.login``.
_GENERIC_FAILURE_MESSAGE = (
    "Le code de récupération est invalide, déjà utilisé, ou ce compte ne "
    "peut pas l'utiliser actuellement."
)

logger = get_logger("services.auth.account_recovery")


def _validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
        )


def _is_eligible_administrator(user: Optional[User]) -> bool:
    return (
        user is not None
        and user.actif
        and any(role.nom == "Administrateur" for role in user.roles)
    )


class AccountRecoveryService:
    def __init__(self, permission_service: PermissionService, settings: Optional[Settings] = None) -> None:
        self._permissions = permission_service
        self._settings = settings
        # Hash factice calculé une fois par instance, jamais à partir d'une
        # chaîne vide ni réutilisé comme un vrai code — uniquement pour que
        # la vérification Argon2 (coûteuse, volontairement) s'exécute aussi
        # quand aucun compte/code éligible n'existe (temps de réponse
        # constant, voir docstring de module).
        self._dummy_hash = hash_password(secrets.token_urlsafe(16))

    def _acting_user_id(self) -> Optional[int]:
        current_user = self._permissions.current_user
        return current_user.id if current_user else None

    def _log_audit(self, session, user_id: Optional[int], action: str, resultat: ResultatAudit, details: Optional[str] = None) -> None:
        session.add(
            AuditLog(user_id=user_id, action=action, entite="admin_recovery", entite_id=user_id, details=details, resultat=resultat)
        )

    def generate_code(self) -> str:
        """Génère (ou régénère, invalidant l'ancien) le code de récupération
        de l'Administrateur actuellement connecté. Retourne le code en
        clair — une seule fois, jamais journalisé, jamais stocké ailleurs
        que dans la mémoire de l'appelant (qui doit l'afficher puis
        l'oublier)."""
        self._permissions.require_permission("ADMIN_RECOVERY_MANAGE")
        current_user = self._permissions.current_user
        if current_user is None:
            raise PermissionDeniedError("Aucun utilisateur connecté.")

        code = secrets.token_urlsafe(32)
        code_hash = hash_password(code)

        with session_scope(self._settings) as session:
            user = session.get(User, current_user.id)
            # Défense en profondeur : revérifie l'éligibilité directement sur
            # le compte, indépendamment de l'attribution RBAC de la
            # permission (qui ne devrait jamais être accordée hors du rôle
            # Administrateur, voir app/db/seed.py, mais ce service ne lui
            # fait jamais une confiance aveugle).
            if not _is_eligible_administrator(user):
                raise PermissionDeniedError("Seul un compte Administrateur actif peut générer un code de récupération.")

            existing = session.query(AdminRecoveryCode).filter_by(user_id=user.id).one_or_none()
            if existing is not None:
                existing.code_hash = code_hash
                existing.generated_at = utcnow()
                existing.consumed_at = None
                existing.failed_attempts = 0
                existing.locked_until = None
            else:
                session.add(AdminRecoveryCode(user_id=user.id, code_hash=code_hash))

            self._log_audit(session, user.id, "ADMIN_RECOVERY_CODE_GENERATED", ResultatAudit.SUCCES)

        logger.info("Code de récupération (ré)généré pour l'utilisateur %s (jamais journalisé en clair).", current_user.username)
        return code

    def reset_password_with_code(self, username: str, code: str, new_password: str) -> None:
        """Flux pré-authentification (écran de connexion). Lève
        :class:`InvalidCredentialsError` avec le même message générique pour
        toute cause d'échec (voir docstring de module) — jamais
        d'information permettant de distinguer les causes côté appelant."""
        pending_error: Optional[InvalidCredentialsError] = None

        with session_scope(self._settings) as session:
            user = session.query(User).filter_by(username=username).one_or_none()
            recovery: Optional[AdminRecoveryCode] = None
            if user is not None:
                recovery = session.query(AdminRecoveryCode).filter_by(user_id=user.id).one_or_none()

            eligible = (
                _is_eligible_administrator(user)
                and recovery is not None
                and recovery.consumed_at is None
            )

            # Naïf (sans fuseau) délibérément : SQLite perd le fuseau horaire
            # au retour (``AdminRecoveryCode.locked_until`` relu depuis la
            # base est toujours naïf), alors que ``utcnow()`` (partagé par
            # tout le projet) est conscient du fuseau — comparer les deux
            # directement lève ``TypeError``. On neutralise ici, localement,
            # sans toucher à ``utcnow()`` ni aux colonnes jamais comparées à
            # « maintenant » (``generated_at``/``consumed_at``).
            now = utcnow().replace(tzinfo=None)
            currently_locked = eligible and recovery.locked_until is not None and recovery.locked_until > now

            if currently_locked:
                self._log_audit(session, user.id, "ADMIN_RECOVERY_ATTEMPT", ResultatAudit.ECHEC, "Compte verrouillé temporairement")
                pending_error = InvalidCredentialsError(_GENERIC_FAILURE_MESSAGE)
            else:
                # Vérification Argon2 toujours exécutée (temps constant),
                # même sur le hash factice si aucun compte/code éligible
                # n'existe — jamais de court-circuit avant cette étape.
                code_is_valid = verify_password(code, recovery.code_hash if eligible else self._dummy_hash)

                if eligible and code_is_valid:
                    # Propage directement hors du bloc transactionnel si le
                    # mot de passe est trop faible (rollback complet via
                    # session_scope) — même principe que
                    # ``AuthService.change_password``, aucun audit d'échec
                    # écrit pour ce cas précis.
                    _validate_password_strength(new_password)
                    user.password_hash = hash_password(new_password)
                    user.must_change_password = False
                    recovery.consumed_at = now
                    recovery.failed_attempts = 0
                    recovery.locked_until = None
                    self._log_audit(session, user.id, "ADMIN_RECOVERY_SUCCESS", ResultatAudit.SUCCES)
                else:
                    if eligible:
                        # Incrément atomique côté SQL (jamais une lecture
                        # Python puis une écriture séparée) : sous SQLite,
                        # seule l'instruction UPDATE elle-même est
                        # sérialisée entre transactions concurrentes — un
                        # ``recovery.failed_attempts += 1`` calculé en
                        # mémoire Python, lui, perdrait des mises à jour
                        # concurrentes (confirmé par
                        # ``test_concurrent_failed_attempts_are_not_lost``,
                        # qui a détecté exactement ce défaut avant cette
                        # correction). Le seuil de verrouillage est évalué
                        # dans la même instruction, sur la valeur déjà
                        # incrémentée — jamais sur une valeur relue à part.
                        new_failed_attempts = AdminRecoveryCode.failed_attempts + 1
                        session.execute(
                            update(AdminRecoveryCode)
                            .where(AdminRecoveryCode.id == recovery.id)
                            .values(
                                failed_attempts=new_failed_attempts,
                                locked_until=case(
                                    (new_failed_attempts >= MAX_FAILED_ATTEMPTS, now + LOCKOUT_DURATION),
                                    else_=AdminRecoveryCode.locked_until,
                                ),
                            )
                        )
                        session.refresh(recovery)
                        detail = f"Code invalide (tentative {recovery.failed_attempts}/{MAX_FAILED_ATTEMPTS})"
                        if recovery.locked_until is not None:
                            detail += " — verrouillage temporaire déclenché"
                        self._log_audit(session, user.id, "ADMIN_RECOVERY_ATTEMPT", ResultatAudit.ECHEC, detail)
                    else:
                        self._log_audit(
                            session, user.id if user else None, "ADMIN_RECOVERY_ATTEMPT", ResultatAudit.ECHEC,
                            "Identifiant inconnu, compte inactif, non administrateur, code déjà utilisé, ou aucun code actif",
                        )
                    pending_error = InvalidCredentialsError(_GENERIC_FAILURE_MESSAGE)

        if pending_error is not None:
            raise pending_error

        logger.info("Mot de passe réinitialisé par code de récupération pour l'utilisateur %s.", username)
