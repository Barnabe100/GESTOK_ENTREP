"""locations.client_id devient facultatif

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-19 00:00:00.000000

Lot « Client facultatif et création rapide depuis une location » : une
location peut désormais être créée sans client identifié, à l'identique de
la vente comptant (``ventes.client_id``, déjà nullable depuis la migration
0006). ``locations.client_id`` passait alors systématiquement par
``NOT NULL`` (voir le commentaire retiré du modèle) : c'est ici le premier
assouplissement d'une contrainte ``NOT NULL`` déjà posée sur une colonne
existante dans l'historique de ce projet (les évolutions précédentes
n'ajoutaient que des colonnes/contraintes), géré via ``batch_alter_table``
(SQLite, ``render_as_batch=True``, voir migrations/env.py) qui recrée la
table en conservant les données et la contrainte de clé étrangère
existante.

Migration purement additive côté données : aucune ligne existante n'a
``client_id`` à NULL avant cette migration (c'était jusqu'ici impossible),
donc aucune ligne n'est modifiée — seule la contrainte change. Réversible :
le downgrade repose ``NOT NULL``, sûr dans ce sens puisqu'aucune location
créée après ce lot sans client ne serait compatible avec un retour en
arrière (cas documenté, pas de perte silencieuse : l'opération échouerait
alors explicitement si une telle ligne existe).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.alter_column('client_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.alter_column('client_id', existing_type=sa.Integer(), nullable=False)
