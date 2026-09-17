"""Primitives cryptographiques Ed25519 pures — aucune clé n'est stockée dans
ce module ; chaque fonction reçoit la clé à utiliser en paramètre explicite.

Voir ``public_key.py`` pour la clé publique de production embarquée côté
client, et ``license_generator/`` pour la génération et l'usage de la clé
privée, qui ne vit JAMAIS dans ce projet client (ni dans le dépôt public, ni
dans les tests distribués, ni dans l'exécutable — contrainte non négociable
de cette phase).
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def verify(public_key_bytes: bytes, message: bytes, signature: bytes) -> bool:
    """Ne lève jamais : retourne False pour toute signature invalide, clé ou
    signature mal formée, ou message altéré. La distinction fine des causes
    d'échec n'est pas nécessaire ici (``LicenseService`` décide du message
    utilisateur) ; cette fonction ne doit jamais interrompre la validation."""
    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, message)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
