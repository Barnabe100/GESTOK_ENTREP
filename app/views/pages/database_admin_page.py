"""Écran d'administration de la base de données (Lot D.6) — réservé à
l'Administrateur (``DATABASE_CONFIG_VIEW``/``DATABASE_CONFIG_UPDATE``, voir
``app.services.database_admin.database_admin_service``).

Affiche la configuration active (lecture seule, jamais le mot de passe),
la configuration en attente le cas échéant, et permet d'en préparer une
nouvelle (jamais appliquée immédiatement — voir le bandeau de redémarrage)
ou d'annuler celle déjà préparée. Chaque action passe par
``DatabaseAdminService``, qui revérifie lui-même la permission requise :
désactiver un bouton ici n'est jamais la seule protection (voir
``PermissionService.require_permission``, toujours invoquée côté service).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import DEFAULT_POSTGRESQL_PORT
from app.services.auth.permission_service import PermissionService
from app.services.database_admin.database_admin_service import DatabaseAdminService
from app.utils.exceptions import AppError
from app.views.common import confirm_action
from app.views.password_line_edit import PasswordLineEdit

_RESTART_NOTICE = (
    "Configuration enregistrée. Elle sera appliquée au prochain démarrage complet de "
    "StockManager Desktop — redémarrez l'application pour qu'elle prenne effet. "
    "L'application continue d'utiliser la configuration active pour la session en cours."
)


def _format_engine_summary(summary) -> str:
    if summary is None:
        return "—"
    if summary.backend == "sqlite":
        return "SQLite"
    profile = summary.postgresql
    return f"PostgreSQL — {profile.host}:{profile.port}/{profile.database} (utilisateur « {profile.username} »)"


class DatabaseAdminPage(QWidget):
    def __init__(
        self,
        database_admin_service: DatabaseAdminService,
        permission_service: PermissionService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = database_admin_service
        self._permissions = permission_service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(scroll_area)
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(self._build_active_group())
        content_layout.addWidget(self._build_pending_group())
        content_layout.addWidget(self._build_new_config_group())
        content_layout.addStretch(1)
        scroll_area.setWidget(content)
        layout.addWidget(scroll_area)

        self.reload()

    # -- configuration active (lecture seule) ----------------------------------------

    def _build_active_group(self) -> QGroupBox:
        group = QGroupBox("Configuration active", self)
        form = QFormLayout(group)
        self.active_label = QLabel("—", group)
        self.active_label.setWordWrap(True)
        form.addRow("Moteur", self.active_label)
        return group

    # -- configuration en attente ------------------------------------------------------

    def _build_pending_group(self) -> QGroupBox:
        group = QGroupBox("Configuration en attente", self)
        layout = QVBoxLayout(group)
        self.pending_label = QLabel("Aucune configuration en attente.", group)
        self.pending_label.setWordWrap(True)
        layout.addWidget(self.pending_label)

        self.cancel_pending_button = QPushButton("Annuler la configuration en attente", group)
        self.cancel_pending_button.setEnabled(self._permissions.has_permission("DATABASE_CONFIG_UPDATE"))
        self.cancel_pending_button.clicked.connect(self._on_cancel_pending_clicked)
        layout.addWidget(self.cancel_pending_button)
        return group

    # -- nouvelle configuration ----------------------------------------------------------

    def _build_new_config_group(self) -> QGroupBox:
        can_update = self._permissions.has_permission("DATABASE_CONFIG_UPDATE")

        group = QGroupBox("Préparer une nouvelle configuration", self)
        layout = QVBoxLayout(group)

        self.sqlite_radio = QRadioButton("SQLite", group)
        self.sqlite_radio.setChecked(True)
        self.postgresql_radio = QRadioButton("PostgreSQL", group)
        layout.addWidget(self.sqlite_radio)
        layout.addWidget(self.postgresql_radio)

        self.postgresql_fields_group = QGroupBox("Paramètres de connexion PostgreSQL", group)
        form = QFormLayout(self.postgresql_fields_group)
        self.host_edit = QLineEdit(self.postgresql_fields_group)
        form.addRow("Hôte", self.host_edit)
        self.port_spin = QSpinBox(self.postgresql_fields_group)
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(DEFAULT_POSTGRESQL_PORT)
        form.addRow("Port", self.port_spin)
        self.database_edit = QLineEdit(self.postgresql_fields_group)
        form.addRow("Base de données", self.database_edit)
        self.username_edit = QLineEdit(self.postgresql_fields_group)
        form.addRow("Utilisateur", self.username_edit)
        self.password_edit = PasswordLineEdit(self.postgresql_fields_group)
        form.addRow("Mot de passe", self.password_edit)
        self.postgresql_fields_group.setEnabled(False)
        layout.addWidget(self.postgresql_fields_group)

        self.sqlite_radio.toggled.connect(self._on_sqlite_selected)
        self.postgresql_radio.toggled.connect(self._on_postgresql_selected)

        self.new_config_status_label = QLabel("", group)
        self.new_config_status_label.setWordWrap(True)
        layout.addWidget(self.new_config_status_label)

        self.test_connection_button = QPushButton("Tester la connexion", group)
        self.test_connection_button.clicked.connect(self._on_test_connection_clicked)
        layout.addWidget(self.test_connection_button)

        self.save_pending_button = QPushButton("Enregistrer comme configuration en attente", group)
        self.save_pending_button.setProperty("variant", "primary")
        self.save_pending_button.clicked.connect(self._on_save_pending_clicked)
        layout.addWidget(self.save_pending_button)

        for widget in (
            self.sqlite_radio, self.postgresql_radio, self.test_connection_button, self.save_pending_button,
        ):
            widget.setEnabled(can_update)

        return group

    def _on_sqlite_selected(self, checked: bool) -> None:
        if not checked:
            return
        self.postgresql_fields_group.setEnabled(False)

    def _on_postgresql_selected(self, checked: bool) -> None:
        if not checked:
            return
        self.postgresql_fields_group.setEnabled(self._permissions.has_permission("DATABASE_CONFIG_UPDATE"))

    def _on_test_connection_clicked(self) -> None:
        self.new_config_status_label.setStyleSheet("color: #374151;")
        self.new_config_status_label.setText("Test de connexion en cours…")
        try:
            self._service.test_postgresql_connection(
                host=self.host_edit.text().strip(), port=self.port_spin.value(),
                database=self.database_edit.text().strip(), username=self.username_edit.text().strip(),
                password=self.password_edit.text(),
            )
        except AppError as exc:
            self.new_config_status_label.setStyleSheet("color: #DC2626;")
            self.new_config_status_label.setText(str(exc))
            return
        self.new_config_status_label.setStyleSheet("color: #16A34A;")
        self.new_config_status_label.setText("Connexion réussie.")

    def _on_save_pending_clicked(self) -> None:
        try:
            if self.sqlite_radio.isChecked():
                self._service.prepare_sqlite_pending_config()
            else:
                self._service.prepare_postgresql_pending_config(
                    host=self.host_edit.text().strip(), port=self.port_spin.value(),
                    database=self.database_edit.text().strip(), username=self.username_edit.text().strip(),
                    password=self.password_edit.text(),
                )
        except AppError as exc:
            QMessageBox.warning(self, "Enregistrement refusé", str(exc))
            return

        QMessageBox.information(self, "Configuration en attente enregistrée", _RESTART_NOTICE)
        self.password_edit.clear()
        self.reload()

    def _on_cancel_pending_clicked(self) -> None:
        if not confirm_action(
            self, "Annuler la configuration en attente",
            "La configuration active n'est pas modifiée. Voulez-vous annuler la configuration en attente ?",
        ):
            return
        try:
            self._service.cancel_pending_config()
        except AppError as exc:
            QMessageBox.warning(self, "Annulation refusée", str(exc))
            return
        self.reload()

    # -- rafraîchissement --------------------------------------------------------------

    def reload(self) -> None:
        try:
            summary = self._service.get_config_summary()
        except AppError as exc:
            self.active_label.setText(str(exc))
            return

        self.active_label.setText(_format_engine_summary(summary.active))
        if summary.pending is None:
            self.pending_label.setText("Aucune configuration en attente.")
            self.cancel_pending_button.setEnabled(False)
        else:
            self.pending_label.setText(
                _format_engine_summary(summary.pending) + "\n\nRedémarrage nécessaire pour l'appliquer."
            )
            self.cancel_pending_button.setEnabled(self._permissions.has_permission("DATABASE_CONFIG_UPDATE"))
