"""motif d'annulation obligatoire

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-21 00:00:00.000000

Ajoute ``annulation_motif`` (500 caractères max, nullable) sur ``entrees``,
``sorties`` et ``ventes`` : toute annulation nouvellement réalisée par
``EntryService.cancel_entry``/``ExitService.cancel_exit``/
``SaleService.cancel_sale`` doit désormais fournir un motif explicite,
conservé définitivement et jamais modifié après coup.

Colonne volontairement ``nullable=True`` (pas de ``NOT NULL``) : les
opérations déjà annulées avant cette migration n'ont aucun motif
historique à récupérer — ``annulation_motif`` reste ``NULL`` pour elles,
sans qu'aucun motif ne soit inventé rétroactivement. La contrainte
« motif obligatoire » n'est appliquée qu'au niveau applicatif (couche
service), pour toute nouvelle annulation à partir de cette version.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('entrees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('annulation_motif', sa.String(length=500), nullable=True))

    with op.batch_alter_table('sorties', schema=None) as batch_op:
        batch_op.add_column(sa.Column('annulation_motif', sa.String(length=500), nullable=True))

    with op.batch_alter_table('ventes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('annulation_motif', sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('ventes', schema=None) as batch_op:
        batch_op.drop_column('annulation_motif')

    with op.batch_alter_table('sorties', schema=None) as batch_op:
        batch_op.drop_column('annulation_motif')

    with op.batch_alter_table('entrees', schema=None) as batch_op:
        batch_op.drop_column('annulation_motif')
