"""module Locations : tables et rattachement aux mouvements de stock

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-17 00:00:01.000000

Ajoute le module Locations (lot dédié) :
- table ``locations`` (document, cycle de vie BROUILLON -> CONFIRMEE ->
  EN_COURS -> RETOURNEE, ou BROUILLON/CONFIRMEE -> ANNULEE) ;
- table ``location_lignes`` (une ligne par article loué, trois quantités
  distinctes : réservée / en location / immobilisée) ;
- table ``location_retours`` (un événement de retour, total ou partiel,
  par ligne — journal immuable, porte le montant facturé pour cet
  événement) ;
- table ``location_paiements`` (journal immuable des paiements reçus sur
  une location, distinct du journal des paiements des ventes) ;
- ``mouvements_stock.location_ligne_id`` (nullable) : cinquième FK
  d'origine, à l'identique d'entree_ligne_id/sortie_ligne_id/vente_ligne_id/
  inventaire_ligne_id — une seule renseignée selon le type de mouvement
  (LOCATION_SORTIE/LOCATION_RETOUR, voir app.models.enums.TypeMouvement).

Migration purement additive : aucune table existante n'est modifiée au-delà
de l'ajout de cette unique colonne nullable sur ``mouvements_stock``.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('numero', sa.String(length=50), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column(
            'statut',
            sa.Enum(
                'BROUILLON', 'CONFIRMEE', 'EN_COURS', 'RETOURNEE', 'ANNULEE',
                name='statut_location', native_enum=False, length=20,
            ),
            nullable=False,
        ),
        sa.Column('date_depart', sa.Date(), nullable=True),
        sa.Column('caution_montant', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('caution_rendue', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('commentaire', sa.String(length=500), nullable=True),
        sa.Column('annulation_motif', sa.String(length=500), nullable=True),
        sa.Column('date_creation', sa.DateTime(), nullable=False),
        sa.Column('date_modification', sa.DateTime(), nullable=False),
        sa.CheckConstraint('caution_montant >= 0', name='ck_location_caution_montant_positif'),
        sa.CheckConstraint('caution_rendue >= 0', name='ck_location_caution_rendue_positif'),
        sa.CheckConstraint('caution_rendue <= caution_montant', name='ck_location_caution_rendue_max'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('numero'),
    )
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_locations_numero'), ['numero'], unique=True)

    op.create_table(
        'location_lignes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=False),
        sa.Column('qte_prevue', sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column('qte_reservee', sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column('qte_en_location', sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column('qte_immobilisee', sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column('tarif_jour', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.CheckConstraint('qte_prevue > 0', name='ck_location_ligne_qte_prevue_positive'),
        sa.CheckConstraint('qte_reservee >= 0', name='ck_location_ligne_qte_reservee_positive'),
        sa.CheckConstraint('qte_en_location >= 0', name='ck_location_ligne_qte_en_location_positive'),
        sa.CheckConstraint('qte_immobilisee >= 0', name='ck_location_ligne_qte_immobilisee_positive'),
        sa.CheckConstraint('tarif_jour >= 0', name='ck_location_ligne_tarif_jour_positif'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id']),
        sa.ForeignKeyConstraint(['article_id'], ['articles.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'location_retours',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_ligne_id', sa.Integer(), nullable=False),
        sa.Column('date_retour', sa.Date(), nullable=False),
        sa.Column('quantite_bon_etat', sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column('quantite_immobilisee', sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column('montant_facture', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date_heure', sa.DateTime(), nullable=False),
        sa.Column('commentaire', sa.String(length=500), nullable=True),
        sa.CheckConstraint('quantite_bon_etat >= 0', name='ck_location_retour_bon_etat_positif'),
        sa.CheckConstraint('quantite_immobilisee >= 0', name='ck_location_retour_immobilisee_positif'),
        sa.CheckConstraint(
            'quantite_bon_etat + quantite_immobilisee > 0', name='ck_location_retour_quantite_non_nulle'
        ),
        sa.CheckConstraint('montant_facture >= 0', name='ck_location_retour_montant_positif'),
        sa.ForeignKeyConstraint(['location_ligne_id'], ['location_lignes.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'location_paiements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('montant', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('date_heure', sa.DateTime(), nullable=False),
        sa.Column('mode_paiement', sa.String(length=50), nullable=True),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('commentaire', sa.String(length=500), nullable=True),
        sa.CheckConstraint('montant > 0', name='ck_location_paiement_montant_positif'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('location_paiements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_location_paiements_location_id'), ['location_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_location_paiements_date_heure'), ['date_heure'], unique=False)

    with op.batch_alter_table('mouvements_stock', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_ligne_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_mouvements_stock_location_ligne_id', 'location_lignes', ['location_ligne_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('mouvements_stock', schema=None) as batch_op:
        batch_op.drop_constraint('fk_mouvements_stock_location_ligne_id', type_='foreignkey')
        batch_op.drop_column('location_ligne_id')

    with op.batch_alter_table('location_paiements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_location_paiements_date_heure'))
        batch_op.drop_index(batch_op.f('ix_location_paiements_location_id'))
    op.drop_table('location_paiements')

    op.drop_table('location_retours')
    op.drop_table('location_lignes')

    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_locations_numero'))
    op.drop_table('locations')
