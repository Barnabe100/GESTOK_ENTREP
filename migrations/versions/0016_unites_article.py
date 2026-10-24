"""unités d'articles : table de référence dédiée

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-24 00:00:00.000000

Évolution F (« unités d'articles ») : remplace le champ libre « Unité » du
formulaire article par un menu déroulant fermé, extensible via un bouton
« Nouveau » — voir ``app.models.catalog.UniteArticle`` et
``app.services.units.unite_article_service``. Même principe que
``motifs_sortie`` (migration 0001) : table de référence dédiée, jamais de
suppression physique de ligne.

Migration purement additive : ``articles.unite`` (texte libre, inchangé)
n'est touchée en rien — aucun article existant n'est modifié. Les valeurs
canoniques initiales (Pièce, Unité, Caisse, Carton, Paquet, Sac,
Kilogramme, Gramme, Litre, Millilitre, Mètre, Mètre carré) ne sont pas
insérées ici : comme pour les permissions/rôles (``app.db.seed``), le
peuplement des données de référence relève du code applicatif
(``app.db.reference_data_sync``), exécuté à chaque démarrage — y compris
pour une installation déjà existante, que cette migration doit elle aussi
amener à jour sans jamais dupliquer une unité déjà créée manuellement.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'unites_article',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('libelle', sa.String(length=20), nullable=False),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_modification', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('libelle'),
    )


def downgrade() -> None:
    op.drop_table('unites_article')
