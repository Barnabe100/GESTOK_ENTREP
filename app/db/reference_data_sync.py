"""Synchronisation ADDITIVE des données de référence (permissions/rôles)
pour une base déjà initialisée.

Distinct de ``seed_reference_data`` (``app.db.seed``), qui ne peuple qu'une
base neuve (table ``roles`` vide) : cette fonction est le mécanisme de mise
à niveau d'une installation existante, exécuté à chaque démarrage, qui
rattrape les permissions ajoutées au code par des versions ultérieures de
l'application sans jamais toucher à ce qui existe déjà.

Règles strictes (jamais dérogées) :
- Aucune permission n'est supprimée.
- Aucun rôle n'est supprimé.
- Aucune association rôle -> permission existante n'est retirée, y compris
  celles qui ne figurent pas dans ``ROLE_PERMISSIONS_MATRIX`` (personnalisation
  administrative faite depuis l'écran des rôles).
- Seuls des ajouts sont effectués : permissions manquantes créées, puis
  associations manquantes ajoutées aux rôles système existants.
- Idempotent : un deuxième appel sans changement de code source ne produit
  aucune modification.
- Ne crée jamais de rôle : un rôle absent (ex. base initialisée par une
  version antérieure à l'introduction de ce rôle) est du ressort de
  ``seed_reference_data`` à l'initialisation, pas de cette synchronisation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.seed import PERMISSIONS, ROLE_PERMISSIONS_MATRIX
from app.models.rbac import Permission, Role
from app.utils.logging_config import get_logger

logger = get_logger("db.reference_data_sync")


@dataclass(frozen=True)
class ReferenceDataSyncResult:
    """Ce qui a été ajouté par un appel à :func:`sync_reference_data` — vide
    si la base était déjà à jour (cas idempotent)."""

    permissions_created: list[str] = field(default_factory=list)
    role_permissions_added: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(self.permissions_created) or bool(self.role_permissions_added)


def sync_reference_data(session: Session) -> ReferenceDataSyncResult:
    """Ajoute les permissions et associations rôle->permission manquantes,
    sans jamais rien retirer ni écraser.

    1. Toute permission de ``PERMISSIONS`` absente de la table ``permissions``
       est créée (code/libellé/module tels que définis dans le code).
    2. Pour chaque rôle système déjà présent en base (rôle absent = ignoré,
       hors périmètre), toute permission attendue par
       ``ROLE_PERMISSIONS_MATRIX`` qui ne lui est pas encore associée est
       ajoutée à son jeu de permissions existant (jamais de réaffectation
       complète, qui écraserait une personnalisation administrative).
    """
    permissions_by_code: dict[str, Permission] = {
        p.code: p for p in session.query(Permission).all()
    }

    created_codes: list[str] = []
    for code, libelle, module in PERMISSIONS:
        if code not in permissions_by_code:
            permission = Permission(code=code, libelle=libelle, module=module)
            session.add(permission)
            permissions_by_code[code] = permission
            created_codes.append(code)

    if created_codes:
        session.flush()

    roles_by_name: dict[str, Role] = {r.nom: r for r in session.query(Role).all()}

    added_by_role: dict[str, list[str]] = {}
    for role_name, expected_codes in ROLE_PERMISSIONS_MATRIX.items():
        role = roles_by_name.get(role_name)
        if role is None:
            continue  # rôle système pas encore créé : hors périmètre du sync additif.

        current_codes = {p.code for p in role.permissions}
        missing_codes = [code for code in expected_codes if code not in current_codes]
        if missing_codes:
            role.permissions.extend(permissions_by_code[code] for code in missing_codes)
            added_by_role[role_name] = missing_codes

    if created_codes or added_by_role:
        session.flush()
        logger.info(
            "Synchronisation des données de référence : %d permission(s) créée(s) (%s), "
            "associations ajoutées pour %d rôle(s) (%s).",
            len(created_codes), ", ".join(created_codes) or "-",
            len(added_by_role), ", ".join(added_by_role) or "-",
        )
    else:
        logger.info("Synchronisation des données de référence : déjà à jour, aucun changement.")

    return ReferenceDataSyncResult(permissions_created=created_codes, role_permissions_added=added_by_role)
