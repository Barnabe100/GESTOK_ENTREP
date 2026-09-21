"""Composants d'interface réutilisés entre les pages de type liste/formulaire
(Catégories, Fournisseurs, et modules similaires à venir).

Ne contient aucune logique métier : uniquement des mécanismes d'interaction
génériques (confirmation, boucle de nouvelle tentative sur un formulaire
modal).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QWidget

from app.utils.exceptions import ValidationError

# Convention unique de l'application pour signaler un champ obligatoire dans
# un formulaire : un « * » accolé au libellé, plus cette légende commune —
# jamais la mention « (optionnel) » sur les champs facultatifs, qui créerait
# une seconde convention concurrente (voir l'audit champs obligatoires/
# facultatifs). Un champ facultatif ne porte simplement aucun marqueur.
REQUIRED_FIELD_MARKER = "*"
REQUIRED_FIELD_LEGEND = "* Champ obligatoire"


def required_label(text: str) -> str:
    """Libellé de champ marqué obligatoire — seul point d'origine du
    marqueur, pour que tous les formulaires appliquent la même convention."""
    return f"{text} {REQUIRED_FIELD_MARKER}"


def build_required_field_legend(parent: QWidget) -> QLabel:
    """Légende commune « * Champ obligatoire », à ajouter une fois par
    dialogue/page comportant au moins un champ marqué par :func:`required_label`."""
    legend = QLabel(REQUIRED_FIELD_LEGEND, parent)
    legend.setObjectName("requiredFieldLegend")
    legend.setStyleSheet("color: #6B7280; font-size: 11px;")
    return legend


def date_to_qdate(value: date) -> QDate:
    """Convertit une ``date`` Python en ``QDate`` — utilisé pour préremplir
    un ``QDateEdit`` (formulaires Ventes/Entrées/Sorties/Inventaires) à
    partir d'une date déjà connue côté Python (aujourd'hui, ou la date d'un
    document existant en modification). Jamais l'inverse dans ce sens :
    lire un ``QDateEdit`` se fait directement via ``QDate.toPython()``, qui
    ne justifie pas un symétrique ici."""
    return QDate(value.year, value.month, value.day)


def parse_date(text: str, field_label: str) -> date:
    """Convertit la saisie d'un champ date (format ``AAAA-MM-JJ``) en
    :class:`datetime.date`. Lève :class:`ValidationError` sur saisie
    invalide, capturée comme toute autre erreur métier par l'appelant."""
    normalized = (text or "").strip()
    if not normalized:
        raise ValidationError(f"Le champ « {field_label} » est obligatoire.")
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError(
            f"Le champ « {field_label} » doit être une date valide (AAAA-MM-JJ)."
        ) from exc


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
