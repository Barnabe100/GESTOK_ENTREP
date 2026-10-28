"""Dialogue de correction — serveur PostgreSQL injoignable au démarrage
(phase accès réseau/déconnexion auto/permissions Consultant, point 1).

Affiché par ``app.main`` lorsque :func:`app.main.bootstrap` échoue alors que
le moteur configuré est PostgreSQL (``settings.db_backend == "postgresql"``)
— jamais pour un déploiement scripté (``STOCKMANAGER_DB_BACKEND`` défini)
ni pour SQLite (pas de recours réseau applicable ici), voir
``app.main._recover_from_startup_failure``.

Mêmes garanties que ``DatabaseSetupWizard`` (dont ce dialogue reprend la
logique, avant toute authentification possible à ce stade) :

- utilise exclusivement les fonctions ``*_unchecked`` de
  ``app.services.database_admin.database_admin_service`` (sans contrôle de
  permission RBAC — aucun utilisateur n'est encore connecté) ;
- ne lit, n'affiche ni ne journalise jamais le mot de passe actif (jamais
  relu depuis le coffre d'identifiants pour pré-remplissage — seuls
  l'hôte/le port/la base/l'utilisateur, non secrets, sont pré-remplis) ;
- ne modifie jamais le schéma de base de données (aucun appel Alembic
  ici) — seule la configuration externe
  (``app.config.db_config_store``) est écrite.

Différence délibérée avec l'assistant de première configuration : la
configuration corrigée est appliquée **immédiatement** comme ``active``
(jamais seulement ``pending`` + redémarrage requis) — légitime uniquement
parce qu'aucune connexion n'a encore jamais réussi pour ce processus (la
règle « jamais de changement de moteur actif en cours de session », qui
protège une session déjà démarrée avec succès, ne s'applique pas à un
démarrage qui n'a encore jamais abouti). Ce dialogue n'appelle cependant
jamais lui-même :func:`app.main.bootstrap` — il se limite strictement à la
saisie et à l'enregistrement ; c'est à l'appelant de relancer le
démarrage après un ``Accepted``.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config.db_config_store import default_db_config_path, promote_pending_to_active
from app.config.settings import DEFAULT_POSTGRESQL_PORT, Settings
from app.services.database_admin.database_admin_service import (
    prepare_postgresql_pending_config_unchecked,
    prepare_sqlite_pending_config_unchecked,
    test_postgresql_connection_unchecked,
)
from app.utils.exceptions import AppError
from app.views.password_line_edit import PasswordLineEdit

GENERIC_UNREACHABLE_MESSAGE = (
    "Le serveur PostgreSQL configuré est actuellement inaccessible (connexion "
    "refusée, serveur arrêté, ou paramètres invalides)."
)


def startup_failure_message(exc: Exception) -> str:
    """Même convention que ``app.main._show_fatal_startup_error`` : une
    ``AppError`` est, par construction de ce projet, déjà un message
    métier sûr à afficher tel quel ; toute autre exception (ex. erreur
    SQLAlchemy/psycopg brute, pouvant contenir la chaîne de connexion ou
    d'autres détails techniques) ne doit jamais être interpolée
    directement — message générique fixe à la place."""
    if isinstance(exc, AppError):
        return str(exc)
    return GENERIC_UNREACHABLE_MESSAGE


class DatabaseUnreachableDialog(QDialog):
    """Retourne ``Accepted`` si une nouvelle configuration a été
    enregistrée comme active (PostgreSQL corrigé ou bascule explicite vers
    SQLite) — à l'appelant de relancer :func:`app.main.bootstrap` ensuite.
    ``Rejected`` (bouton Quitter, croix) signifie que l'utilisateur
    renonce : l'appelant doit alors traiter l'échec d'origine comme
    fatal, exactement comme avant ce lot."""

    def __init__(self, settings: Settings, failure: Exception, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._config_path = default_db_config_path(settings.data_dir)

        self.setWindowTitle("Connexion à la base de données impossible")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        self.error_label = QLabel(startup_failure_message(failure), self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #DC2626; font-weight: bold;")
        layout.addWidget(self.error_label)

        intro = QLabel(
            "Corrigez les paramètres de connexion ci-dessous puis réessayez, ou "
            "basculez temporairement sur SQLite (base locale à ce poste) pour "
            "continuer à utiliser l'application en attendant que le serveur "
            "redevienne accessible.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.postgresql_radio = QRadioButton("PostgreSQL (corriger les paramètres)", self)
        self.postgresql_radio.setChecked(True)
        self.sqlite_radio = QRadioButton("Utiliser SQLite pour cette installation", self)
        layout.addWidget(self.postgresql_radio)
        layout.addWidget(self.sqlite_radio)

        self.postgresql_group = self._build_postgresql_group(settings)
        layout.addWidget(self.postgresql_group)
        self.postgresql_radio.toggled.connect(self.postgresql_group.setEnabled)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons_layout = QHBoxLayout()
        self.quit_button = QPushButton("Quitter l'application", self)
        self.quit_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.quit_button)
        buttons_layout.addStretch(1)
        self.retry_button = QPushButton("Enregistrer et réessayer", self)
        self.retry_button.setDefault(True)
        self.retry_button.clicked.connect(self._on_retry_clicked)
        buttons_layout.addWidget(self.retry_button)
        layout.addLayout(buttons_layout)

    def _build_postgresql_group(self, settings: Settings) -> QGroupBox:
        group = QGroupBox("Paramètres de connexion PostgreSQL", self)
        form = QFormLayout(group)

        # Pré-rempli avec la configuration active (jamais le mot de passe,
        # voir docstring de module) — ``settings.postgresql`` est toujours
        # défini ici en pratique (ce dialogue n'est affiché que si
        # ``db_backend == "postgresql"``, voir app.main).
        active_pg = settings.postgresql

        self.host_edit = QLineEdit(group)
        self.host_edit.setText(active_pg.host if active_pg else "")
        form.addRow("Hôte", self.host_edit)

        self.port_spin = QSpinBox(group)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(active_pg.port if active_pg else DEFAULT_POSTGRESQL_PORT)
        form.addRow("Port", self.port_spin)

        self.database_edit = QLineEdit(group)
        self.database_edit.setText(active_pg.database if active_pg else "")
        form.addRow("Base de données", self.database_edit)

        self.username_edit = QLineEdit(group)
        self.username_edit.setText(active_pg.username if active_pg else "")
        form.addRow("Utilisateur", self.username_edit)

        self.password_edit = PasswordLineEdit(group)
        form.addRow("Mot de passe", self.password_edit)

        self.test_connection_button = QPushButton("Tester la connexion", group)
        self.test_connection_button.clicked.connect(self._on_test_connection_clicked)
        form.addRow("", self.test_connection_button)

        return group

    def _on_test_connection_clicked(self) -> None:
        self.status_label.setStyleSheet("color: #374151;")
        self.status_label.setText("Test de connexion en cours…")
        try:
            test_postgresql_connection_unchecked(
                self._settings,
                host=self.host_edit.text().strip(), port=self.port_spin.value(),
                database=self.database_edit.text().strip(), username=self.username_edit.text().strip(),
                password=self.password_edit.text(),
            )
        except AppError as exc:
            self.status_label.setStyleSheet("color: #DC2626;")
            self.status_label.setText(str(exc))
            return
        self.status_label.setStyleSheet("color: #16A34A;")
        self.status_label.setText("Connexion réussie.")

    def _on_retry_clicked(self) -> None:
        try:
            if self.sqlite_radio.isChecked():
                prepare_sqlite_pending_config_unchecked(self._config_path)
            else:
                prepare_postgresql_pending_config_unchecked(
                    self._config_path,
                    host=self.host_edit.text().strip(), port=self.port_spin.value(),
                    database=self.database_edit.text().strip(), username=self.username_edit.text().strip(),
                    password=self.password_edit.text(),
                )
        except AppError as exc:
            self.status_label.setStyleSheet("color: #DC2626;")
            self.status_label.setText(str(exc))
            return

        # Légitime uniquement ici : aucune connexion n'a encore jamais
        # réussi pour ce processus (voir docstring de module).
        promote_pending_to_active(self._config_path)
        self.accept()
