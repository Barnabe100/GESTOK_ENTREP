"""Dialogue « À propos » (Lot P) : identité du produit StockManager,
jamais celle de l'entreprise cliente (voir ``SettingsPage``, dont le logo/
les coordonnées gérées appartiennent au client, pas au produit).

Le bloc licence n'est affiché — et ``LicenseService.get_info()`` n'est
appelé — que si l'utilisateur courant possède ``LICENSE_VIEW`` (seul
l'Administrateur l'a, voir ``app.db.seed``) : jamais d'appel à une méthode
gardée par une permission que l'utilisateur n'a pas, jamais d'exception
``PermissionDeniedError`` provoquée depuis ce dialogue.

Aucune coordonnée de support (email/téléphone/site) n'existe dans le
projet : la section Support renvoie génériquement vers la documentation
utilisateur et les fichiers de diagnostic/log, sans rien inventer.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from app.resources import APP_LOGO_FULL_PATH
from app.services.auth.permission_service import PermissionService
from app.services.licensing.license_service import LicenseService, LicenseState
from app.version import APP_NAME, PUBLISHER_NAME, __version__

_LOGO_MAX_WIDTH_PX = 280

_STATE_LABELS = {
    LicenseState.VALID: "Valide",
    LicenseState.EXPIRED: "Expirée",
    LicenseState.MISSING: "Aucune licence activée",
    LicenseState.INVALID: "Invalide",
    LicenseState.CORRUPTED: "Corrompue",
}

_SUPPORT_TEXT = (
    "Pour obtenir de l'aide, consultez la documentation utilisateur et les "
    "fichiers de diagnostic/log de l'application."
)


class AboutDialog(QDialog):
    def __init__(
        self,
        license_service: LicenseService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("À propos de StockManager")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        if APP_LOGO_FULL_PATH.exists():
            logo_pixmap = QPixmap(str(APP_LOGO_FULL_PATH))
            if not logo_pixmap.isNull():
                logo_label = QLabel(self)
                # Proportions jamais déformées : mise à l'échelle par largeur
                # maximale avec KeepAspectRatio, jamais un redimensionnement
                # forcé en largeur ET hauteur.
                logo_label.setPixmap(
                    logo_pixmap.scaledToWidth(
                        min(_LOGO_MAX_WIDTH_PX, logo_pixmap.width()),
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                logo_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                layout.addWidget(logo_label)

        identity_form = QFormLayout()
        identity_form.addRow("Nom", QLabel(APP_NAME, self))
        identity_form.addRow("Version", QLabel(__version__, self))
        identity_form.addRow("Éditeur", QLabel(PUBLISHER_NAME, self))
        layout.addLayout(identity_form)

        if permission_service.has_permission("LICENSE_VIEW"):
            layout.addWidget(self._build_license_group(license_service))

        layout.addWidget(self._build_support_group())

    def _build_license_group(self, license_service: LicenseService) -> QGroupBox:
        info = license_service.get_info()

        group = QGroupBox("Licence", self)
        form = QFormLayout(group)
        form.addRow("État", QLabel(_STATE_LABELS.get(info.state, info.state.value), group))
        form.addRow("Édition", QLabel(info.edition.value if info.edition else "—", group))
        return group

    def _build_support_group(self) -> QGroupBox:
        group = QGroupBox("Support", self)
        layout = QVBoxLayout(group)
        support_label = QLabel(_SUPPORT_TEXT, group)
        support_label.setWordWrap(True)
        layout.addWidget(support_label)
        return group
