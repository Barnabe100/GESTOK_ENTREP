"""Validation du tarif choisi sur une ligne de vente ou de location
(Mission 5, §2/§3/§4) — partagée entre ``SaleService`` et
``LocationService`` : même règle formelle des deux côtés, jamais dupliquée.

Autorité unique et définitive : appelée depuis ``_build_lignes`` des deux
services, donc systématiquement revérifiée à chaque création/modification
de document, quelle que soit l'interface appelante (jamais contournable
depuis l'UI, voir le cahier des charges §6)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.models.enums import TypeTarif
from app.utils.exceptions import ValidationError


def validate_chosen_tariff(
    *,
    type_tarif: TypeTarif,
    montant: Decimal,
    prix_sous_traitant: Optional[Decimal],
    intervalle_min: Optional[Decimal],
    intervalle_max: Optional[Decimal],
    article_reference: str,
    label: str,
    multi_price_enabled: bool = True,
) -> None:
    """``montant`` est le ``prix_unitaire``/``tarif_jour`` réellement saisi
    sur la ligne — jamais recalculé ici, seulement vérifié.

    - SOUS_TRAITANT : refusé si l'article n'a aucun prix sous-traitant
      configuré (rien à appliquer).
    - AUTRE : refusé si aucun intervalle n'est configuré pour l'article, ou
      si le montant choisi en est hors bornes (bornes inclusives).
    - NORMAL : aucune contrainte supplémentaire (même liberté qu'avant
      cette mission — ``montant`` reste une vraie saisie utilisateur).

    Mission « Gestion configurable des prix multiples » : ``multi_price_enabled``
    (défaut ``True`` — comportement inchangé pour tout appelant qui ne le
    précise pas encore explicitement) reflète
    ``company_settings_service.is_multi_price_enabled()``, décidé une fois
    par l'appelant (``SaleService``/``LocationService``) avant d'appeler
    cette fonction, jamais relu ici. Lorsqu'il est ``False``, tout
    ``type_tarif`` autre que ``NORMAL`` est refusé d'emblée — avant même de
    vérifier si un tarif sous-traitant ou un intervalle « Autre » existe
    pour l'article, puisque ces tarifs supplémentaires ne doivent alors
    jamais être sélectionnables, qu'ils soient ou non configurés. Cette
    fonction restant l'autorité unique appelée par les deux services avant
    toute création de ligne (voir la docstring de module), c'est ici que la
    règle est réellement non contournable — y compris par un appel direct
    du service, sans passer par l'interface."""
    if not multi_price_enabled and type_tarif != TypeTarif.NORMAL:
        raise ValidationError(
            "Les tarifs multiples sont désactivés pour cette installation : seul le "
            f"{label} normal peut être appliqué pour « {article_reference} »."
        )
    if type_tarif == TypeTarif.SOUS_TRAITANT and prix_sous_traitant is None:
        raise ValidationError(
            f"Aucun {label} sous-traitant n'est configuré pour « {article_reference} »."
        )
    if type_tarif == TypeTarif.AUTRE:
        if intervalle_min is None or intervalle_max is None:
            raise ValidationError(
                f"Aucun intervalle « Autre {label} » n'est configuré pour « {article_reference} »."
            )
        if not (intervalle_min <= montant <= intervalle_max):
            raise ValidationError(
                f"Le {label} choisi pour « {article_reference} » doit être compris entre "
                f"{intervalle_min} et {intervalle_max}."
            )
