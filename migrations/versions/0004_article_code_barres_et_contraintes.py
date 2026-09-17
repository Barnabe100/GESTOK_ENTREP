"""article code_barres et contraintes stock_max

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17 01:29:01.592240

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NB : l'autogénération Alembic ne détecte pas les changements de
    # CheckConstraint ; les deux contraintes stock_max sont ajoutées à la main.
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('code_barres', sa.String(length=50), nullable=True))
        batch_op.create_unique_constraint('uq_articles_code_barres', ['code_barres'])
        batch_op.create_check_constraint(
            'ck_article_stock_max_positif', 'stock_max IS NULL OR stock_max >= 0'
        )
        batch_op.create_check_constraint(
            'ck_article_stock_max_gte_min', 'stock_max IS NULL OR stock_max >= stock_min'
        )


def downgrade() -> None:
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.drop_constraint('ck_article_stock_max_gte_min', type_='check')
        batch_op.drop_constraint('ck_article_stock_max_positif', type_='check')
        batch_op.drop_constraint('uq_articles_code_barres', type_='unique')
        batch_op.drop_column('code_barres')
