"""Composants d'interface réutilisés entre les pages de type liste/formulaire
(Catégories, Fournisseurs, et modules similaires à venir).

Ne contient aucune logique métier : uniquement des mécanismes d'interaction
génériques (confirmation, boucle de nouvelle tentative sur un formulaire
modal).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

from app.utils.exceptions import ValidationError


def parse_decimal(text: str, field_label: str) -> Decimal:
    """Convertit la saisie d'un champ numérique en ``Decimal``.

    Simple conversion de type (accepte la virgule décimale française) : les
    règles métier (signe, bornes) restent de la responsabilité du service
    appelé ensuite. Lève :class:`ValidationError`, capturée comme toute autre
    erreur métier par l'appelant (``except AppError``).
    """
    normalized = (text or "").strip().replace(",", ".")
    if not normalized:
        raise ValidationError(f"Le champ « {field_label} » est obligatoire.")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValidationError(f"Le champ « {field_label} » doit être un nombre valide.") from exc


def parse_optional_decimal(text: str, field_label: str) -> Optional[Decimal]:
    normalized = (text or "").strip().replace(",", ".")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValidationError(f"Le champ « {field_label} » doit être un nombre valide.") from exc


def confirm_action(parent: QWidget, title: str, message: str) -> bool:
    """Boîte de confirmation standard avant une opération sensible
    (ex. activation/désactivation)."""
    return (
        QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def run_modal_form(dialog_factory: Callable[[], QDialog], submit: Callable[[QDialog], bool]) -> None:
    """Ouvre un dialogue modal et appelle ``submit`` s'il est validé.

    Si ``submit`` retourne False (validation ou erreur métier refusée par le
    service), le dialogue est rouvert pour permettre une nouvelle saisie,
    jusqu'à annulation ou succès. ``submit`` est responsable d'afficher les
    messages d'erreur/succès à l'utilisateur.
    """
    while True:
        dialog = dialog_factory()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if submit(dialog):
            return
