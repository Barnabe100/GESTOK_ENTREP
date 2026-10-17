"""récupération administrateur : table admin_recovery_codes

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17 00:00:00.000000

Ajoute la table ``admin_recovery_codes`` (un seul code actif par
utilisateur — ``user_id`` unique) : empreinte Argon2 du code, date de
génération, date de consommation (NULL tant que jamais utilisé avec
succès), compteur de tentatives échouées et date de fin de verrouillage
temporaire. Jamais le code en clair.

Migration purement additive : aucune table existante n'est modifiée.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'admin_recovery_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('failed_attempts', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('admin_recovery_codes')
