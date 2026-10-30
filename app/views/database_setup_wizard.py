"""Assistant de première configuration de la base de données (Lot D.5).

Affiché, au tout premier démarrage seulement (voir
``app.main._is_first_run``), **avant toute authentification** : aucun
utilisateur n'existe encore à ce stade (le compte administrateur initial
n'est créé qu'un peu plus tard par ``app.db.seed.seed_initial_admin``,
appelé par ``app.main.bootstrap``). C'est pourquoi ce dialogue appelle les
fonctions ``*_unchecked`` de
``app.services.database_admin.database_admin_service`` directement,
jamais via ``DatabaseAdminService`` (qui exige une permission RBAC
vérifiable, donc un utilisateur déjà connecté) — voir la docstring de ce
module de service pour la justification complète de cette séparation.

Ne confond jamais (§D.5 du mandat) :
- un test de connexion réussi (``_on_test_connection_clicked`` — ne persiste
  jamais rien) ;
- la préparation d'une configuration en attente (``_on_finish_clicked``
  pour PostgreSQL — écrit ``pending``, jamais ``active``) ;
- l'application effective de cette configuration (jamais faite par ce
  dialogue ni par aucun code synchrone de ce processus — seulement au
  prochain démarrage complet, voir ``app.main.apply_pending_db_config_if_any``).

SQLite reste toujours l'option présélectionnée et la plus simple à
valider (aucune saisie requise) — fermer ce dialogue sans rien choisir
d'autre laisse l'installation strictement inchangée.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
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

from app.config.db_config_store import default_db_config_path
from app.config.settings import DEFAULT_POSTGRESQL_PORT, Settings
from app.security.credential_vault import get_credential_vault
from app.services.database_admin.database_admin_service import (
    prepare_postgresql_pending_config_unchecked,
    test_postgresql_connection_unchecked,
)
from app.utils.exceptions import AppError
from app.views.password_line_edit import PasswordLineEdit

_INTRO_TEXT = (
    "Bienvenue dans StockManager Desktop. Choisissez le moteur de base de données à "
    "utiliser. SQLite convient à un poste unique et ne nécessite aucune configuration "
    "supplémentaire. PostgreSQL convient à un usage en réseau, mais nécessite un "
    "serveur déjà préparé par un administrateur PostgreSQL."
)

_RESTART_NOTICE = (
    "Configuration PostgreSQL enregistrée. Elle sera appliquée au prochain démarrage "
    "complet de StockManager Desktop — fermez puis relancez l'application. "
    "StockManager continuera d'utiliser SQLite pour cette session en cours."
)


class DatabaseSetupWizard(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._config_path = default_db_config_path(settings.data_dir)
        self._restart_notice_shown = False

        self.setWindowTitle("Première configuration — Base de données")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        intro = QLabel(_INTRO_TEXT, self)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.sqlite_radio = QRadioButton("SQLite (recommandé pour un poste unique)", self)
        self.sqlite_radio.setChecked(True)
        self.postgresql_radio = QRadioButton("PostgreSQL (serveur réseau déjà préparé)", self)
        layout.addWidget(self.sqlite_radio)
        layout.addWidget(self.postgresql_radio)

        self.postgresql_group = self._build_postgresql_group()
        self.postgresql_group.setEnabled(False)
        layout.addWidget(self.postgresql_group)

        self.sqlite_radio.toggled.connect(self._on_sqlite_selected)
        self.postgresql_radio.toggled.connect(self._on_postgresql_selected)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons_layout = QHBoxLayout()
        self.later_button = QPushButton("Configurer plus tard", self)
        self.later_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.later_button)
        buttons_layout.addStretch(1)
        self.finish_button = QPushButton("Terminer", self)
        self.finish_button.setProperty("variant", "primary")
        self.finish_button.setDefault(True)
        self.finish_button.clicked.connect(self._on_finish_clicked)
        buttons_layout.addWidget(self.finish_button)
        layout.addLayout(buttons_layout)

    def _build_postgresql_group(self) -> QGroupBox:
        group = QGroupBox("Paramètres de connexion PostgreSQL", self)
        form = QFormLayout(group)

        self.host_edit = QLineEdit(group)
        form.addRow("Hôte", self.host_edit)

        self.port_spin = QSpinBox(group)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(DEFAULT_POSTGRESQL_PORT)
        form.addRow("Port", self.port_spin)

        self.database_edit = QLineEdit(group)
        form.addRow("Base de données", self.database_edit)

        self.username_edit = QLineEdit(group)
        form.addRow("Utilisateur", self.username_edit)

        self.password_edit = PasswordLineEdit(group)
        form.addRow("Mot de passe", self.password_edit)

        self.test_connection_button = QPushButton("Tester la connexion", group)
        self.test_connection_button.clicked.connect(self._on_test_connection_clicked)
        form.addRow("", self.test_connection_button)

        return group

    def _on_sqlite_selected(self, checked: bool) -> None:
        # Qt émet aussi ce signal avec checked=False lorsque l'utilisateur
        # bascule vers PostgreSQL (groupe exclusif) : seule la transition
        # vers True concerne vraiment ce gestionnaire — l'autre moitié de
        # la bascule est traitée par _on_postgresql_selected ci-dessous.
        if not checked:
            return
        self.postgresql_group.setEnabled(False)

    def _on_postgresql_selected(self, checked: bool) -> None:
        if not checked:
            return

        self.status_label.setText("")

        # §4.4 du mandat : le coffre sécurisé est vérifié avant même
        # d'accepter une saisie de mot de passe — jamais seulement au
        # moment d'enregistrer.
        try:
            get_credential_vault()
        except AppError as exc:
            self.postgresql_group.setEnabled(False)
            # Déclenche _on_sqlite_selected(True) (désactive le groupe,
            # déjà fait ci-dessus) et, par exclusivité, un nouvel appel à
            # _on_postgresql_selected(False) — sans effet (voir le garde
            # ci-dessus) : jamais de nouvel appel à setText après ce point.
            self.sqlite_radio.setChecked(True)
            self.status_label.setStyleSheet("color: #DC2626;")
            self.status_label.setText(
                "PostgreSQL indisponible sur ce poste : " + str(exc)
            )
            return

        self.postgresql_group.setEnabled(True)

    def _on_test_connection_clicked(self) -> None:
        self.status_label.setStyleSheet("color: #374151;")
        self.status_label.setText("Test de connexion en cours…")
        try:
            test_postgresql_connection_unchecked(
                self._settings,
                host=self.host_edit.text().strip(),
                port=self.port_spin.value(),
                database=self.database_edit.text().strip(),
                username=self.username_edit.text().strip(),
                password=self.password_edit.text(),
            )
        except AppError as exc:
            self.status_label.setStyleSheet("color: #DC2626;")
            self.status_label.setText(str(exc))
            return
        self.status_label.setStyleSheet("color: #16A34A;")
        self.status_label.setText("Connexion réussie.")

    def _on_finish_clicked(self) -> None:
        if self.sqlite_radio.isChecked():
            self.accept()
            return

        try:
            prepare_postgresql_pending_config_unchecked(
                self._config_path,
                host=self.host_edit.text().strip(),
                port=self.port_spin.value(),
                database=self.database_edit.text().strip(),
                username=self.username_edit.text().strip(),
                password=self.password_edit.text(),
            )
        except AppError as exc:
            self.status_label.setStyleSheet("color: #DC2626;")
            self.status_label.setText(str(exc))
            return

        self.status_label.setStyleSheet("color: #374151;")
        self.status_label.setText(_RESTART_NOTICE)
        self._restart_notice_shown = True
        self.finish_button.setText("Fermer")
        self.finish_button.clicked.disconnect(self._on_finish_clicked)
        self.finish_button.clicked.connect(self.accept)
        self.later_button.setVisible(False)
        self.sqlite_radio.setEnabled(False)
        self.postgresql_radio.setEnabled(False)
        self.postgresql_group.setEnabled(False)
