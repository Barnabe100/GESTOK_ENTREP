"""tarifs de vente et de location (normal / sous-traitant / autre)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-22 00:00:00.000000

Mission 5 (§2/§3/§4) : trois tarifs par article, pour la vente comme pour
la location, entièrement indépendants l'un de l'autre.

- ``articles.prix_sous_traitant`` / ``prix_autre_min`` / ``prix_autre_max``
  (vente) et leurs équivalents ``tarif_location_sous_traitant`` /
  ``tarif_location_autre_min`` / ``tarif_location_autre_max`` (location) :
  tous nullable, sans valeur par défaut — un article existant avant cette
  migration garde les six champs à NULL (aucun tarif alternatif configuré),
  comportement inchangé (seul ``prix_vente``/``tarif_location_jour`` reste
  utilisé, exactement comme avant). ``prix_autre_min``/``prix_autre_max``
  ne sont significatifs qu'ensemble (l'intervalle autorisé pour « Autre
  prix »), jamais un prix fixe.
- ``vente_lignes.type_tarif`` / ``location_lignes.type_tarif`` (NORMAL,
  SOUS_TRAITANT ou AUTRE) : ``server_default='NORMAL'`` pour que chaque
  ligne déjà existante (créée avant l'introduction de cette notion) soit
  correctement classée NORMAL, la seule valeur cohérente pour un prix qui
  n'a jamais été autre chose qu'une saisie libre jusqu'ici — jamais une
  valeur arbitraire inventée.

Contraintes ajoutées (défense en profondeur ; la validation croisée réelle,
avec message métier compréhensible, vit dans ``ArticleService`` et dans
``SaleService``/``LocationService`` pour le respect de l'intervalle à la
ligne) : bornes positives, intervalle bien formé (début <= fin), début de
l'intervalle <= prix sous-traitant, fin de l'intervalle >= prix normal —
voir ``app.models.catalog.Article`` pour le détail de chaque règle.

Migration purement additive et réversible : aucune donnée existante n'est
modifiée au-delà des deux ``server_default`` ci-dessus (comportement
inchangé), aucune table ni colonne existante n'est supprimée ou renommée.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prix_sous_traitant', sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(sa.Column('prix_autre_min', sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(sa.Column('prix_autre_max', sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(
            sa.Column('tarif_location_sous_traitant', sa.Numeric(precision=14, scale=2), nullable=True)
        )
        batch_op.add_column(
            sa.Column('tarif_location_autre_min', sa.Numeric(precision=14, scale=2), nullable=True)
        )
        batch_op.add_column(
            sa.Column('tarif_location_autre_max', sa.Numeric(precision=14, scale=2), nullable=True)
        )
        batch_op.create_check_constraint(
            'ck_article_prix_sous_traitant_positif', 'prix_sous_traitant IS NULL OR prix_sous_traitant >= 0'
        )
        batch_op.create_check_constraint(
            'ck_article_prix_autre_min_positif', 'prix_autre_min IS NULL OR prix_autre_min >= 0'
        )
        batch_op.create_check_constraint(
            'ck_article_prix_autre_max_positif', 'prix_autre_max IS NULL OR prix_autre_max >= 0'
        )
        batch_op.create_check_constraint(
            'ck_article_prix_autre_min_le_max',
            'prix_autre_min IS NULL OR prix_autre_max IS NULL OR prix_autre_min <= prix_autre_max',
        )
        batch_op.create_check_constraint(
            'ck_article_prix_autre_min_le_sous_traitant',
            'prix_autre_min IS NULL OR prix_sous_traitant IS NULL OR prix_autre_min <= prix_sous_traitant',
        )
        batch_op.create_check_constraint(
            'ck_article_prix_autre_max_ge_normal', 'prix_autre_max IS NULL OR prix_autre_max >= prix_vente'
        )
        batch_op.create_check_constraint(
            'ck_article_tarif_location_sous_traitant_positif',
            'tarif_location_sous_traitant IS NULL OR tarif_location_sous_traitant >= 0',
        )
        batch_op.create_check_constraint(
            'ck_article_tarif_location_autre_min_positif',
            'tarif_location_autre_min IS NULL OR tarif_location_autre_min >= 0',
        )
        batch_op.create_check_constraint(
            'ck_article_tarif_location_autre_max_positif',
            'tarif_location_autre_max IS NULL OR tarif_location_autre_max >= 0',
        )
        batch_op.create_check_constraint(
            'ck_article_tarif_location_autre_min_le_max',
            'tarif_location_autre_min IS NULL OR tarif_location_autre_max IS NULL '
            'OR tarif_location_autre_min <= tarif_location_autre_max',
        )
        batch_op.create_check_constraint(
            'ck_article_tarif_location_autre_min_le_sous_traitant',
            'tarif_location_autre_min IS NULL OR tarif_location_sous_traitant IS NULL '
            'OR tarif_location_autre_min <= tarif_location_sous_traitant',
        )
        batch_op.create_check_constraint(
            'ck_article_tarif_location_autre_max_ge_normal',
            'tarif_location_autre_max IS NULL OR tarif_location_autre_max >= tarif_location_jour',
        )

    with op.batch_alter_table('vente_lignes', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'type_tarif',
                sa.Enum('NORMAL', 'SOUS_TRAITANT', 'AUTRE', name='type_tarif', native_enum=False, length=20),
                nullable=False,
                server_default='NORMAL',
            )
        )

    with op.batch_alter_table('location_lignes', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'type_tarif',
                sa.Enum('NORMAL', 'SOUS_TRAITANT', 'AUTRE', name='type_tarif', native_enum=False, length=20),
                nullable=False,
                server_default='NORMAL',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('location_lignes', schema=None) as batch_op:
        batch_op.drop_column('type_tarif')

    with op.batch_alter_table('vente_lignes', schema=None) as batch_op:
        batch_op.drop_column('type_tarif')

    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.drop_constraint('ck_article_tarif_location_autre_max_ge_normal', type_='check')
        batch_op.drop_constraint('ck_article_tarif_location_autre_min_le_sous_traitant', type_='check')
        batch_op.drop_constraint('ck_article_tarif_location_autre_min_le_max', type_='check')
        batch_op.drop_constraint('ck_article_tarif_location_autre_max_positif', type_='check')
        batch_op.drop_constraint('ck_article_tarif_location_autre_min_positif', type_='check')
        batch_op.drop_constraint('ck_article_tarif_location_sous_traitant_positif', type_='check')
        batch_op.drop_constraint('ck_article_prix_autre_max_ge_normal', type_='check')
        batch_op.drop_constraint('ck_article_prix_autre_min_le_sous_traitant', type_='check')
        batch_op.drop_constraint('ck_article_prix_autre_min_le_max', type_='check')
        batch_op.drop_constraint('ck_article_prix_autre_max_positif', type_='check')
        batch_op.drop_constraint('ck_article_prix_autre_min_positif', type_='check')
        batch_op.drop_constraint('ck_article_prix_sous_traitant_positif', type_='check')
        batch_op.drop_column('tarif_location_autre_max')
        batch_op.drop_column('tarif_location_autre_min')
        batch_op.drop_column('tarif_location_sous_traitant')
        batch_op.drop_column('prix_autre_max')
        batch_op.drop_column('prix_autre_min')
        batch_op.drop_column('prix_sous_traitant')
