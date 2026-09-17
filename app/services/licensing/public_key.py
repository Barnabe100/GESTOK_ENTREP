"""Clé publique Ed25519 de production, embarquée dans le client.

Générée une seule fois par ``license_generator/generate_keypair.py`` (voir
son README) ; seule la clé publique quitte cet outil — la clé privée
correspondante n'existe que sur le poste de l'éditeur et n'est jamais
présente dans ce dépôt ni dans l'exécutable client.

Aucun autre module ne doit définir de clé publique de secours ni de valeur
« par défaut » alternative : ``LicenseService`` utilise cette constante sauf
injection explicite d'une clé de test (voir ``build_service_registry`` et
``tests/conftest.py``), qui ne concerne jamais le code de production.
"""
from __future__ import annotations

PRODUCTION_PUBLIC_KEY_HEX = "a0243ec0489cf39557bd1b1f6d2fc2a1d16c0038f4dc205f5bb31aac294400d1"

PRODUCTION_PUBLIC_KEY_BYTES = bytes.fromhex(PRODUCTION_PUBLIC_KEY_HEX)
