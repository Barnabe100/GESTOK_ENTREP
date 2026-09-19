"""Détail en lecture seule d'une entrée du journal d'audit.

Aucune action possible depuis ce dialogue (pas de bouton de modification ni
de suppression) : la seule affaire de ce module est d'afficher lisiblement
un ``AuditSummary`` déjà chargé par ``AuditPage`` — aucun accès base de
données, aucune vérification de permission ici (la donnée fournie a déjà
été autorisée par ``AuditService.list_audits``, gardé par ``AUDIT_VIEW``).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.models.enums import ResultatAudit
from app.services.audit.audit_summary import AuditSummary

_RESULTAT_LABELS = {
    ResultatAudit.SUCCES: "Succès",
    ResultatAudit.ECHEC: "Échec",
}


class AuditDetailDialog(QDialog):
    def __init__(self, audit: AuditSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Détail de l'audit #{audit.id}")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Date/heure", QLabel(audit.date_heure.strftime("%Y-%m-%d %H:%M:%S"), self))
        form.addRow("Utilisateur", QLabel(audit.username or "—", self))
        form.addRow("Action", QLabel(audit.action, self))
        form.addRow("Entité", QLabel(audit.entite, self))
        form.addRow("Référence", QLabel(str(audit.entite_id) if audit.entite_id is not None else "—", self))
        form.addRow("Résultat", QLabel(_RESULTAT_LABELS.get(audit.resultat, str(audit.resultat)), self))

        layout.addLayout(form)

        layout.addWidget(QLabel("Détails", self))
        details_edit = QTextEdit(self)
        details_edit.setPlainText(audit.details or "—")
        details_edit.setReadOnly(True)
        layout.addWidget(details_edit)

        self.setLayout(layout)
