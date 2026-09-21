"""Données de référence : rôles, permissions et matrice permissions -> rôles.

Reflète telle quelle la matrice validée avec l'utilisateur. Ce ne sont pas
des données métier saisies par un opérateur : c'est un jeu de données de
référence nécessaire au fonctionnement du RBAC, réinjecté au premier
démarrage de l'application.
"""
from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.models.rbac import Permission, Role
from app.models.user import User
from app.security.password_hashing import hash_password
from app.utils.logging_config import get_logger

logger = get_logger("db.seed")

INITIAL_ADMIN_USERNAME = "admin"

# (code, libellé, module)
PERMISSIONS: list[tuple[str, str, str]] = [
    ("DASHBOARD_VIEW", "Consulter le tableau de bord", "dashboard"),
    ("ARTICLE_VIEW", "Consulter les articles", "articles"),
    ("ARTICLE_CREATE", "Créer un article", "articles"),
    ("ARTICLE_UPDATE", "Modifier un article", "articles"),
    ("ARTICLE_ACTIVATE", "Activer un article", "articles"),
    ("ARTICLE_DEACTIVATE", "Désactiver un article", "articles"),
    ("CATEGORY_VIEW", "Consulter les catégories", "categories"),
    ("CATEGORY_CREATE", "Créer une catégorie", "categories"),
    ("CATEGORY_UPDATE", "Modifier une catégorie", "categories"),
    ("CATEGORY_ACTIVATE", "Activer une catégorie", "categories"),
    ("CATEGORY_DEACTIVATE", "Désactiver une catégorie", "categories"),
    ("SUPPLIER_VIEW", "Consulter les fournisseurs", "fournisseurs"),
    ("SUPPLIER_CREATE", "Créer un fournisseur", "fournisseurs"),
    ("SUPPLIER_UPDATE", "Modifier un fournisseur", "fournisseurs"),
    ("SUPPLIER_ACTIVATE", "Activer un fournisseur", "fournisseurs"),
    ("SUPPLIER_DEACTIVATE", "Désactiver un fournisseur", "fournisseurs"),
    ("STOCK_REASON_VIEW", "Consulter les motifs de sortie", "motifs_sortie"),
    ("STOCK_REASON_CREATE", "Créer un motif de sortie", "motifs_sortie"),
    ("STOCK_REASON_UPDATE", "Modifier un motif de sortie", "motifs_sortie"),
    ("STOCK_REASON_ACTIVATE", "Activer un motif de sortie", "motifs_sortie"),
    ("STOCK_REASON_DEACTIVATE", "Désactiver un motif de sortie", "motifs_sortie"),
    ("STOCK_ENTRY_VIEW", "Consulter les entrées", "entrees"),
    ("STOCK_ENTRY_CREATE", "Créer une entrée", "entrees"),
    ("STOCK_ENTRY_UPDATE", "Modifier une entrée en brouillon", "entrees"),
    ("STOCK_ENTRY_VALIDATE", "Valider une entrée", "entrees"),
    ("STOCK_ENTRY_CANCEL", "Annuler une entrée validée", "entrees"),
    ("STOCK_EXIT_VIEW", "Consulter les sorties", "sorties"),
    ("STOCK_EXIT_CREATE", "Créer une sortie", "sorties"),
    ("STOCK_EXIT_UPDATE", "Modifier une sortie en brouillon", "sorties"),
    ("STOCK_EXIT_VALIDATE", "Valider une sortie", "sorties"),
    ("STOCK_EXIT_CANCEL", "Annuler une sortie validée", "sorties"),
    ("SALE_VIEW", "Consulter les ventes", "ventes"),
    ("SALE_CREATE", "Créer une vente", "ventes"),
    ("SALE_UPDATE", "Modifier une vente en brouillon", "ventes"),
    ("SALE_VALIDATE", "Valider une vente", "ventes"),
    ("SALE_CANCEL", "Annuler une vente validée", "ventes"),
    ("SALE_PAYMENT_CREATE", "Enregistrer un paiement sur une vente", "ventes"),
    ("CLIENT_VIEW", "Consulter les clients", "clients"),
    ("CLIENT_CREATE", "Créer un client", "clients"),
    ("CLIENT_UPDATE", "Modifier un client", "clients"),
    ("CLIENT_ACTIVATE", "Activer un client", "clients"),
    ("CLIENT_DEACTIVATE", "Désactiver un client", "clients"),
    ("STOCK_MOVEMENT_VIEW", "Consulter les mouvements de stock", "mouvements"),
    ("INVENTORY_VIEW", "Consulter les inventaires", "inventaires"),
    ("INVENTORY_CREATE", "Créer un inventaire", "inventaires"),
    ("INVENTORY_UPDATE", "Modifier un inventaire en brouillon", "inventaires"),
    ("INVENTORY_VALIDATE", "Valider un inventaire", "inventaires"),
    ("REPORT_VIEW", "Consulter les rapports", "rapports"),
    ("REPORT_EXPORT", "Exporter un rapport", "rapports"),
    ("USER_VIEW", "Consulter les utilisateurs", "utilisateurs"),
    ("USER_CREATE", "Créer un utilisateur", "utilisateurs"),
    ("USER_UPDATE", "Modifier un utilisateur", "utilisateurs"),
    ("USER_ACTIVATE", "Activer/désactiver un compte utilisateur", "utilisateurs"),
    ("USER_RESET_PASSWORD", "Réinitialiser le mot de passe d'un utilisateur", "utilisateurs"),
    ("ROLE_VIEW", "Consulter les rôles et permissions", "roles"),
    ("ROLE_UPDATE", "Modifier les permissions d'un rôle", "roles"),
    ("SETTINGS_VIEW", "Consulter les paramètres", "parametres"),
    ("SETTINGS_UPDATE", "Modifier les paramètres", "parametres"),
    ("BACKUP_VIEW", "Consulter l'historique des sauvegardes", "sauvegardes"),
    ("BACKUP_CREATE", "Lancer une sauvegarde", "sauvegardes"),
    ("BACKUP_RESTORE", "Restaurer une sauvegarde", "restauration"),
    ("AUDIT_VIEW", "Consulter le journal d'audit", "audit"),
    ("LICENSE_VIEW", "Consulter la licence", "licences"),
    ("LICENSE_ACTIVATE", "Activer une licence", "licences"),
    (
        "SYSTEM_RESET_BUSINESS_DATA",
        "Réinitialiser les données métier (après une période de test)",
        "systeme",
    ),
]

_ALL_CODES = [code for code, _, _ in PERMISSIONS]

_GESTIONNAIRE_STOCK_CODES = [
    "DASHBOARD_VIEW",
    "ARTICLE_VIEW", "ARTICLE_CREATE", "ARTICLE_UPDATE", "ARTICLE_ACTIVATE", "ARTICLE_DEACTIVATE",
    "CATEGORY_VIEW", "CATEGORY_CREATE", "CATEGORY_UPDATE", "CATEGORY_ACTIVATE", "CATEGORY_DEACTIVATE",
    "SUPPLIER_VIEW", "SUPPLIER_CREATE", "SUPPLIER_UPDATE", "SUPPLIER_ACTIVATE", "SUPPLIER_DEACTIVATE",
    # Les motifs de sortie (STOCK_REASON_*) sont réservés à l'Administrateur (décision
    # métier explicite de cette phase) : le Gestionnaire de stock ne les reçoit pas,
    # y compris STOCK_REASON_VIEW.
    "STOCK_ENTRY_VIEW", "STOCK_ENTRY_CREATE", "STOCK_ENTRY_UPDATE", "STOCK_ENTRY_VALIDATE",
    "STOCK_EXIT_VIEW", "STOCK_EXIT_CREATE", "STOCK_EXIT_UPDATE", "STOCK_EXIT_VALIDATE",
    "STOCK_MOVEMENT_VIEW",
    "INVENTORY_VIEW", "INVENTORY_CREATE", "INVENTORY_UPDATE", "INVENTORY_VALIDATE",
    "REPORT_VIEW", "REPORT_EXPORT",
    "CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE", "CLIENT_ACTIVATE", "CLIENT_DEACTIVATE",
]

_VENDEUR_CODES = [
    "DASHBOARD_VIEW",
    "ARTICLE_VIEW",
    "SALE_VIEW", "SALE_CREATE", "SALE_UPDATE", "SALE_VALIDATE", "SALE_PAYMENT_CREATE",
    # Le Vendeur peut rechercher/sélectionner et créer un client à la volée
    # au moment de la vente, mais jamais activer/désactiver un compte client
    # (décision métier explicite de ce lot).
    "CLIENT_VIEW", "CLIENT_CREATE", "CLIENT_UPDATE",
]

_CONSULTATION_CODES = [
    "DASHBOARD_VIEW",
    "ARTICLE_VIEW", "CATEGORY_VIEW", "SUPPLIER_VIEW",
    "STOCK_MOVEMENT_VIEW",
    "REPORT_VIEW",
]

# nom du rôle -> codes de permission (Administrateur = toutes, calculé)
ROLE_PERMISSIONS_MATRIX: dict[str, list[str]] = {
    "Administrateur": _ALL_CODES,
    "Gestionnaire de stock": _GESTIONNAIRE_STOCK_CODES,
    "Vendeur": _VENDEUR_CODES,
    "Consultation": _CONSULTATION_CODES,
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "Administrateur": "Accès complet à l'application.",
    "Gestionnaire de stock": "Gestion du catalogue et des mouvements de stock.",
    "Vendeur": "Création et validation des ventes.",
    "Consultation": "Accès en lecture seule aux données autorisées.",
}


def seed_reference_data(session: Session, force: bool = False) -> None:
    """Insère rôles, permissions et associations rôle->permissions si absentes.

    Ne touche à rien si des rôles existent déjà, sauf ``force=True`` (les
    permissions éventuellement modifiées manuellement en base seraient alors
    réalignées sur la matrice validée).
    """
    if not force and session.query(Role).count() > 0:
        logger.info("Données de référence déjà présentes : seed ignoré.")
        return

    permissions_by_code: dict[str, Permission] = {
        p.code: p for p in session.query(Permission).all()
    }
    for code, libelle, module in PERMISSIONS:
        if code not in permissions_by_code:
            permission = Permission(code=code, libelle=libelle, module=module)
            session.add(permission)
            permissions_by_code[code] = permission
    session.flush()

    roles_by_name: dict[str, Role] = {r.nom: r for r in session.query(Role).all()}
    for role_name, permission_codes in ROLE_PERMISSIONS_MATRIX.items():
        role = roles_by_name.get(role_name)
        if role is None:
            role = Role(nom=role_name, description=ROLE_DESCRIPTIONS[role_name])
            session.add(role)
            roles_by_name[role_name] = role
        role.permissions = [permissions_by_code[code] for code in permission_codes]

    session.flush()
    logger.info(
        "Données de référence initialisées : %d rôles, %d permissions.",
        len(roles_by_name),
        len(permissions_by_code),
    )


def seed_initial_admin(session: Session) -> Optional[str]:
    """Crée le compte Administrateur initial si aucun utilisateur n'existe.

    Le mot de passe est généré aléatoirement (jamais stocké en clair) et
    retourné une seule fois à l'appelant, à charge pour lui de le
    communiquer à l'opérateur (journal de démarrage). ``must_change_password``
    force son changement dès la première connexion.

    Retourne le mot de passe généré, ou None si un utilisateur existe déjà
    (aucune action effectuée).
    """
    if session.query(User).count() > 0:
        return None

    admin_role = session.query(Role).filter_by(nom="Administrateur").one()
    generated_password = secrets.token_urlsafe(12)

    admin_user = User(
        username=INITIAL_ADMIN_USERNAME,
        password_hash=hash_password(generated_password),
        role_id=admin_role.id,
        roles=[admin_role],
        actif=True,
        must_change_password=True,
    )
    session.add(admin_user)
    session.flush()

    logger.info("Compte administrateur initial créé : %r", INITIAL_ADMIN_USERNAME)
    return generated_password
