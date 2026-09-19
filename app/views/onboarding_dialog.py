"""Guidage léger de premier lancement (Lot O).

Affiché une seule fois, automatiquement, à la première connexion réussie du
compte administrateur initial (voir ``OnboardingService.should_show_automatically``)
— jamais à chaque démarrage une fois fermé, et jamais pour un autre compte.
Reste réouvrable manuellement à tout moment depuis le bouton dédié de la
barre supérieure de ``MainWindow`` (gardé par ``SETTINGS_VIEW``).

Chaque étape ne s'affiche que si l'utilisateur courant possède la permission
nécessaire pour la consulter — jamais d'appel à une méthode de service
gardée sans avoir vérifié ``has_permission`` au préalable (même principe que
``AboutDialog``, Lot P). L'état « Terminé »/« À faire » de chaque étape est
recalculé en direct à chaque ouverture, à partir des données réelles —
jamais mémorisé séparément.

Toute fermeture du dialogue (bouton « Fermer », clic sur une étape qui
navigue puis referme, ou fermeture via la croix) marque le guidage comme
définitivement terminé (``OnboardingService.mark_completed``) : c'est un
simple coup de pouce ponctuel, pas un assistant à compléter obligatoirement
avant de pouvoir l'écarter — cohérent avec l'exigence d'un guidage « léger »
qui ne bloque jamais l'utilisation normale de l'application.

Ne gère ni le logo StockManager (identité du produit, voir ``AboutDialog``)
ni aucune coordonnée de support fictive : uniquement les informations de
l'entreprise cliente (``CompanySettingsService``, déjà distinctes de
l'identité StockManager, voir ``SettingsPage``).
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.services.auth.permission_service import PermissionService
from app.services.backups.backup_service import BackupService
from app.services.licensing.license_service import LicenseService, LicenseState
from app.services.onboarding.onboarding_service import OnboardingService
from app.services.settings.company_settings_service import CompanySettingsService
from app.services.users.user_service import UserService

_INTRO_TEXT = (
    "Quelques étapes recommandées pour finaliser la configuration de "
    "StockManager. Vous pouvez fermer ce guide à tout moment et le "
    "rouvrir plus tard depuis le bouton « Guide de démarrage »."
)


class OnboardingDialog(QDialog):
    def __init__(
        self,
        *,
        company_settings_service: CompanySettingsService,
        user_service: UserService,
        license_service: LicenseService,
        backup_service: BackupService,
        onboarding_service: OnboardingService,
        permission_service: PermissionService,
        on_navigate: Callable[[str, Optional[str]], bool],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._company_settings_service = company_settings_service
        self._user_service = user_service
        self._license_service = license_service
        self._backup_service = backup_service
        self._onboarding_service = onboarding_service
        self._permissions = permission_service
        self._on_navigate = on_navigate

        self.setWindowTitle("Bien démarrer avec StockManager")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        intro_label = QLabel(_INTRO_TEXT, self)
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        self._steps_layout = QVBoxLayout()
        layout.addLayout(self._steps_layout)
        self._build_steps()

        close_button = QPushButton("Fermer", self)
        close_button.clicked.connect(self.reject)
        layout.addWidget(close_button)

        # Toute façon de fermer le dialogue (bouton, croix, navigation vers
        # une étape) émet ``finished`` : un seul point d'écriture pour
        # marquer le guidage comme terminé, jamais de code dupliqué par
        # chemin de fermeture.
        self.finished.connect(lambda _result: self._onboarding_service.mark_completed())

    def _build_steps(self) -> None:
        if self._permissions.has_permission("SETTINGS_VIEW"):
            config = self._company_settings_service.get_config()
            self._add_step(
                "Informations de l'entreprise et devise",
                completed=bool(config.nom),
                button_label="Configurer",
                module_name="Paramètres",
            )
            self._add_step(
                "Logo de l'entreprise (optionnel)",
                completed=config.logo_path is not None,
                button_label="Configurer",
                module_name="Paramètres",
            )

        if self._permissions.has_permission("USER_VIEW"):
            users = self._user_service.list_users()
            self._add_step(
                "Utilisateurs",
                completed=len(users) > 1,
                button_label="Configurer",
                module_name="Utilisateurs",
            )

        if self._permissions.has_permission("LICENSE_VIEW"):
            info = self._license_service.get_info()
            self._add_step(
                "Licence",
                completed=info.state == LicenseState.VALID,
                button_label="Ouvrir",
                module_name="Licences",
            )

        if self._permissions.has_permission("BACKUP_VIEW"):
            backups = self._backup_service.list_backups()
            self._add_step(
                "Première sauvegarde",
                completed=len(backups) > 0,
                button_label="Ouvrir",
                module_name="Sauvegardes",
            )

    def _add_step(self, label: str, *, completed: bool, button_label: str, module_name: str) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel(label, self))
        row.addStretch(1)
        row.addWidget(QLabel("Terminé" if completed else "À faire", self))
        open_button = QPushButton(button_label, self)
        open_button.clicked.connect(lambda _checked=False, m=module_name: self._navigate(m))
        row.addWidget(open_button)
        self._steps_layout.addLayout(row)

    def _navigate(self, module_name: str) -> None:
        self._on_navigate(module_name, None)
        self.accept()
