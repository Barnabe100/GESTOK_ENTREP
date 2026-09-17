"""Hachage sécurisé des mots de passe (Argon2).

Utilisé par le modèle ``User`` (colonne ``password_hash``). Le flux
d'authentification complet (écran de connexion, session, contrôle des
permissions) sera implémenté dans une phase ultérieure ; ce module ne fournit
que la primitive cryptographique, indépendante de toute logique métier.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    """Retourne le hash Argon2 du mot de passe. Ne jamais stocker le mot de passe en clair."""
    if not plain_password:
        raise ValueError("Le mot de passe ne peut pas être vide.")
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Vérifie un mot de passe contre son hash. Retourne False si invalide (jamais d'exception)."""
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
