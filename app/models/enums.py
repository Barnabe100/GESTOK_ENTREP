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


class StatutPaiement(str, enum.Enum):
    """Statut de paiement d'une vente, dérivé de ``total`` et de la somme des
    ``Paiement`` rattachés (voir ``SaleService``) : NON_PAYEE tant qu'aucun
    paiement n'a été enregistré, PARTIELLEMENT_PAYEE tant que le reste à
    payer est strictement positif, PAYEE dès que le reste atteint zéro (y
    compris une vente au total nul, payée par construction)."""

    NON_PAYEE = "NON_PAYEE"
    PARTIELLEMENT_PAYEE = "PARTIELLEMENT_PAYEE"
    PAYEE = "PAYEE"


class TypeMouvement(str, enum.Enum):
    ENTREE = "ENTREE"
    SORTIE = "SORTIE"
    VENTE = "VENTE"
    AJUSTEMENT = "AJUSTEMENT"
    ANNULATION = "ANNULATION"
    # Module Locations : LOCATION_SORTIE au départ (quantité négative),
    # LOCATION_RETOUR à chaque retour en bon état remis en stock (quantité
    # positive) — jamais pour une quantité immobilisée, qui ne redevient
    # jamais disponible (voir app.models.rental). Ni l'un ni l'autre ne
    # recalcule le CMUP (seule ENTREE le fait, règle StockService n°4).
    LOCATION_SORTIE = "LOCATION_SORTIE"
    LOCATION_RETOUR = "LOCATION_RETOUR"


class ModeGestionArticle(str, enum.Enum):
    """Mode de gestion d'un article (voir app.models.catalog.Article) : VENTE
    (par défaut, vendu normalement via le module Ventes) ou LOCATION (loué
    via le module Locations) — mutuellement exclusifs (décision métier
    explicite du lot Locations) : un article en mode LOCATION ne peut pas
    être vendu via SaleService tant qu'il n'a pas été rebasculé en VENTE."""

    VENTE = "VENTE"
    LOCATION = "LOCATION"


class StatutLocation(str, enum.Enum):
    """Locations : cycle de vie BROUILLON -> CONFIRMEE -> EN_COURS ->
    RETOURNEE, ou BROUILLON/CONFIRMEE -> ANNULEE (jamais après le départ —
    décision métier explicite de ce lot : une fois le stock physiquement
    sorti, seule une suite de retours peut clore la location). Pas de statut
    distinct pour un retour partiel : une location reste EN_COURS jusqu'à ce
    que toutes ses lignes soient intégralement retournées (bon état +
    immobilisée), voir LocationService."""

    BROUILLON = "BROUILLON"
    CONFIRMEE = "CONFIRMEE"
    EN_COURS = "EN_COURS"
    RETOURNEE = "RETOURNEE"
    ANNULEE = "ANNULEE"


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
