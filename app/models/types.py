"""Types de colonnes partagés par tous les modèles.

Un seul point de définition pour la précision monétaire et la précision des
quantités, afin de ne jamais avoir à raisonner sur des ``float`` pour les
montants financiers (voir architecture validée : Decimal(14,2) partout).
"""
from sqlalchemy import Numeric

# Montants financiers : Decimal(14,2), arrondi ROUND_HALF_UP appliqué par app.utils.money
MONEY = Numeric(14, 2)

# Quantités : Decimal(14,3) pour permettre les unités fractionnaires (kg, L, ...)
QUANTITY = Numeric(14, 3)
