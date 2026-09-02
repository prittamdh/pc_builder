"""add products.condition

Retailers sell opened-and-repackaged stock alongside sealed stock, under names like
"[RePacked]" (TPS Tech) and "Open Box OEM" (Computech, EliteHubs, PrimeABGB). Those
units are systematically cheaper, so with no way to tell them apart they win price
comparisons and lead cheapest-first sorts against sealed retail units - an "AMD Ryzen 3
4100 Open Box OEM" was the cheapest CPU in the catalog.

NULL means an ordinary sealed listing, which is the overwhelming majority, so the
column stays cheap and nothing has to be backfilled to keep meaning what it meant.

Revision ID: c4a1f7e2d910
Revises: 8d3f2c9a4b17
"""
from alembic import op
import sqlalchemy as sa

revision = "c4a1f7e2d910"
down_revision = "8d3f2c9a4b17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("condition", sa.String(32), nullable=True))
    op.create_index("ix_products_condition", "products", ["condition"])


def downgrade() -> None:
    op.drop_index("ix_products_condition", table_name="products")
    op.drop_column("products", "condition")
