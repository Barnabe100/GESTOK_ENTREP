"""Moteur central des mouvements de stock.

Règles fondamentales (cahier des charges, phase StockService) :

1. **Point de passage unique.** Toute variation du stock d'un article —
   quelle qu'en soit l'origine (entrée, sortie, vente, ajustement
   d'inventaire, annulation, départ/retour de location) — doit passer par
   :meth:`StockService.apply_movement`.
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

3. **Stock jamais négatif, sans exception, y compris sous accès concurrent.**
   ``apply_movement`` n'affecte jamais ``Article.stock_actuel`` par une
   simple affectation Python (``article.stock_actuel = ...``) calculée à
   partir d'une valeur déjà chargée en mémoire : une telle lecture-puis-
   écriture perdrait silencieusement une mise à jour si deux appels
   concurrents (deux ventes validées presque simultanément sur le même
   article, par exemple) lisaient tous les deux l'ancienne valeur avant que
   l'un des deux n'écrive la sienne — le second écraserait alors le
   résultat du premier, bien que les deux ``MouvementStock`` aient été
   créés correctement (défaut constaté et corrigé dans ce lot : audit
   global, finding P0-1).

   À la place, la variation de stock est appliquée par une unique
   instruction SQL ``UPDATE ... SET stock_actuel = stock_actuel + :delta
   WHERE id = :id AND stock_actuel + :delta >= -ε`` (voir
   ``_NEGATIVE_STOCK_EPSILON`` ci-dessous pour ε), avec ``RETURNING`` pour
   récupérer en un seul aller-retour la valeur réellement appliquée. SQLite
   n'autorise qu'un seul écrivain à la fois sur une base donnée : la
   clause ``WHERE`` est donc évaluée par le moteur sur la valeur réellement
   présente en base au moment de l'écriture, jamais sur une valeur Python
   obsolète — deux appels concurrents sur le même article sont strictement
   sérialisés par SQLite lui-même (le second attend la fin de la
   transaction du premier, grâce au verrou d'écriture acquis dès la
   première instruction d'écriture de cette transaction — voir
   ``app/db/session.py`` : aucun ``isolation_level``/``busy_timeout``
   personnalisé n'est nécessaire, le délai d'attente par défaut du module
   ``sqlite3`` de Python, 5 secondes, suffit largement aux transactions
   courtes de cette application). Si la clause ``WHERE`` ne trouve aucune
   ligne correspondante, c'est que l'opération ferait réellement passer le
   stock sous zéro (évalué sur la valeur à jour) : ``ValidationError`` est
   alors levée, sans qu'aucune écriture n'ait eu lieu.

   ``ε = _NEGATIVE_STOCK_EPSILON`` est une marge strictement défensive
   (0,0005, soit la moitié de la plus petite quantité représentable à la
   précision de ce projet, 3 décimales) contre un bruit flottant résiduel
   **côté moteur SQLite** lors de l'évaluation de cette clause ``WHERE``
   (SQLite stocke les colonnes ``Numeric`` en ``REAL``, IEEE 754 — vérifié
   empiriquement sans aucune perte de précision observée sur plusieurs cas
   limites, dont l'épuisement exact à zéro d'une quantité fractionnaire,
   mais conservée par prudence). Elle ne sert jamais à arrondir une valeur
   persistée ou affichée, et ne relâche jamais la règle métier elle-même
   (toujours « jamais négatif », la marge ne pouvant absorber qu'une
   fraction infime d'une unité, jamais une quantité réellement négative).

   Le CMUP (règle 4 ci-dessous), lui, **n'est jamais calculé en SQL** : SQLite
   ne fait pas d'arithmétique décimale exacte ni du ``ROUND_HALF_UP``. Les
   valeurs ``stock_avant``/``cmup_avant`` nécessaires à son calcul sont
   obtenues par le ``RETURNING`` de la même instruction (donc garanties à
   jour, sans lecture Python préalable), puis le calcul proprement dit est
   fait en ``Decimal`` pur (``compute_new_cmup``, inchangé) avant d'être
   réécrit par une seconde instruction ``UPDATE``, elle-même protégée par
   le même verrou d'écriture SQLite déjà acquis par la première instruction
   de cette transaction — aucun autre écrivain ne peut s'intercaler entre
   les deux.

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

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.catalog import Article
from app.models.enums import TypeMouvement
from app.models.movement import MouvementStock
from app.utils.exceptions import ValidationError
from app.utils.money import round_money

# Voir règle 3 de la docstring de module.
_NEGATIVE_STOCK_EPSILON = Decimal("0.0005")


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
        location_ligne_id: Optional[int] = None,
        mouvement_origine_id: Optional[int] = None,
    ) -> MouvementStock:
        """Applique un mouvement de stock sur ``article`` et l'enregistre.

        ``quantite_signee`` est positive pour une augmentation de stock
        (ENTREE, ANNULATION d'une sortie/vente) et négative pour une
        diminution (SORTIE, VENTE, ANNULATION d'une entrée). L'appelant est
        responsable du signe : ce service ne fait aucune hypothèse sur le
        type de mouvement au-delà du recalcul du CMUP (règle 4 ci-dessus).

        Lève :class:`ValidationError` si l'opération ferait passer le stock
        en négatif — avant toute écriture, sans exception de rôle, et de
        façon sûre sous accès concurrent (voir règle 3 de la docstring de
        module : mise à jour SQL atomique et conditionnelle, jamais une
        lecture-puis-écriture Python).
        """
        if type_mouvement == TypeMouvement.ENTREE and quantite_signee <= 0:
            # Erreur de saisie pure (aucun appelant réel n'envoie une
            # quantité non positive pour une ENTREE) : autant la détecter
            # avant de solliciter la base, elle n'a pas besoin d'être
            # évaluée atomiquement.
            raise ValidationError("Une entrée doit avoir une quantité strictement positive.")

        result = session.execute(
            update(Article)
            .where(
                Article.id == article.id,
                Article.stock_actuel + quantite_signee >= -_NEGATIVE_STOCK_EPSILON,
            )
            .values(stock_actuel=Article.stock_actuel + quantite_signee)
            .returning(Article.stock_actuel, Article.cout_moyen_pondere)
        )
        row = result.first()
        if row is None:
            # La clause WHERE a bloqué l'écriture : l'opération ferait
            # réellement passer le stock sous zéro, évalué sur la valeur à
            # jour (jamais une valeur Python potentiellement obsolète) —
            # relecture uniquement pour un message d'erreur exact, sans
            # écriture.
            stock_actuel_reel = session.scalar(select(Article.stock_actuel).where(Article.id == article.id))
            stock_apres_refuse = stock_actuel_reel + quantite_signee
            raise ValidationError(
                f"Cette opération est refusée : le stock de « {article.reference} » "
                f"deviendrait négatif ({stock_apres_refuse})."
            )

        stock_apres, cmup_avant = row
        stock_avant = stock_apres - quantite_signee

        if type_mouvement == TypeMouvement.ENTREE:
            nouveau_cmup = self.compute_new_cmup(stock_avant, cmup_avant, quantite_signee, cout_unitaire or Decimal("0"))
            session.execute(update(Article).where(Article.id == article.id).values(cout_moyen_pondere=nouveau_cmup))

        # Resynchronise l'objet ORM déjà détenu par l'appelant (modifié
        # jusqu'ici uniquement via des instructions SQL Core, jamais par
        # affectation Python) — les appelants lisent ``article.stock_actuel``
        # immédiatement après cet appel.
        session.refresh(article)

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
            location_ligne_id=location_ligne_id,
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
