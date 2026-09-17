"""Moteur central des mouvements de stock.

Règles fondamentales (cahier des charges, phase StockService) :

1. **Point de passage unique.** Toute variation du stock d'un article —
   quelle qu'en soit l'origine (entrée, sortie, vente, ajustement
   d'inventaire, annulation) — doit passer par :meth:`StockService.apply_movement`.
   Aucune vue, aucun repository, aucun autre service ne doit écrire
   directement dans ``Article.stock_actuel``.

2. **Jamais de session propre.** Contrairement aux services des phases
   précédentes (CategoryService, ArticleService, ...), ``StockService`` ne
   possède aucune méthode ouvrant son propre ``session_scope()``. Il opère
   toujours sur une session déjà ouverte par l'appelant (typiquement
   ``EntryService``), afin que « créer les lignes + appliquer les
   mouvements + mettre à jour le stock + recalculer le CMUP » constitue une
   seule transaction atomique : tout réussit, ou tout est annulé par un
   rollback (cf. §4 du cahier des charges de cette phase).

3. **Stock jamais négatif, sans exception.** Avant toute écriture,
   ``apply_movement`` calcule ``stock_après = stock_avant + quantité`` (la
   quantité étant signée : positive pour une augmentation, négative pour
   une diminution) et refuse l'opération si ce résultat est négatif — quel
   que soit le rôle de l'utilisateur, aucun contournement n'est prévu.

4. **CMUP recalculé uniquement sur une ENTRÉE.** Le Coût Moyen Unitaire
   Pondéré n'est recalculé que pour les mouvements de type ``ENTREE``, selon
   la formule validée :

       CMUP_nouveau = ((stock_avant × CMUP_avant) + (quantité × prix_achat))
                      / (stock_avant + quantité)

   Les sorties, ventes, ajustements et annulations ne modifient jamais le
   CMUP — y compris l'annulation d'une entrée : conformément à la décision
   métier validée, il n'y a aucune reconstruction rétroactive de l'historique
   du CMUP en V1.

5. **Immuabilité des mouvements.** Un ``MouvementStock`` n'est jamais modifié
   ni supprimé après création : c'est le journal d'audit du stock lui-même.
   Une correction passe toujours par un nouveau mouvement (ex. ANNULATION),
   jamais par l'édition d'un mouvement existant.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.catalog import Article
from app.models.enums import TypeMouvement
from app.models.movement import MouvementStock
from app.utils.exceptions import ValidationError
from app.utils.money import round_money


class StockService:
    """Applique les variations de stock de façon centralisée et traçable.

    Ne dépend d'aucun ``PermissionService`` : c'est un collaborateur de bas
    niveau invoqué par des services déjà responsables du contrôle des
    permissions (ex. ``EntryService.validate_entry`` vérifie
    ``STOCK_ENTRY_VALIDATE`` avant d'appeler ce service).
    """

    def apply_movement(
        self,
        session: Session,
        article: Article,
        type_mouvement: TypeMouvement,
        quantite_signee: Decimal,
        *,
        user_id: int,
        cout_unitaire: Optional[Decimal] = None,
        commentaire: Optional[str] = None,
        entree_ligne_id: Optional[int] = None,
        sortie_ligne_id: Optional[int] = None,
        vente_ligne_id: Optional[int] = None,
        inventaire_ligne_id: Optional[int] = None,
        mouvement_origine_id: Optional[int] = None,
    ) -> MouvementStock:
        """Applique un mouvement de stock sur ``article`` et l'enregistre.

        ``quantite_signee`` est positive pour une augmentation de stock
        (ENTREE, ANNULATION d'une sortie/vente) et négative pour une
        diminution (SORTIE, VENTE, ANNULATION d'une entrée). L'appelant est
        responsable du signe : ce service ne fait aucune hypothèse sur le
        type de mouvement au-delà du recalcul du CMUP (règle 4 ci-dessus).

        Lève :class:`ValidationError` si l'opération ferait passer le stock
        en négatif — avant toute écriture, sans exception de rôle.
        """
        stock_avant = article.stock_actuel
        stock_apres = stock_avant + quantite_signee

        if stock_apres < 0:
            raise ValidationError(
                f"Cette opération est refusée : le stock de « {article.reference} » "
                f"deviendrait négatif ({stock_apres})."
            )

        if type_mouvement == TypeMouvement.ENTREE:
            if quantite_signee <= 0:
                raise ValidationError("Une entrée doit avoir une quantité strictement positive.")
            article.cout_moyen_pondere = self.compute_new_cmup(
                stock_avant, article.cout_moyen_pondere, quantite_signee, cout_unitaire or Decimal("0")
            )

        article.stock_actuel = stock_apres

        movement = MouvementStock(
            article_id=article.id,
            type=type_mouvement,
            quantite=quantite_signee,
            stock_avant=stock_avant,
            stock_apres=stock_apres,
            cout_unitaire=cout_unitaire,
            entree_ligne_id=entree_ligne_id,
            sortie_ligne_id=sortie_ligne_id,
            vente_ligne_id=vente_ligne_id,
            inventaire_ligne_id=inventaire_ligne_id,
            mouvement_origine_id=mouvement_origine_id,
            user_id=user_id,
            commentaire=commentaire,
        )
        session.add(movement)
        session.flush()
        return movement

    @staticmethod
    def compute_new_cmup(
        stock_avant: Decimal, cmup_avant: Decimal, quantite_entree: Decimal, prix_achat_entree: Decimal
    ) -> Decimal:
        """Formule du CMUP validée (voir règle 4 ci-dessus).

        Le cas « stock initial nul » n'appelle aucun traitement particulier :
        avec stock_avant = 0, la formule se réduit naturellement à
        ``prix_achat_entree`` (le terme ``stock_avant × CMUP_avant``
        s'annule), qui est exactement la règle attendue.
        """
        nouveau_stock = stock_avant + quantite_entree
        valeur_avant = stock_avant * cmup_avant
        valeur_entree = quantite_entree * prix_achat_entree
        nouveau_cmup = (valeur_avant + valeur_entree) / nouveau_stock
        return round_money(nouveau_cmup)
