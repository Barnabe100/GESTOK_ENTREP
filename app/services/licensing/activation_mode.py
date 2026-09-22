"""Mode d'activation d'une licence StockManager : ``LOCAL`` (comportement
actuel, fichier ``.lic`` vérifié et activé entièrement hors ligne) ou
``SERVER`` (préparation pour un futur serveur TechNova — non implémenté à ce
stade, voir ``license_server_client.py``).

Le mode est une propriété de CETTE INSTALLATION (persistée dans la table
``parametres``, comme ``license.device_id`` — voir ``ActivationService``),
jamais une propriété du fichier ``.lic`` lui-même : un même fichier de
licence peut être activé en LOCAL sur un poste et, plus tard, en SERVER sur
un autre, sans aucune incompatibilité de format.
"""
from __future__ import annotations

import enum
from typing import Optional


class ActivationMode(str, enum.Enum):
    LOCAL = "LOCAL"
    SERVER = "SERVER"

    @classmethod
    def from_stored_value(cls, value: Optional[str]) -> "ActivationMode":
        """Toujours ``LOCAL`` si la valeur stockée est absente ou invalide —
        par sécurité, ne jamais basculer silencieusement vers un mode qui
        suppose un serveur dont la disponibilité n'est pas garantie."""
        if value is None:
            return cls.LOCAL
        try:
            return cls(value)
        except ValueError:
            return cls.LOCAL


DEFAULT_ACTIVATION_MODE = ActivationMode.LOCAL
