"""ajout clients et ventes.client_id

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('clients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=150), nullable=False),
    sa.Column('telephone', sa.String(length=30), nullable=True),
    sa.Column('email', sa.String(length=150), nullable=True),
    sa.Column('adresse', sa.String(length=255), nullable=True),
    sa.Column('observations', sa.String(length=500), nullable=True),
    sa.Column('statut', sa.Enum('ACTIF', 'INACTIF', name='statut_actif_inactif', native_enum=False, length=20), nullable=False),
    sa.Column('date_creation', sa.DateTime(), nullable=False),
    sa.Column('date_modification', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # client_id nullable : les ventes existantes se retrouvent automatiquement
    # à NULL (vente comptant), sans backfill ni impact sur l'historique.
    with op.batch_alter_table('ventes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_ventes_client_id_clients', 'clients', ['client_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('ventes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ventes_client_id_clients', type_='foreignkey')
        batch_op.drop_column('client_id')
    op.drop_table('clients')
