"""Hiérarchie d'exceptions applicatives.

Les services métier des phases suivantes lèveront des sous-classes de
``AppError`` plutôt que des exceptions génériques, afin que la couche UI et
le gestionnaire d'erreurs centralisé puissent les traiter de façon uniforme.
"""
from __future__ import annotations


class AppError(Exception):
    """Racine de toutes les erreurs applicatives connues."""


class ValidationError(AppError):
    """Une règle de validation métier n'est pas respectée."""


class NotFoundError(AppError):
    """L'entité demandée n'existe pas."""


class ConflictError(AppError):
    """L'opération entre en conflit avec l'état actuel des données
    (ex. référence déjà utilisée, opération déjà validée)."""


class PermissionDeniedError(AppError):
    """L'utilisateur courant n'a pas la permission requise."""


class AuthenticationError(AppError):
    """Échec d'authentification."""


class InvalidCredentialsError(AuthenticationError):
    """Identifiant ou mot de passe invalide.

    Volontairement le même type d'exception pour un utilisateur inconnu et
    pour un mot de passe erroné (ne jamais révéler si un identifiant existe)."""


class AccountDisabledError(AuthenticationError):
    """Le compte existe et les identifiants sont corrects, mais il est désactivé."""


class DatabaseError(AppError):
    """Erreur d'accès aux données (connexion, transaction, intégrité)."""


class ConfigurationError(AppError):
    """La configuration de l'application est invalide ou incomplète."""
