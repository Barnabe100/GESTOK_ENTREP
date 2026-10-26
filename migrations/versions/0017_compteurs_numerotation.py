"""compteurs de numérotation atomique des documents

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-26 00:00:00.000000

Audit multi-poste : voir ``app.models.counters.CompteurNumerotation`` et
``app.repositories.counter_repository.CounterRepository`` — remplace
``numero = f"PREFIX-{count_all()+1:06d}"`` (collisions mesurées sous accès
concurrent réel : jusqu'à 87 % à 50 postes simulés créant un document au
même instant, voir le rapport de l'audit) par un compteur persistant,
incrémenté atomiquement par une unique instruction SQL (``UPDATE ...
RETURNING``), jamais par une lecture-puis-écriture Python.

Initialisation (upgrade) : chaque compteur est initialisé au PLUS GRAND
numéro déjà attribué pour son type — jamais au nombre de lignes
(``COUNT(*)``), qui peut être inférieur si un brouillon a déjà été
supprimé (un brouillon jamais validé peut disparaître sans laisser de
trace, voir ``SaleService.create_sale`` et les équivalents) : utiliser
``COUNT(*)`` ici aurait pu faire réattribuer, pour un nouveau document, un
numéro déjà porté par un document existant. Le suffixe numérique est
extrait et comparé en Python (jamais par une expression SQL
``CAST``/``SUBSTR`` spécifique à un dialecte) : portable à l'identique sur
SQLite et PostgreSQL, sans risque sur les volumes de données réalistes de
cette application.

Migration purement additive : aucune table de document existante n'est
modifiée, aucun numéro déjà attribué n'est touché. Réversible :
``downgrade()`` supprime uniquement la nouvelle table
``compteurs_numerotation`` — sans aucun effet sur les documents eux-mêmes.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


# (préfixe utilisé dans le numéro, table portant la colonne ``numero``)
_COMPTEURS = (
    ("VNT", "ventes"),
    ("ENT", "entrees"),
    ("SOR", "sorties"),
    ("INV", "inventaires"),
    ("LOC", "locations"),
)


def _max_numero_suffix(connection, table_name: str) -> int:
    """Plus grand suffixe numérique déjà attribué parmi les ``numero``
    existants de ``table_name`` (format ``PREFIX-NNNNNN``) — 0 si la table
    est vide (aucun document créé, installation neuve)."""
    table = sa.table(table_name, sa.column("numero"))
    numeros = connection.execute(sa.select(table.c.numero)).scalars().all()
    max_suffix = 0
    for numero in numeros:
        suffixe = numero.split("-")[-1]
        try:
            max_suffix = max(max_suffix, int(suffixe))
        except ValueError:  # pragma: no cover - format déjà garanti par l'application
            continue
    return max_suffix


def upgrade() -> None:
    op.create_table(
        'compteurs_numerotation',
        sa.Column('type_document', sa.String(length=10), nullable=False),
        sa.Column('valeur', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('type_document'),
    )

    connection = op.get_bind()
    compteurs_table = sa.table(
        'compteurs_numerotation',
        sa.column('type_document', sa.String(length=10)),
        sa.column('valeur', sa.Integer()),
    )
    for type_document, table_name in _COMPTEURS:
        valeur_initiale = _max_numero_suffix(connection, table_name)
        connection.execute(
            compteurs_table.insert().values(type_document=type_document, valeur=valeur_initiale)
        )


def downgrade() -> None:
    op.drop_table('compteurs_numerotation')
