"""code_barres : unicité restreinte aux articles actifs

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-20 00:00:00.000000

Contexte (lot code-barres) : la contrainte unique globale posée en 0004
empêchait un article désactivé de « libérer » son code-barres pour un
nouvel article actif (règle métier demandée : éviter les doublons entre
articles ACTIFS seulement, en conservant l'historique d'un article
désactivé sans le modifier). Remplacée par un index unique partiel,
restreint aux lignes ``statut = 'ACTIF'`` (SQLite supporte les index
partiels via la clause WHERE) — deux articles inactifs, ou un actif et un
inactif, peuvent désormais partager le même code-barres ; deux articles
actifs, jamais.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.drop_constraint('uq_articles_code_barres', type_='unique')
    op.create_index(
        'ix_articles_code_barres_actif_unique',
        'articles',
        ['code_barres'],
        unique=True,
        sqlite_where=sa.text("statut = 'ACTIF'"),
    )


def downgrade() -> None:
    op.drop_index('ix_articles_code_barres_actif_unique', table_name='articles')
    with op.batch_alter_table('articles', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_articles_code_barres', ['code_barres'])
