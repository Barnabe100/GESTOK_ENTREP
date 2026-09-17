"""motifs_sortie libelle unique et description

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17 01:18:08.572505

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('motifs_sortie', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.String(length=500), nullable=True))
        batch_op.create_unique_constraint('uq_motifs_sortie_libelle', ['libelle'])
        batch_op.drop_column('code')


def downgrade() -> None:
    with op.batch_alter_table('motifs_sortie', schema=None) as batch_op:
        batch_op.add_column(sa.Column('code', sa.VARCHAR(length=50), nullable=False))
        batch_op.drop_constraint('uq_motifs_sortie_libelle', type_='unique')
        batch_op.drop_column('description')
