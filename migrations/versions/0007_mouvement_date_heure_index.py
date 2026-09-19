"""index sur mouvements_stock.date_heure

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('mouvements_stock', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_mouvements_stock_date_heure'), ['date_heure'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('mouvements_stock', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mouvements_stock_date_heure'))
