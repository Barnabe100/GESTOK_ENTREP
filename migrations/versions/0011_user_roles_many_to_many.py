"""multi-rôles : relation many-to-many User <-> Role

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-21 00:00:00.000000

Introduit la table d'association ``user_roles`` (many-to-many entre
``users`` et ``roles``), pour permettre à un utilisateur d'avoir plusieurs
rôles simultanément. Les permissions effectives d'un utilisateur deviennent
l'union des permissions de tous ses rôles (voir ``AuthService.login``).

Migration volontairement purement ADDITIVE : ``users.role_id`` n'est ni
modifiée, ni rendue nullable, ni supprimée dans cette révision. Après un
audit exhaustif de ses usages (constructions ORM directes dans plusieurs
tests de repositories, assertions de non-régression du module Rôles, etc.),
la conserver telle quelle en tant que simple pointeur de compatibilité vers
« un » rôle de l'utilisateur (le premier assigné) évite une migration
destructive tout en gardant `role_id` NOT NULL cohérent pour tout code qui
n'a pas encore été adapté au multi-rôle. Elle n'est plus utilisée pour le
calcul des permissions ni pour déterminer l'appartenance à un rôle — c'est
désormais exclusivement le rôle de ``user_roles``.

Préservation des données existantes : pour chaque utilisateur déjà présent,
son ``role_id`` actuel est reporté tel quel dans ``user_roles`` — après
cette migration, chaque utilisateur existant conserve donc exactement son
rôle actuel, ni plus ni moins.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'role_id'),
    )

    # Préserve le rôle actuel de chaque utilisateur existant : une ligne
    # user_roles par utilisateur, reprenant exactement son role_id actuel.
    op.execute(
        "INSERT INTO user_roles (user_id, role_id) SELECT id, role_id FROM users"
    )


def downgrade() -> None:
    # users.role_id n'a jamais été modifiée par upgrade() : rien à restaurer
    # côté users, il suffit de retirer la table d'association.
    op.drop_table('user_roles')
