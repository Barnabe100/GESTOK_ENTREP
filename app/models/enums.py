"""Énumérations métier partagées par les modèles (stockées en base sous forme de texte)."""
import enum


class StatutActifInactif(str, enum.Enum):
    """Categories, fournisseurs, articles, motifs de sortie : jamais de suppression physique."""

    ACTIF = "ACTIF"
    INACTIF = "INACTIF"


class StatutOperation(str, enum.Enum):
    """Entrées, sorties, ventes : cycle de vie d'un document."""

    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"
    ANNULEE = "ANNULEE"


class StatutInventaire(str, enum.Enum):
    BROUILLON = "BROUILLON"
    VALIDE = "VALIDE"


class TypeMouvement(str, enum.Enum):
    ENTREE = "ENTREE"
    SORTIE = "SORTIE"
    VENTE = "VENTE"
    AJUSTEMENT = "AJUSTEMENT"
    ANNULATION = "ANNULATION"


class ResultatAudit(str, enum.Enum):
    SUCCES = "SUCCES"
    ECHEC = "ECHEC"


class EditionLicence(str, enum.Enum):
    DEMO = "DEMO"
    STANDARD = "STANDARD"
    PROFESSIONAL = "PROFESSIONAL"
    ENTREPRISE = "ENTREPRISE"


class StatutLicence(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIREE = "EXPIREE"
    INVALIDE = "INVALIDE"
    REVOQUEE = "REVOQUEE"
