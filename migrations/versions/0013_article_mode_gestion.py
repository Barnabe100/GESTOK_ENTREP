"""mode de gestion des articles (vente / location)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-17 00:00:00.000000

Prépare le module Locations (lot dédié suivant) sans introduire ses tables :
- ``articles.mode_gestion`` (VENTE par défaut, server_default) : un article
  existant reste vendable sans aucun changement de comportement tant que ce
  mode n'est pas explicitement basculé vers LOCATION (mutuellement
  exclusif avec le module Ventes, voir ``app.models.catalog.Article``) ;
- ``articles.tarif_location_jour`` (nullable) : tarif catalogue journalier
  de location, sans objet tant que l'article reste en mode VENTE ;
- table ``article_mode_gestion_changements`` : historique immuable de
  chaque changement de mode (jamais de valeur rétroactive inventée pour les
  articles déjà existants — aucune ligne n'est créée par cette migration).

Migration purement additive : aucune donnée existante n'est modifiée au-delà
du défaut ``mode_gestion = 'VENTE'`` (comportement inchangé), aucune table
existante n'est supprimée ou renommée.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'mode_gestion',
                sa.Enum('VENTE', 'LOCATION', name='mode_gestion_article', native_enum=False, length=20),
                nullable=False,
                server_default='VENTE',
            )
        )
        batch_op.add_column(
            sa.Column('tarif_location_jour', sa.Numeric(precision=14, scale=2), nullable=True)
        )

    op.create_table(
        'article_mode_gestion_changements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column(
            'ancien_mode',
            sa.Enum('VENTE', 'LOCATION', name='mode_gestion_article', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column(
            'nouveau_mode',
            sa.Enum('VENTE', 'LOCATION', name='mode_gestion_article', native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column('date_heure', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('article_mode_gestion_changements', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_article_mode_gestion_changements_article_id'), ['article_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_article_mode_gestion_changements_date_heure'), ['date_heure'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('article_mode_gestion_changements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_article_mode_gestion_changements_date_heure'))
        batch_op.drop_index(batch_op.f('ix_article_mode_gestion_changements_article_id'))
    op.drop_table('article_mode_gestion_changements')

    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.drop_column('tarif_location_jour')
        batch_op.drop_column('mode_gestion')
