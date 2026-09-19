"""État du guidage de premier lancement (Lot O) : un unique indicateur
persistant, stocké dans la table ``parametres`` existante (même mécanisme
que la configuration des sauvegardes, ``app.services.backups``) — aucune
table ni migration dédiée n'est nécessaire pour un simple drapeau.

``onboarding.completed`` est un indicateur d'APPLICATION (mono-poste, une
seule base partagée par tous les comptes), pas un état par utilisateur : une
fois le guidage fermé une première fois par l'administrateur initial, il ne
réapparaît plus automatiquement pour personne. Aucune vérification de
permission ici : ce drapeau ne porte aucune donnée sensible ni métier, et
n'est manipulé que par des écrans déjà eux-mêmes gardés (voir
``OnboardingDialog``, qui ne s'ouvre que pour l'administrateur initial ou
via un bouton gardé par ``SETTINGS_VIEW``).
"""
from __future__ import annotations

from typing import Optional

from app.config.settings import Settings
from app.db.session import session_scope
from app.repositories.parameter_repository import ParameterRepository

_KEY_COMPLETED = "onboarding.completed"
_VALUE_COMPLETED = "1"


class OnboardingService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings

    def is_completed(self) -> bool:
        with session_scope(self._settings) as session:
            return ParameterRepository(session).get_value(_KEY_COMPLETED) == _VALUE_COMPLETED

    def mark_completed(self) -> None:
        with session_scope(self._settings) as session:
            ParameterRepository(session).set_value(_KEY_COMPLETED, _VALUE_COMPLETED)

    def should_show_automatically(self, username: str, *, initial_admin_username: str) -> bool:
        """Vrai uniquement à la première connexion réussie du compte
        administrateur initial (``initial_admin_username``, voir
        ``app.db.seed.INITIAL_ADMIN_USERNAME``), tant que le guidage n'a
        jamais été fermé. Un second compte Administrateur créé plus tard ne
        déclenche jamais ce guidage automatiquement (l'entreprise est déjà
        censée avoir été configurée) — il reste néanmoins réouvrable
        manuellement, voir ``OnboardingDialog``."""
        return username == initial_admin_username and not self.is_completed()
