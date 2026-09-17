"""inventaires numero

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17 09:24:45.984209

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('inventaires', schema=None) as batch_op:
        batch_op.add_column(sa.Column('numero', sa.String(length=50), nullable=False))
        batch_op.create_index(batch_op.f('ix_inventaires_numero'), ['numero'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('inventaires', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inventaires_numero'))
        batch_op.drop_column('numero')
