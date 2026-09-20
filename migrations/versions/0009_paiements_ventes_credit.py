"""paiements et ventes à crédit

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-20 00:00:00.000000

Ajoute la gestion des ventes à crédit et des paiements partiels (§5) :
- table ``paiements`` (journal immuable, un paiement = une ligne, jamais
  fusionné dans ``ventes``) ;
- ``ventes.montant_paye``/``ventes.statut_paiement`` : totaux courants
  dénormalisés, recalculés dans la même transaction que chaque paiement
  inséré (voir ``SaleService.record_payment``) — jamais la source de
  vérité, à l'identique de ``articles.stock_actuel`` vis-à-vis de
  ``mouvements_stock``.

Backfill des ventes déjà existantes : ``montant_paye = 0``,
``statut_paiement = 'NON_PAYEE'`` par défaut (server_default), quel que
soit leur statut de cycle de vie (BROUILLON/VALIDEE/ANNULEE) — cohérent
avec la règle métier retenue : un paiement ne peut être enregistré que sur
une vente déjà VALIDEE (jamais sur un brouillon), donc aucune vente
antérieure à cette migration n'a de paiement à recouvrer rétroactivement.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('ventes', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('montant_paye', sa.Numeric(precision=14, scale=2), nullable=False, server_default='0')
        )
        batch_op.add_column(
            sa.Column(
                'statut_paiement',
                sa.Enum(
                    'NON_PAYEE', 'PARTIELLEMENT_PAYEE', 'PAYEE',
                    name='statut_paiement', native_enum=False, length=25,
                ),
                nullable=False,
                server_default='NON_PAYEE',
            )
        )

    op.create_table(
        'paiements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vente_id', sa.Integer(), nullable=False),
        sa.Column('montant', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('date_heure', sa.DateTime(), nullable=False),
        sa.Column('mode_paiement', sa.String(length=50), nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('commentaire', sa.String(length=500), nullable=True),
        sa.CheckConstraint('montant > 0', name='ck_paiement_montant_positif'),
        sa.ForeignKeyConstraint(['vente_id'], ['ventes.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('paiements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_paiements_vente_id'), ['vente_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_paiements_date_heure'), ['date_heure'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('paiements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_paiements_date_heure'))
        batch_op.drop_index(batch_op.f('ix_paiements_vente_id'))
    op.drop_table('paiements')

    with op.batch_alter_table('ventes', schema=None) as batch_op:
        batch_op.drop_column('statut_paiement')
        batch_op.drop_column('montant_paye')
