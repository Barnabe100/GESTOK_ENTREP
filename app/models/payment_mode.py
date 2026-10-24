"""Modes de paiement proposés dans les formulaires de paiement (Ventes et
Locations, évolutions D/E) — liste fermée, source de référence unique
partagée par les deux modules (``PaymentFormDialog`` et
``LocationPaymentFormDialog``).

Ces trois valeurs ne sont pas nouvelles : elles reprennent exactement les
exemples déjà suggérés à l'utilisateur avant ce lot (placeholder du champ
libre, manuel utilisateur) — aucun mode supplémentaire n'a été inventé
sans usage métier déjà établi.

``Paiement.mode_paiement``/``LocationPaiement.mode_paiement`` restent de
simples colonnes texte (``String(50)``, ``nullable``) : ces libellés sont
stockés tels quels, à l'identique des valeurs déjà enregistrées par le
champ libre historique. Un paiement déjà existant dont le mode ne figure
pas dans cette liste (saisie libre antérieure à ce lot) reste affiché sans
aucune modification dans l'historique et les reçus — seule la saisie d'un
*nouveau* paiement est désormais contrainte à ces choix.
"""
from __future__ import annotations

MODES_PAIEMENT: tuple[str, ...] = ("Espèces", "Mobile Money", "Virement")
